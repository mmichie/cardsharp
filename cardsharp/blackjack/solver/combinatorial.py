"""Single-pass combinatorial blackjack solver.

Enumerates complete game sequences (deal -> player -> dealer -> payout)
from a shared composition-tracked deck. Dealer draws are evaluated inline
at each player terminal state, capturing player-dealer shoe correlation.

This closes the ~0.05-0.13% gap between the fast two-phase solver and
published WoO Appendix 9 values.

Usage:
    from cardsharp.blackjack.solver import solve
    result = solve(rules, mode="combinatorial")
"""

import math

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.rules import Rules

from .types import (
    CARD_VALUES,
    CARD_IDX,
    Deck,
    StateEV,
    add_card,
    display_value,
    hand_state_from_cards,
)
from .dealer import dealer_blackjack_prob
from .engine import SolverResult, _generate_strategy, _compute_house_edge


# ---------------------------------------------------------------------------
# Dealer evaluation (inline, returns EV directly)
# ---------------------------------------------------------------------------


def _dealer_probs(dealer_hard, dealer_usable, deck, hit_soft_17, memo):
    """Dealer outcome probability distribution from this state and deck.

    Returns {final_total: probability} where 22 = bust.
    Memoized by (dealer_state, deck_composition) -- shared across all
    player totals, making it much more cache-friendly than folding
    player_total into the key.
    """
    from collections import defaultdict

    key = ("dp", dealer_hard, dealer_usable, deck.key)
    if key in memo:
        return memo[key]

    disp = display_value(dealer_hard, dealer_usable)

    if disp > 21:
        result = {22: 1.0}
        memo[key] = result
        return result

    if disp >= 18 or (disp == 17 and not (dealer_usable and hit_soft_17)):
        result = {disp: 1.0}
        memo[key] = result
        return result

    result = defaultdict(float)
    for ci, cv in enumerate(CARD_VALUES):
        p, new_deck = deck.draw(ci)
        if p == 0:
            continue
        new_hard, new_usable, _ = add_card(dealer_hard, dealer_usable, cv)
        sub = _dealer_probs(new_hard, new_usable, new_deck, hit_soft_17, memo)
        for total, sp in sub.items():
            result[total] += p * sp

    result = dict(result)
    memo[key] = result
    return result


def _ev_vs_dealer(player_disp, dealer_probs):
    """Player's EV against a dealer outcome distribution."""
    ev = 0.0
    for total, p in dealer_probs.items():
        if total == 22:
            ev += p
        elif player_disp > total:
            ev += p
        elif player_disp < total:
            ev -= p
    return ev


# ---------------------------------------------------------------------------
# Player terminal -> dealer (with peek conditioning)
# ---------------------------------------------------------------------------


def _ev_stand(player_disp, upcard, deck, hit_soft_17, peek, memo):
    """EV of standing: inline dealer evaluation from current deck.

    For peek with Ace/10 upcard, conditions on hole card not making BJ.
    """
    d_hard_init = upcard
    d_usable_init = upcard == 1

    if not peek or upcard not in (1, 10):
        dp = _dealer_probs(d_hard_init, d_usable_init, deck, hit_soft_17, memo)
        return _ev_vs_dealer(player_disp, dp)

    # Peek conditioning: exclude the hole card that makes BJ
    exclude_val = 10 if upcard == 1 else 1
    exclude_idx = CARD_IDX[exclude_val]
    p_exclude = deck.draw(exclude_idx)[0]

    if p_exclude >= 1.0:
        return -1.0

    from collections import defaultdict
    cond_factor = 1.0 / (1.0 - p_exclude)
    combined = defaultdict(float)

    for ci, hole_val in enumerate(CARD_VALUES):
        if hole_val == exclude_val:
            continue
        p_hole, deck_after_hole = deck.draw(ci)
        if p_hole == 0:
            continue
        adj_p = p_hole * cond_factor

        hard, usable, _ = add_card(d_hard_init, d_usable_init, hole_val)
        sub = _dealer_probs(hard, usable, deck_after_hole, hit_soft_17, memo)
        for total, sp in sub.items():
            combined[total] += adj_p * sp

    return _ev_vs_dealer(player_disp, combined)


# ---------------------------------------------------------------------------
# Player actions (hit / double / surrender)
# ---------------------------------------------------------------------------


def _ev_hit(hard_total, usable_ace, upcard, deck, hit_soft_17, peek, memo):
    """EV of hitting and playing optimally afterward."""
    key = ("h", hard_total, usable_ace, upcard, deck.key)
    if key in memo:
        return memo[key]

    ev = 0.0
    for ci, cv in enumerate(CARD_VALUES):
        p, new_deck = deck.draw(ci)
        if p == 0:
            continue
        new_hard, new_usable, disp = add_card(hard_total, usable_ace, cv)

        if disp > 21:
            ev += p * (-1.0)
        else:
            s = _ev_stand(disp, upcard, new_deck, hit_soft_17, peek, memo)
            h = _ev_hit(new_hard, new_usable, upcard, new_deck, hit_soft_17,
                        peek, memo)
            ev += p * max(s, h)

    memo[key] = ev
    return ev


def _ev_double(hard_total, usable_ace, upcard, deck, hit_soft_17, peek, memo):
    """EV of doubling: one card, forced stand, 2x bet."""
    ev = 0.0
    for ci, cv in enumerate(CARD_VALUES):
        p, new_deck = deck.draw(ci)
        if p == 0:
            continue
        _, _, disp = add_card(hard_total, usable_ace, cv)

        if disp > 21:
            ev += p * (-2.0)
        else:
            ev += p * 2.0 * _ev_stand(disp, upcard, new_deck, hit_soft_17,
                                       peek, memo)
    return ev


# ---------------------------------------------------------------------------
# Player decision (best of all available actions)
# ---------------------------------------------------------------------------


def _ev_player(hard, usable, upcard, deck, hit_soft_17, peek,
               allow_double, allow_surrender, memo):
    """Best EV across all available actions for a player hand."""
    key = ("p", hard, usable, upcard, allow_double, deck.key)
    if key in memo:
        return memo[key]

    disp = display_value(hard, usable)

    ev_s = _ev_stand(disp, upcard, deck, hit_soft_17, peek, memo)
    ev_h = _ev_hit(hard, usable, upcard, deck, hit_soft_17, peek, memo)

    candidates = [(ev_s, Action.STAND), (ev_h, Action.HIT)]

    if allow_double:
        ev_d = _ev_double(hard, usable, upcard, deck, hit_soft_17, peek, memo)
        candidates.append((ev_d, Action.DOUBLE))

    if allow_surrender:
        candidates.append((-0.5, Action.SURRENDER))

    best_ev, best_action = max(candidates, key=lambda x: x[0])
    memo[key] = best_ev
    return best_ev


# ---------------------------------------------------------------------------
# Split evaluation
# ---------------------------------------------------------------------------


def _ev_one_split_hand(pair_value, card_val, upcard, deck, allow_das,
                       hit_soft_17, peek, memo):
    """EV of one split hand with inline dealer evaluation."""
    hard = pair_value + card_val
    usable = False
    if pair_value == 1 and hard + 10 <= 21:
        usable = True
    elif card_val == 1 and hard + 10 <= 21:
        usable = True

    disp = hard + 10 if usable else hard
    if disp > 21 and usable:
        usable = False
        disp = hard

    # Split aces: forced stand
    if pair_value == 1:
        return _ev_stand(disp, upcard, deck, hit_soft_17, peek, memo)

    if disp > 21:
        return -1.0

    ev_s = _ev_stand(disp, upcard, deck, hit_soft_17, peek, memo)
    ev_h = _ev_hit(hard, usable, upcard, deck, hit_soft_17, peek, memo)
    candidates = [ev_s, ev_h]

    if allow_das:
        ev_d = _ev_double(hard, usable, upcard, deck, hit_soft_17, peek, memo)
        candidates.append(ev_d)

    return max(candidates)


def _ev_split(pair_value, upcard, deck, allow_das, hit_soft_17, peek,
              allow_resplit, max_hands, resplit_aces, memo):
    """EV of splitting with correlated initial card dealing.

    Each split hand is evaluated independently with inline dealer probs.
    Cross-hand deck depletion is captured for the initial deal cards.
    """
    can_resplit = (
        allow_resplit
        and max_hands > 2
        and (pair_value != 1 or resplit_aces)
    )

    total_ev = 0.0

    for ci1, cv1 in enumerate(CARD_VALUES):
        p1, deck1 = deck.draw(ci1)
        if p1 == 0:
            continue

        for ci2, cv2 in enumerate(CARD_VALUES):
            p2, deck2 = deck1.draw(ci2)
            if p2 == 0:
                continue

            # Hand 1
            if cv1 == pair_value and can_resplit:
                ev_play = _ev_one_split_hand(pair_value, cv1, upcard, deck2,
                                             allow_das, hit_soft_17, peek, memo)
                ev_resplit = _ev_split(pair_value, upcard, deck2, allow_das,
                                      hit_soft_17, peek, allow_resplit,
                                      max_hands - 1, resplit_aces, memo) - 1.0
                ev_h1 = max(ev_play, ev_resplit)
            else:
                ev_h1 = _ev_one_split_hand(pair_value, cv1, upcard, deck2,
                                           allow_das, hit_soft_17, peek, memo)

            # Hand 2
            if cv2 == pair_value and can_resplit:
                ev_play = _ev_one_split_hand(pair_value, cv2, upcard, deck2,
                                             allow_das, hit_soft_17, peek, memo)
                ev_resplit = _ev_split(pair_value, upcard, deck2, allow_das,
                                      hit_soft_17, peek, allow_resplit,
                                      max_hands - 1, resplit_aces, memo) - 1.0
                ev_h2 = max(ev_play, ev_resplit)
            else:
                ev_h2 = _ev_one_split_hand(pair_value, cv2, upcard, deck2,
                                           allow_das, hit_soft_17, peek, memo)

            total_ev += p1 * p2 * (ev_h1 + ev_h2)

    return total_ev


# ---------------------------------------------------------------------------
# Top-level solve
# ---------------------------------------------------------------------------


def solve_combinatorial(rules: Rules) -> SolverResult:
    """Compute exact house edge using single-pass combinatorial analysis."""
    use_finite = hasattr(rules, "num_decks") and rules.num_decks <= 8
    deck = Deck.finite(rules.num_decks) if use_finite else Deck.infinite()

    hit_soft_17 = rules.dealer_hit_soft_17
    bj_payout = rules.blackjack_payout
    allow_double = rules.allow_double_down
    allow_split = rules.allow_split
    allow_das = rules.allow_double_after_split
    allow_surrender = rules.allow_surrender and (
        rules.allow_late_surrender or rules.allow_early_surrender
        or rules.allow_surrender
    )
    peek = rules.dealer_peek
    allow_resplit = rules.allow_resplitting
    max_hands = rules.max_splits + 1
    resplit_aces = rules.resplit_aces

    # Compute EV for every initial deal
    ev_table = {}

    for upcard in CARD_VALUES:
        # Share memo across all player hands for the same upcard.
        # Dealer sub-computations from overlapping deck states are reused.
        upcard_memo = {}

        for i, cv1 in enumerate(CARD_VALUES):
            for cv2 in CARD_VALUES[i:]:
                hard, usable, _, is_pair = hand_state_from_cards(cv1, cv2)
                pair_value = cv1 if is_pair else 0

                remaining = deck.remove_card(cv1).remove_card(cv2).remove_card(upcard)
                memo = upcard_memo

                # Compute EVs for each action
                disp = display_value(hard, usable)

                ev_s = _ev_stand(disp, upcard, remaining, hit_soft_17, peek, memo)
                ev_h = _ev_hit(hard, usable, upcard, remaining, hit_soft_17,
                               peek, memo)
                ev_d = (
                    _ev_double(hard, usable, upcard, remaining, hit_soft_17,
                               peek, memo)
                    if allow_double else math.nan
                )
                ev_sp = (
                    _ev_split(pair_value, upcard, remaining, allow_das,
                              hit_soft_17, peek, allow_resplit, max_hands,
                              resplit_aces, memo)
                    if (is_pair and allow_split) else math.nan
                )
                ev_sr = -0.5 if allow_surrender else math.nan

                candidates = [(ev_h, Action.HIT), (ev_s, Action.STAND)]
                if allow_double:
                    candidates.append((ev_d, Action.DOUBLE))
                if is_pair and allow_split:
                    candidates.append((ev_sp, Action.SPLIT))
                if allow_surrender:
                    candidates.append((ev_sr, Action.SURRENDER))

                best_ev, best_action = max(candidates, key=lambda x: x[0])

                sev = StateEV(
                    hit=ev_h, stand=ev_s, double=ev_d, split=ev_sp,
                    surrender=ev_sr, best_action=best_action, best_ev=best_ev,
                )
                ev_table[(cv1, cv2, upcard)] = sev

    house_edge = _compute_house_edge(ev_table, deck, bj_payout, peek)
    strategy = _generate_strategy(ev_table, allow_double)

    return SolverResult(
        house_edge=house_edge, ev_table=ev_table, strategy=strategy,
    )
