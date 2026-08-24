// GPU round kernel: plays classic-blackjack rounds on pre-shuffled card
// orderings in pure integer arithmetic, mirroring round.rs / strategy.rs /
// counting.rs decision-for-decision. No RNG and no floats live here: the
// host generates the exact shuffle orderings (shoe.rs OrderingGen) and
// replays all money/statistics f64 arithmetic from the packed outcome
// records this kernel emits (gpu/replay.rs). True-count thresholds are
// compared with exact integer cross-multiplication, which is equivalent
// to the CPU's f64 comparisons for the gated (quarter-representable)
// thresholds; see gpu/mod.rs for the proof sketch and the gates.
//
// One invocation plays one segment: a single shoe (flat-bet mode) or a
// slice of one shard (counting mode, carry in/out). Any situation the
// kernel cannot reproduce exactly (mid-round shoe exhaustion, tripped
// safety guards) sets a flag and the host replays that whole shard on
// the CPU engine instead, so results are never approximated.

struct Params {
    total_cards: u32,
    reshuffle_point: u32,
    burn: u32,
    n_players: u32,
    max_hands: u32,
    stride_words: u32,
    mode_shard: u32,
    counting_on: u32,
    always_insure: u32,
    rules_bits: u32,
    double_on: u32,
    n_deviations: u32,
    min_bet_e8: i32,
    max_bet_e8: i32,
    bankroll_e8: i32,
    init_decks_num: u32,
    init_decks_den: u32,
    max_rounds_per_seg: u32,
    n_segments: u32,
    pad_: u32,
}

// rules_bits, mirroring rules.rs fields the kernel consults.
const RB_DEALER_PEEK: u32 = 1u;
const RB_ALLOW_INSURANCE: u32 = 2u;
const RB_ALLOW_EARLY_SURRENDER: u32 = 4u;
const RB_ALLOW_SURRENDER: u32 = 8u;
const RB_ALLOW_SPLIT: u32 = 16u;
const RB_ALLOW_DOUBLE: u32 = 32u;
const RB_ALLOW_DAS: u32 = 64u;
const RB_ALLOW_RESPLIT: u32 = 128u;
const RB_RESPLIT_ACES: u32 = 256u;
const RB_HIT_SPLIT_ACES: u32 = 512u;
const RB_FIVE_CARD_CHARLIE: u32 = 1024u;
const RB_DEALER_H17: u32 = 2048u;

struct Segment {
    cards_base: u32,
    n_orderings: u32,
    round_budget: u32,
    rec_base: u32,
    carry_count: i32,
    decks_num: u32,
    decks_den: u32,
    next_pos: u32,
    ordering_idx: u32,
    pad0: u32,
    pad1: u32,
    pad2: u32,
}

struct Status {
    rounds_played: u32,
    flags: u32,
    out_count: i32,
    out_decks_num: u32,
    out_decks_den: u32,
    out_next: u32,
    out_ordering: u32,
    pad0: u32,
}

// Status.flags
const F_EXHAUSTED: u32 = 1u;   // mid-round out of cards: host replays shard on CPU
const F_ORDER_OUT: u32 = 2u;   // needs more orderings: host continues next wave
const F_BUDGET: u32 = 4u;      // round budget reached
const F_CUT: u32 = 8u;         // cut card reached (shoe mode: segment complete)
const F_GUARD: u32 = 16u;      // safety loop guard tripped: host replays on CPU

struct Deviation {
    hand_value: u32,
    is_soft: u32,
    dealer_value: u32,
    thr4: i32,
    above: i32,
    below: i32,
}

@group(0) @binding(0) var<uniform> params: Params;
@group(0) @binding(1) var<storage, read> cards: array<u32>;
@group(0) @binding(2) var<storage, read> segments: array<Segment>;
@group(0) @binding(3) var<storage, read> table: array<u32>;
@group(0) @binding(4) var<storage, read> deviations: array<Deviation>;
@group(0) @binding(5) var<storage, read_write> records: array<u32>;
@group(0) @binding(6) var<storage, read_write> status: array<Status>;

// Actions, in strategy.rs Action order; valid-action sets are bitmasks.
const A_HIT: u32 = 0u;
const A_STAND: u32 = 1u;
const A_DOUBLE: u32 = 2u;
const A_SPLIT: u32 = 3u;
const A_SURRENDER: u32 = 4u;

// Table cell codes (strategy.rs TableAction / encoding.py _CELL_CODES).
const T_HIT: u32 = 0u;
const T_STAND: u32 = 1u;
const T_DOUBLE: u32 = 2u;
const T_DOUBLE_STAND: u32 = 3u;
const T_SPLIT: u32 = 4u;
const T_SURRENDER: u32 = 5u;

// ---------------------------------------------------------------------
// Per-thread round state. Hand slots are seat*4 + hand (max_hands <= 4,
// n_players <= 7, gated host-side); slot 28 is the dealer.
// ---------------------------------------------------------------------
const DEALER: u32 = 28u;
var<private> h_ncards: array<u32, 29>;
var<private> h_hard: array<u32, 29>;  // sum of non-ace bj values
var<private> h_aces: array<u32, 29>;
var<private> h_r1: array<u32, 29>;
var<private> h_r2: array<u32, 29>;
var<private> h_split: array<u32, 29>;
var<private> h_done: array<u32, 29>;
var<private> h_doubled: array<u32, 29>;     // money-doubled (for the record)
var<private> h_dbl_action: array<u32, 29>;  // Double in action history
var<private> h_surr: array<u32, 29>;
var<private> h_nactions: array<u32, 29>;
var<private> h_bet_e8: array<i32, 29>;

var<private> p_nhands: array<u32, 7>;
var<private> p_money_e8: array<i32, 7>;
var<private> p_insured: array<u32, 7>;
var<private> p_bj: array<u32, 7>;
var<private> p_must_stand: array<u32, 7>;
var<private> p_mult: array<u32, 7>;

var<private> seg_cards_base: u32;
var<private> seg_n_orderings: u32;
var<private> next_pos: u32;
var<private> ordering_idx: u32;
var<private> count: i32;
var<private> pending: i32;
var<private> round_sum: i32;
var<private> decks_num: u32;
var<private> decks_den: u32;
var<private> exhausted: bool;
var<private> guard_tripped: bool;

fn rule(bit: u32) -> bool {
    return (params.rules_bits & bit) != 0u;
}

// card.rs Rank::bj_value
fn bjv(code: u32) -> u32 {
    if code == 1u {
        return 11u;
    }
    return min(code, 10u);
}

// counting.rs Counter::hi_lo
fn hilo(code: u32) -> i32 {
    if code >= 2u && code <= 6u {
        return 1;
    }
    if code >= 7u && code <= 9u {
        return 0;
    }
    return -1;
}

fn card_at(idx: u32) -> u32 {
    return (cards[idx >> 2u] >> ((idx & 3u) * 8u)) & 0xffu;
}

// shoe.rs Shoe::deal (classic, in-round): the round-aware exhaustion path
// (reshuffle_discards_mid_round) consumes RNG the host did not model, so
// hitting it aborts the segment for CPU replay; a safe constant keeps the
// abandoned round terminating.
fn deal() -> u32 {
    if next_pos >= params.total_cards {
        exhausted = true;
        return 2u;
    }
    let c = card_at(seg_cards_base + ordering_idx * params.stride_words * 4u + next_pos);
    next_pos = next_pos + 1u;
    // round.rs deal_card: every dealt card is visible to the counter.
    let hl = hilo(c);
    pending = pending + hl;
    round_sum = round_sum + hl;
    return c;
}

fn hand_add(i: u32, code: u32) {
    let n = h_ncards[i];
    if n == 0u {
        h_r1[i] = code;
    } else if n == 1u {
        h_r2[i] = code;
    }
    h_ncards[i] = n + 1u;
    if code == 1u {
        h_aces[i] = h_aces[i] + 1u;
    } else {
        h_hard[i] = h_hard[i] + bjv(code);
    }
}

// hand.rs Hand::value: aces start at 1; at most one promotion to 11 can
// ever apply (a second would need min <= 1 with two aces, impossible).
fn hval(i: u32) -> u32 {
    let minv = h_hard[i] + h_aces[i];
    if h_aces[i] > 0u && minv + 10u <= 21u {
        return minv + 10u;
    }
    return minv;
}

// hand.rs Hand::is_soft
fn hsoft(i: u32) -> bool {
    let minv = h_hard[i] + h_aces[i];
    return h_aces[i] > 0u && minv + 10u <= 21u;
}

// hand.rs Hand::is_blackjack
fn hand_bj(i: u32) -> bool {
    if h_ncards[i] != 2u || h_split[i] != 0u {
        return false;
    }
    let has_ace = h_r1[i] == 1u || h_r2[i] == 1u;
    let has_ten = bjv(h_r1[i]) == 10u || bjv(h_r2[i]) == 10u;
    return has_ace && has_ten;
}

// hand.rs Hand::is_rank_pair
fn is_pair(i: u32) -> bool {
    return h_ncards[i] == 2u && h_r1[i] == h_r2[i];
}

fn contains_ace(i: u32) -> bool {
    return h_aces[i] > 0u;
}

// counting.rs Counter::true_count comparison: tc >= thr4/4 with
// tc = count / (decks_num/decks_den). Exact integer form (decks_num > 0):
// count * 4 * decks_den >= thr4 * decks_num.
fn tc_ge(thr4: i32) -> bool {
    return count * 4 * i32(decks_den) >= thr4 * i32(decks_num);
}

// counting.rs Counter::bet_amount ramp index (multipliers 1/4/8/12/20):
// trunc(tc) <= 1 -> 0, ==2 -> 1, ==3 -> 2, ==4 -> 3, >=5 -> 4.
fn ramp_index() -> u32 {
    if tc_ge(20) {
        return 4u;
    }
    if tc_ge(16) {
        return 3u;
    }
    if tc_ge(12) {
        return 2u;
    }
    if tc_ge(8) {
        return 1u;
    }
    return 0u;
}

fn ramp_multiplier(idx: u32) -> i32 {
    if idx == 0u {
        return 1;
    }
    if idx == 1u {
        return 4;
    }
    if idx == 2u {
        return 8;
    }
    if idx == 3u {
        return 12;
    }
    return 20;
}

fn table_byte(idx: u32) -> u32 {
    return (table[idx >> 2u] >> ((idx & 3u) * 8u)) & 0xffu;
}

// strategy.rs StrategyTable::dealer_index
fn dealer_index(up_code: u32) -> u32 {
    let bj = bjv(up_code);
    if bj == 11u {
        return 9u;
    }
    if bj >= 10u {
        return 8u;
    }
    return bj - 2u;
}

// strategy.rs StrategyTable::lookup (hard 0..179, soft 180..269, pairs 270..369)
fn lookup(i: u32, dealer_idx: u32) -> u32 {
    if is_pair(i) {
        let bj = bjv(h_r1[i]);
        var row: u32;
        if bj == 11u {
            row = 9u;
        } else if bj == 10u {
            row = 8u;
        } else {
            row = bj - 2u;
        }
        return table_byte(270u + row * 10u + dealer_idx);
    }
    let v = hval(i);
    if hsoft(i) && v >= 13u && v <= 21u {
        return table_byte(180u + (v - 13u) * 10u + dealer_idx);
    }
    if v >= 4u && v <= 21u {
        return table_byte((v - 4u) * 10u + dealer_idx);
    }
    return T_HIT;
}

fn valid_has(valid: u32, action: u32) -> bool {
    return (valid & (1u << action)) != 0u;
}

// strategy.rs ValidActions::first (Python list order)
fn valid_first(valid: u32) -> u32 {
    if valid_has(valid, A_HIT) {
        return A_HIT;
    }
    if valid_has(valid, A_STAND) {
        return A_STAND;
    }
    if valid_has(valid, A_DOUBLE) {
        return A_DOUBLE;
    }
    if valid_has(valid, A_SPLIT) {
        return A_SPLIT;
    }
    return A_SURRENDER;
}

// strategy.rs TableAction::as_action for the refused-split hard re-read;
// 255 = DoubleStand (never a playable action).
fn cell_as_action(cell: u32) -> u32 {
    if cell == T_HIT {
        return A_HIT;
    }
    if cell == T_STAND {
        return A_STAND;
    }
    if cell == T_DOUBLE {
        return A_DOUBLE;
    }
    if cell == T_SPLIT {
        return A_SPLIT;
    }
    if cell == T_SURRENDER {
        return A_SURRENDER;
    }
    return 255u;
}

// strategy.rs StrategyTable::decide, transliterated fallback-for-fallback.
fn decide_table(i: u32, up_code: u32, valid: u32) -> u32 {
    let dealer_idx = dealer_index(up_code);
    let chosen = lookup(i, dealer_idx);

    if chosen == T_DOUBLE_STAND {
        if valid_has(valid, A_DOUBLE) {
            return A_DOUBLE;
        }
        if valid_has(valid, A_STAND) {
            return A_STAND;
        }
        return A_HIT;
    }
    if chosen == T_DOUBLE {
        if valid_has(valid, A_DOUBLE) {
            return A_DOUBLE;
        }
        if valid_has(valid, A_HIT) {
            return A_HIT;
        }
        return A_STAND;
    }
    if chosen == T_SURRENDER {
        if valid_has(valid, A_SURRENDER) {
            return A_SURRENDER;
        }
        if valid_has(valid, A_SPLIT) {
            return A_SPLIT;
        }
        if hval(i) >= 17u && !hsoft(i) {
            if valid_has(valid, A_STAND) {
                return A_STAND;
            }
            return A_HIT;
        }
        if valid_has(valid, A_HIT) {
            return A_HIT;
        }
        return A_STAND;
    }
    if chosen == T_SPLIT {
        if valid_has(valid, A_SPLIT) {
            return A_SPLIT;
        }
        let v = hval(i);
        if v >= 4u && v <= 21u {
            let hard_action = cell_as_action(table_byte((v - 4u) * 10u + dealer_idx));
            if hard_action != 255u && valid_has(valid, hard_action) {
                return hard_action;
            }
        }
        if valid_has(valid, A_HIT) {
            return A_HIT;
        }
        return A_STAND;
    }
    // T_HIT | T_STAND
    var action: u32;
    if chosen == T_HIT {
        action = A_HIT;
    } else {
        action = A_STAND;
    }
    if valid_has(valid, action) {
        return action;
    }
    if valid_has(valid, A_HIT) {
        return A_HIT;
    }
    if valid_has(valid, A_STAND) {
        return A_STAND;
    }
    return valid_first(valid);
}

// counting.rs Counter::decide_deviation: drain pending, then scan the
// deviation table; returns 255 to fall through to the chart.
fn decide_deviation(i: u32, up_code: u32) -> u32 {
    count = count + pending;
    pending = 0;
    let hand_value = hval(i);
    let soft = hsoft(i);
    let dealer_value = bjv(up_code);
    for (var d = 0u; d < params.n_deviations; d = d + 1u) {
        let dev = deviations[d];
        if hand_value == dev.hand_value && u32(soft) == dev.is_soft && dealer_value == dev.dealer_value {
            if dev.above >= 0 && tc_ge(dev.thr4) {
                if u32(dev.above) == A_DOUBLE && h_ncards[i] != 2u {
                    return A_HIT;
                }
                return u32(dev.above);
            }
            if dev.below >= 0 && !tc_ge(dev.thr4) {
                return u32(dev.below);
            }
        }
    }
    return 255u;
}

// round.rs TableDecider::decide
fn decide(i: u32, up_code: u32, valid: u32) -> u32 {
    if params.counting_on != 0u {
        let dev = decide_deviation(i, up_code);
        if dev != 255u {
            return dev;
        }
    }
    return decide_table(i, up_code, valid);
}

// rules.rs DoubleOn::allows
fn double_on_allows(hand_value: u32) -> bool {
    if params.double_on == 0u {
        return true;
    }
    if params.double_on == 1u {
        return hand_value >= 9u && hand_value <= 11u;
    }
    return hand_value >= 10u && hand_value <= 11u;
}

// rules.rs Rules::can_double_down (ClassicActionValidator)
fn can_double_down(i: u32) -> bool {
    if !rule(RB_ALLOW_DOUBLE) || h_ncards[i] != 2u {
        return false;
    }
    if h_split[i] != 0u && !rule(RB_ALLOW_DAS) {
        return false;
    }
    return double_on_allows(hval(i));
}

// rules.rs Rules::can_split
fn can_split(i: u32) -> bool {
    if !rule(RB_ALLOW_SPLIT) {
        return false;
    }
    if !is_pair(i) {
        return false;
    }
    if !rule(RB_ALLOW_RESPLIT) && h_split[i] != 0u {
        return false;
    }
    if contains_ace(i) && h_split[i] != 0u {
        return rule(RB_RESPLIT_ACES);
    }
    return true;
}

// rules.rs Rules::can_surrender
fn can_surrender(i: u32, is_first_action: bool) -> bool {
    if !is_first_action {
        return false;
    }
    if h_split[i] != 0u {
        return false;
    }
    return rule(RB_ALLOW_SURRENDER);
}

const V_HIT_STAND: u32 = 3u; // (1<<A_HIT) | (1<<A_STAND)
const V_STAND_ONLY: u32 = 2u;

// round.rs valid_actions_state
fn valid_actions_state(seat: u32, hand_index: u32) -> u32 {
    let i = seat * 4u + hand_index;
    let has_doubled = h_dbl_action[i] != 0u;

    let is_split_ace = h_split[i] != 0u && contains_ace(i) && h_ncards[i] >= 2u;
    if is_split_ace && !rule(RB_HIT_SPLIT_ACES) {
        return V_STAND_ONLY;
    }

    var valid = V_HIT_STAND;
    if !has_doubled && h_ncards[i] == 2u {
        let afford = p_money_e8[seat] >= h_bet_e8[i];
        if can_double_down(i) && afford {
            valid = valid | (1u << A_DOUBLE);
        }
        if can_split(i) && p_nhands[seat] < params.max_hands && afford {
            valid = valid | (1u << A_SPLIT);
        }
        let is_first_action = h_nactions[i] == 0u;
        if can_surrender(i, is_first_action) && h_split[i] == 0u {
            valid = valid | (1u << A_SURRENDER);
        }
    }
    return valid;
}

// round.rs valid_actions_property (the early-surrender variant)
fn valid_actions_property(seat: u32) -> u32 {
    let i = seat * 4u;
    if h_done[i] != 0u {
        return 0u;
    }
    let n = h_ncards[i];
    if n == 0u {
        return 0u;
    }
    if n == 1u {
        return V_HIT_STAND;
    }
    var valid = V_HIT_STAND;
    if n == 2u {
        if can_double_down(i) {
            // doubled_bet <= max_bet, exact in eighth-units
            if h_bet_e8[i] * 2 <= params.max_bet_e8 {
                valid = valid | (1u << A_DOUBLE);
            }
        }
        if is_pair(i) && can_split(i) && p_nhands[seat] < params.max_hands {
            valid = valid | (1u << A_SPLIT);
        }
        if h_split[i] == 0u {
            let is_first_action = h_nactions[i] == 0u;
            if can_surrender(i, is_first_action) {
                valid = valid | (1u << A_SURRENDER);
            }
        }
    }
    return valid;
}

// round.rs PlayerRound::hit
fn player_hit(seat: u32, i: u32, code: u32) {
    hand_add(i, code);
    if hval(i) > 21u {
        h_done[i] = 1u;
    } else if p_must_stand[seat] != 0u {
        h_done[i] = 1u;
        p_must_stand[seat] = 0u;
    }
}

// rules.rs Rules::is_five_card_charlie
fn is_five_card_charlie(i: u32) -> bool {
    if !rule(RB_FIVE_CARD_CHARLIE) {
        return false;
    }
    return h_ncards[i] >= 5u && hval(i) <= 21u;
}

// round.rs PlayerRound::is_done
fn player_is_done(seat: u32) -> bool {
    for (var h = 0u; h < p_nhands[seat]; h = h + 1u) {
        if h_done[seat * 4u + h] == 0u {
            return false;
        }
    }
    return true;
}

// round.rs player_action
fn player_action(seat: u32, hand_index: u32, action: u32) {
    let i = seat * 4u + hand_index;
    h_nactions[i] = h_nactions[i] + 1u;
    if action == A_DOUBLE {
        h_dbl_action[i] = 1u;
    }

    if action == A_HIT {
        // Reference-engine quirk: any split hand containing an ace refuses
        // the hit outright.
        if h_split[i] != 0u && contains_ace(i) && h_ncards[i] > 1u {
            h_done[i] = 1u;
            return;
        }
        let code = deal();
        player_hit(seat, i, code);
        if is_five_card_charlie(i) {
            h_done[i] = 1u;
        } else if h_split[i] != 0u && contains_ace(i) && h_ncards[i] == 2u {
            h_done[i] = 1u;
        } else if hval(i) > 21u {
            h_done[i] = 1u;
        }
        return;
    }

    if action == A_SPLIT {
        let is_splitting_aces = h_r1[i] == 1u;
        // PlayerRound::split: post the matching bet, move the second card.
        p_money_e8[seat] = p_money_e8[seat] - h_bet_e8[i];
        let moved = h_r2[i];
        let j = seat * 4u + p_nhands[seat];
        h_ncards[j] = 0u;
        h_hard[j] = 0u;
        h_aces[j] = 0u;
        h_r1[j] = 0u;
        h_r2[j] = 0u;
        h_split[j] = 1u;
        h_done[j] = 0u;
        h_doubled[j] = 0u;
        h_dbl_action[j] = 0u;
        h_surr[j] = 0u;
        h_nactions[j] = 0u;
        h_bet_e8[j] = h_bet_e8[i];
        hand_add(j, moved);
        // remove the moved card from the source hand
        h_ncards[i] = 1u;
        h_r2[i] = 0u;
        if moved == 1u {
            h_aces[i] = h_aces[i] - 1u;
        } else {
            h_hard[i] = h_hard[i] - bjv(moved);
        }
        h_split[i] = 1u;
        p_nhands[seat] = p_nhands[seat] + 1u;
        if is_splitting_aces {
            p_must_stand[seat] = 1u;
        }
        // One card to the original hand, then one to the new hand (raw
        // adds, not hits, exactly as player_action deals them).
        let c1 = deal();
        hand_add(i, c1);
        if is_splitting_aces {
            h_done[i] = 1u;
        }
        let c2 = deal();
        hand_add(j, c2);
        if is_splitting_aces {
            h_done[j] = 1u;
        }
        return;
    }

    if action == A_DOUBLE {
        // Cannot double on split aces; the action stays in the history.
        if h_split[i] != 0u && contains_ace(i) {
            return;
        }
        p_money_e8[seat] = p_money_e8[seat] - h_bet_e8[i];
        h_bet_e8[i] = h_bet_e8[i] * 2;
        h_doubled[i] = 1u;
        p_must_stand[seat] = 1u;
        let code = deal();
        player_hit(seat, i, code);
        h_done[i] = 1u;
        return;
    }

    if action == A_STAND {
        h_done[i] = 1u;
        return;
    }

    // A_SURRENDER: half the bet comes back; replay recreates the f64 flow.
    p_money_e8[seat] = p_money_e8[seat] + h_bet_e8[i] / 2;
    h_surr[i] = 1u;
    h_bet_e8[i] = 0;
    h_done[i] = 1u;
}

// rules.rs Rules::should_dealer_hit
fn should_dealer_hit() -> bool {
    let score = hval(DEALER);
    let is_soft_17 = score == 17u && hsoft(DEALER);
    return score < 17u || (is_soft_17 && rule(RB_DEALER_H17));
}

// round.rs any_live_hand
fn any_live_hand() -> bool {
    for (var seat = 0u; seat < params.n_players; seat = seat + 1u) {
        for (var h = 0u; h < p_nhands[seat]; h = h + 1u) {
            let i = seat * 4u + h;
            if h_bet_e8[i] <= 0 {
                continue;
            }
            if h_ncards[i] == 0u {
                continue;
            }
            if hval(i) > 21u {
                continue;
            }
            if hand_bj(i) {
                continue;
            }
            return true;
        }
    }
    return false;
}

// Winner codes for the record (round.rs Winner).
const W_PLAYER: u32 = 0u;
const W_DEALER: u32 = 1u;
const W_DRAW: u32 = 2u;

// round.rs calculate_winner (ClassicWinResolver chain)
fn hand_winner(i: u32, dealer_value: u32, dealer_blackjack: bool) -> u32 {
    let player_value = hval(i);
    let player_blackjack = hand_bj(i);
    if player_blackjack && dealer_blackjack {
        return W_DRAW;
    }
    if player_blackjack {
        return W_PLAYER;
    }
    if dealer_blackjack {
        return W_DEALER;
    }
    if player_value > 21u {
        return W_DEALER;
    }
    if dealer_value > 21u {
        return W_PLAYER;
    }
    if player_value > dealer_value {
        return W_PLAYER;
    }
    if dealer_value > player_value {
        return W_DEALER;
    }
    return W_DRAW;
}

fn reset_hand(i: u32) {
    h_ncards[i] = 0u;
    h_hard[i] = 0u;
    h_aces[i] = 0u;
    h_r1[i] = 0u;
    h_r2[i] = 0u;
    h_split[i] = 0u;
    h_done[i] = 0u;
    h_doubled[i] = 0u;
    h_dbl_action[i] = 0u;
    h_surr[i] = 0u;
    h_nactions[i] = 0u;
    h_bet_e8[i] = 0;
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let seg_i = gid.x;
    if seg_i >= params.n_segments {
        return;
    }
    let seg = segments[seg_i];
    seg_cards_base = seg.cards_base;
    seg_n_orderings = seg.n_orderings;
    next_pos = seg.next_pos;
    ordering_idx = seg.ordering_idx;
    count = seg.carry_count;
    decks_num = seg.decks_num;
    decks_den = seg.decks_den;
    pending = 0;
    round_sum = 0;
    exhausted = false;
    guard_tripped = false;

    var rounds_played = 0u;
    var flags = 0u;
    let peek = rule(RB_DEALER_PEEK);

    loop {
        if rounds_played >= seg.round_budget || rounds_played >= params.max_rounds_per_seg {
            flags = flags | F_BUDGET;
            break;
        }

        // run_shard: remaining BEFORE the round (and before any shuffle).
        let remaining_before = params.total_cards - min(next_pos, params.total_cards);

        // shoe.rs begin_round: cut card reached -> shuffle. In shoe mode
        // the segment IS one shoe, so the segment ends; in shard mode the
        // next ordering becomes current (host guarantees burn < the
        // reshuffle point, so one shuffle per round boundary suffices).
        if next_pos >= params.reshuffle_point {
            if params.mode_shard == 0u {
                flags = flags | F_CUT;
                break;
            }
            if ordering_idx + 1u >= seg_n_orderings {
                flags = flags | F_ORDER_OUT;
                break;
            }
            ordering_idx = ordering_idx + 1u;
            next_pos = params.burn;
        }

        // --- PlacingBetsState (round.rs play_round) ---
        for (var seat = 0u; seat < params.n_players; seat = seat + 1u) {
            var mult_idx = 0u;
            var bet: i32;
            if params.counting_on != 0u {
                mult_idx = ramp_index();
                // (min_bet * multiplier).min(max_bet).min(money); the
                // player's money at bet time is the fresh bankroll.
                bet = min(
                    min(params.min_bet_e8 * ramp_multiplier(mult_idx), params.max_bet_e8),
                    params.bankroll_e8,
                );
            } else {
                bet = params.min_bet_e8;
            }
            p_mult[seat] = mult_idx;
            p_nhands[seat] = 1u;
            p_money_e8[seat] = params.bankroll_e8 - bet;
            p_insured[seat] = 0u;
            p_bj[seat] = 0u;
            p_must_stand[seat] = 0u;
            for (var h = 0u; h < 4u; h = h + 1u) {
                reset_hand(seat * 4u + h);
            }
            h_bet_e8[seat * 4u] = bet;
        }
        reset_hand(DEALER);

        // --- DealingState: one card to each player then the dealer, twice.
        for (var deal_pass = 0u; deal_pass < 2u; deal_pass = deal_pass + 1u) {
            for (var seat = 0u; seat < params.n_players; seat = seat + 1u) {
                let c = deal();
                hand_add(seat * 4u, c);
            }
            let dc = deal();
            hand_add(DEALER, dc);
        }

        // No-peek: naturals stand automatically; resolution waits.
        if !peek {
            for (var seat = 0u; seat < params.n_players; seat = seat + 1u) {
                if hand_bj(seat * 4u) {
                    p_bj[seat] = 1u;
                    h_done[seat * 4u] = 1u;
                }
            }
        }

        let dealer_up = h_r1[DEALER];

        // --- OfferInsuranceState ---
        if dealer_up == 1u && rule(RB_ALLOW_INSURANCE) {
            var wants = false;
            if params.counting_on != 0u {
                // Counter::wants_insurance: TC >= 3 on the round-start count.
                wants = tc_ge(12);
            } else {
                wants = params.always_insure != 0u;
            }
            if wants {
                for (var seat = 0u; seat < params.n_players; seat = seat + 1u) {
                    p_insured[seat] = 1u;
                    // buy_insurance(bets[0] / 2): even in eighth-units for
                    // quarter-representable bets (gated host-side).
                    p_money_e8[seat] = p_money_e8[seat] - h_bet_e8[seat * 4u] / 2;
                }
            }
        }

        // --- Early surrender (before the peek) ---
        if rule(RB_ALLOW_EARLY_SURRENDER) {
            for (var seat = 0u; seat < params.n_players; seat = seat + 1u) {
                let i = seat * 4u;
                if h_done[i] != 0u {
                    continue;
                }
                let valid = valid_actions_property(seat);
                let action = decide(i, dealer_up, valid);
                if action == A_SURRENDER {
                    // PlayerRound::surrender, without an action-history push.
                    p_money_e8[seat] = p_money_e8[seat] + h_bet_e8[i] / 2;
                    h_surr[i] = 1u;
                    h_bet_e8[i] = 0;
                    h_done[i] = 1u;
                }
            }
        }

        var round_over = false;
        if peek {
            if (dealer_up == 1u || bjv(dealer_up) == 10u) && hand_bj(DEALER) {
                // handle_dealer_blackjack: money credits are replayed on
                // the host; here only hand/done state matters.
                for (var seat = 0u; seat < params.n_players; seat = seat + 1u) {
                    let i = seat * 4u;
                    if h_done[i] != 0u {
                        continue;
                    }
                    if hand_bj(i) {
                        h_bet_e8[i] = 0; // pushed
                    }
                    h_done[i] = 1u;
                }
                round_over = true;
            } else {
                // Peek confirmed no dealer blackjack: naturals are paid now.
                for (var seat = 0u; seat < params.n_players; seat = seat + 1u) {
                    let i = seat * 4u;
                    if hand_bj(i) {
                        h_bet_e8[i] = 0;
                        p_bj[seat] = 1u;
                        h_done[i] = 1u;
                    }
                }
            }
        }

        // --- PlayersTurnState ---
        if !round_over {
            for (var seat = 0u; seat < params.n_players; seat = seat + 1u) {
                var hand_index = 0u;
                var outer_guard = 0u;
                while hand_index < p_nhands[seat] {
                    outer_guard = outer_guard + 1u;
                    if outer_guard > 16u {
                        guard_tripped = true;
                        break;
                    }
                    let i = seat * 4u + hand_index;
                    if h_done[i] != 0u {
                        hand_index = hand_index + 1u;
                        continue;
                    }
                    var inner_guard = 0u;
                    loop {
                        if h_done[i] != 0u {
                            break;
                        }
                        inner_guard = inner_guard + 1u;
                        if inner_guard > 64u {
                            guard_tripped = true;
                            break;
                        }
                        let valid = valid_actions_state(seat, hand_index);
                        let action = decide(i, dealer_up, valid);
                        if valid_has(valid, action) {
                            player_action(seat, hand_index, action);
                        } else {
                            // Reference engine forces a stand on an
                            // invalid action.
                            h_done[i] = 1u;
                        }
                        let busted = hval(i) > 21u;
                        if busted || player_is_done(seat) {
                            break;
                        }
                    }
                    if guard_tripped {
                        break;
                    }
                    hand_index = hand_index + 1u;
                }
                if guard_tripped {
                    break;
                }
            }
        }

        // --- DealersTurnState ---
        if !round_over && any_live_hand() {
            var dealer_guard = 0u;
            while should_dealer_hit() {
                dealer_guard = dealer_guard + 1u;
                if dealer_guard > 32u {
                    guard_tripped = true;
                    break;
                }
                let dc = deal();
                hand_add(DEALER, dc);
            }
        }

        if exhausted || guard_tripped {
            // Mid-round shoe exhaustion consumes RNG the host did not
            // model (or a guard fired): the whole shard replays on CPU.
            if exhausted {
                flags = flags | F_EXHAUSTED;
            }
            if guard_tripped {
                flags = flags | F_GUARD;
            }
            break;
        }

        // --- EndRoundState: winners + the packed outcome record ---
        let dealer_value = hval(DEALER);
        let dealer_blackjack = hand_bj(DEALER);
        let rec_round_base = (seg.rec_base + rounds_played) * params.n_players;
        for (var seat = 0u; seat < params.n_players; seat = seat + 1u) {
            var word = p_mult[seat] & 7u;
            word = word | (p_insured[seat] << 3u);
            word = word | (p_bj[seat] << 4u);
            word = word | ((p_nhands[seat] & 7u) << 5u);
            if dealer_blackjack {
                word = word | (1u << 8u);
            }
            for (var h = 0u; h < p_nhands[seat]; h = h + 1u) {
                let i = seat * 4u + h;
                let w = hand_winner(i, dealer_value, dealer_blackjack);
                var hb = w & 3u;
                hb = hb | (h_doubled[i] << 2u);
                hb = hb | (h_surr[i] << 3u);
                hb = hb | (h_split[i] << 4u);
                word = word | (hb << (10u + 5u * h));
            }
            records[rec_round_base + seat] = word;
        }
        rounds_played = rounds_played + 1u;

        // --- Counter::finish_round ---
        if params.counting_on != 0u {
            let remaining_after = params.total_cards - min(next_pos, params.total_cards);
            if remaining_after > remaining_before {
                // Reshuffled: reset and recount this round's cards.
                count = round_sum;
            } else {
                count = count + pending;
            }
            pending = 0;
            round_sum = 0;
            // decks_remaining = max(0.5, remaining / 52)
            if remaining_after <= 26u {
                decks_num = 1u;
                decks_den = 2u;
            } else {
                decks_num = remaining_after;
                decks_den = 52u;
            }
        }
    }

    status[seg_i].rounds_played = rounds_played;
    status[seg_i].flags = flags;
    status[seg_i].out_count = count;
    status[seg_i].out_decks_num = decks_num;
    status[seg_i].out_decks_den = decks_den;
    status[seg_i].out_next = next_pos;
    status[seg_i].out_ordering = ordering_idx;
    status[seg_i].pad0 = 0u;
}
