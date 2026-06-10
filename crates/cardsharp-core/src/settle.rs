//! Conditional dealer settlement (Rao-Blackwellization).
//!
//! Once every player hand is resolved, the round's payoff depends only on
//! the dealer's remaining draws. Instead of recording the REALIZED payoff,
//! the estimator can record its exact expectation over the dealer's draw
//! distribution given the engine's knowledge: the dealer's two dealt cards
//! and the exact multiset of cards left in the shoe. The dealer still
//! draws physically afterwards -- the shoe trajectory, cut-card dynamics,
//! and counting behavior are unchanged -- so by the tower property the
//! recorded estimator keeps the same mean with strictly less variance.
//!
//! Scope notes, stated plainly:
//! - This conditions on the dealer's HOLE CARD (the engine knows it).
//!   Averaging over an unknown hole as well -- the solver's view -- would
//!   remove more variance but needs a per-composition dealer distribution
//!   whose exact computation costs more per round than the whole
//!   simulation; deliberately not attempted here.
//! - Peek games only: under no-peek rules a dealer blackjack reroutes
//!   payouts through OBO refunds and surrender voiding, which would have
//!   to be priced per outcome; under peek, the peek already excluded it.
//! - Non-CSM shoes only: the recursion models draws without replacement
//!   from the remaining shoe, which is exactly how the cut-card shoe
//!   deals. (A mid-round exhaustion reshuffle during the dealer's draws
//!   would recycle discards the recursion does not model; that requires
//!   penetration ~1.0, far outside supported counting/analysis configs.)

use crate::card::Rank;
use crate::rules::Rules;

/// A live player hand at settlement time: its final value and the bet
/// riding on it. Busted, surrendered, and already-settled hands are
/// excluded (their payoff no longer depends on the dealer).
#[derive(Debug, Clone, Copy)]
pub struct LiveHand {
    pub value: u32,
    pub bet: f64,
}

/// Dealer outcomes tracked by the recursion: final totals 17-21 and bust.
const OUTCOMES: usize = 6;

fn outcome_index(total: u32) -> usize {
    match total {
        17 => 0,
        18 => 1,
        19 => 2,
        20 => 3,
        21 => 4,
        _ => 5, // bust
    }
}

/// Payout returned to the players (stake plus winnings) for one dealer
/// outcome, mirroring the classic win resolver and payout calculator for
/// non-natural live hands: win pays 2x the bet, push returns it, loss
/// pays nothing.
fn payout_for_outcome(hands: &[LiveHand], outcome: usize) -> f64 {
    let mut total = 0.0;
    for hand in hands {
        let payout = if outcome == 5 {
            hand.bet * 2.0 // dealer bust: every live hand wins
        } else {
            let dealer_total = 17 + outcome as u32;
            if hand.value > dealer_total {
                hand.bet * 2.0
            } else if hand.value == dealer_total {
                hand.bet
            } else {
                0.0
            }
        };
        total += payout;
    }
    total
}

/// Hi-lo of the dealer state machine: add one card to (total, soft),
/// demoting a soft ace on overflow. Equivalent to `Hand::value` for the
/// dealer's draw sequence (two simultaneous 11-aces are impossible).
fn dealer_add(total: u32, soft: bool, card: Rank) -> (u32, bool) {
    let (mut total, mut soft) = if card == Rank::Ace {
        if total + 11 <= 21 {
            (total + 11, true)
        } else {
            (total + 1, soft) // ace counts 1 when 11 would bust
        }
    } else {
        (total + card.bj_value(), soft)
    };
    if total > 21 && soft {
        total -= 10;
        soft = false;
    }
    (total, soft)
}

fn dealer_should_hit(total: u32, soft: bool, rules: &Rules) -> bool {
    total < 17 || (total == 17 && soft && rules.dealer_hit_soft_17)
}

/// Exact dealer-outcome distribution given the dealer's current (total,
/// soft) state and the remaining-shoe composition collapsed to ten value
/// classes (ten/jack/queen/king are interchangeable for dealer totals,
/// so collapsing them is exact and prunes the recursion's branching).
/// Class order: ace, 2..9, ten-class. Draws are without replacement;
/// probabilities accumulate into `dist` weighted by `p`.
fn outcome_distribution(
    total: u32,
    soft: bool,
    class_counts: &mut [u32; 10],
    n_remaining: u32,
    rules: &Rules,
    p: f64,
    dist: &mut [f64; OUTCOMES],
) {
    if !dealer_should_hit(total, soft, rules) {
        let idx = if total > 21 { 5 } else { outcome_index(total) };
        dist[idx] += p;
        return;
    }
    debug_assert!(n_remaining > 0, "dealer must hit but the shoe is empty");
    for class_idx in 0..10 {
        let count = class_counts[class_idx];
        if count == 0 {
            continue;
        }
        // Class values: index 0 = ace, 1..=8 = pips 2..9, 9 = ten-class.
        let rank = match class_idx {
            0 => Rank::Ace,
            9 => Rank::Ten,
            pip => Rank::ALL[pip],
        };
        let p_draw = p * count as f64 / n_remaining as f64;
        let (next_total, next_soft) = dealer_add(total, soft, rank);
        class_counts[class_idx] -= 1;
        outcome_distribution(
            next_total,
            next_soft,
            class_counts,
            n_remaining - 1,
            rules,
            p_draw,
            dist,
        );
        class_counts[class_idx] += 1;
    }
}

/// Collapse 13 rank counts (Rank::ALL order) into the ten value classes
/// the dealer recursion branches over.
fn collapse_to_classes(counts: &[u32; 13]) -> [u32; 10] {
    let mut classes = [0u32; 10];
    classes[0] = counts[0]; // ace
    classes[1..9].copy_from_slice(&counts[1..9]); // pips 2..9
    classes[9] = counts[9] + counts[10] + counts[11] + counts[12]; // T J Q K
    classes
}

/// Expected total payout to the players over the dealer's draw
/// distribution. `dealer` is the dealer's two-card state; `counts` the
/// exact remaining-shoe composition the dealer will draw from.
pub fn expected_payout(
    dealer_total: u32,
    dealer_soft: bool,
    counts: &mut [u32; 13],
    n_remaining: u32,
    rules: &Rules,
    hands: &[LiveHand],
) -> f64 {
    let mut classes = collapse_to_classes(counts);
    let mut dist = [0.0f64; OUTCOMES];
    outcome_distribution(
        dealer_total,
        dealer_soft,
        &mut classes,
        n_remaining,
        rules,
        1.0,
        &mut dist,
    );
    let mut expected = 0.0;
    for (outcome, p) in dist.iter().enumerate() {
        if *p > 0.0 {
            expected += p * payout_for_outcome(hands, outcome);
        }
    }
    expected
}

#[cfg(test)]
mod tests {
    use super::*;

    fn h17_rules() -> Rules {
        // Plain struct construction; only dealer_hit_soft_17 matters here.
        Rules {
            blackjack_payout: 1.5,
            dealer_hit_soft_17: true,
            allow_split: true,
            allow_double_down: true,
            allow_insurance: true,
            allow_surrender: true,
            allow_early_surrender: false,
            allow_double_after_split: true,
            allow_resplitting: false,
            dealer_peek: true,
            num_decks: 6,
            min_bet: 10.0,
            max_bet: 1000.0,
            max_splits: 3,
            insurance_payout: 2.0,
            five_card_charlie: false,
            penetration: 0.75,
            burn_cards: 0,
            resplit_aces: false,
            hit_split_aces: false,
            allow_obo: true,
            use_csm: false,
            double_on: crate::rules::DoubleOn::Any,
        }
    }

    #[test]
    fn pat_dealer_is_deterministic() {
        let rules = h17_rules();
        let mut counts = [24u32; 13];
        let hands = [LiveHand {
            value: 19,
            bet: 10.0,
        }];
        // Dealer hard 18 stands immediately: player 19 wins exactly.
        let e = expected_payout(18, false, &mut counts, 312, &rules, &hands);
        assert!((e - 20.0).abs() < 1e-12);
        // Dealer hard 20: player 19 loses exactly.
        let e = expected_payout(20, false, &mut counts, 312, &rules, &hands);
        assert!(e.abs() < 1e-12);
    }

    #[test]
    fn ace_counts_one_on_high_totals() {
        // Regression: an ace drawn onto hard 12 makes 13 (and keeps
        // drawing), never 23. A shoe of only aces forces the dealer from
        // hard 12 through 13..16 up to 17: a guaranteed stand on 17.
        let rules = h17_rules();
        let hands = [LiveHand {
            value: 18,
            bet: 10.0,
        }];
        let mut counts = [0u32; 13];
        counts[0] = 24; // aces only
        let e = expected_payout(12, false, &mut counts, 24, &rules, &hands);
        assert!(
            (e - 20.0).abs() < 1e-12,
            "dealer 12 + five aces = 17, player 18 wins; got {e}"
        );
        assert_eq!(dealer_add(12, false, Rank::Ace), (13, false));
        assert_eq!(dealer_add(16, false, Rank::Ace), (17, false));
        assert_eq!(dealer_add(5, false, Rank::Ace), (16, true));
    }

    #[test]
    fn distribution_sums_to_one_and_counts_are_restored() {
        let rules = h17_rules();
        let mut classes = collapse_to_classes(&[24u32; 13]);
        assert_eq!(classes[9], 96, "ten-class collapses T/J/Q/K");
        let before = classes;
        let mut dist = [0.0f64; OUTCOMES];
        outcome_distribution(12, false, &mut classes, 312, &rules, 1.0, &mut dist);
        let total: f64 = dist.iter().sum();
        assert!((total - 1.0).abs() < 1e-9, "probabilities sum to {total}");
        assert_eq!(classes, before, "recursion must restore counts");
    }

    #[test]
    fn soft_17_hits_under_h17_only() {
        let mut rules = h17_rules();
        let hands = [LiveHand {
            value: 18,
            bet: 10.0,
        }];
        // Force a degenerate shoe of only tens: a soft 17 that hits
        // becomes hard 17 (A demoted), then stands; an S17 dealer stands
        // on soft 17 directly. Either way the player 18 wins -- but the
        // H17 path must consume a draw, which we can see through a shoe
        // where drawing changes the outcome: use a shoe of only fours:
        // soft 17 + 4 = 21 under H17 (player loses), stands at 17 under
        // S17 (player wins).
        let mut counts = [0u32; 13];
        counts[3] = 24; // fours
        let e_h17 = expected_payout(17, true, &mut counts, 24, &rules, &hands);
        assert!(e_h17.abs() < 1e-12, "H17 dealer reaches 21: player loses");
        rules.dealer_hit_soft_17 = false;
        let e_s17 = expected_payout(17, true, &mut counts, 24, &rules, &hands);
        assert!(
            (e_s17 - 20.0).abs() < 1e-12,
            "S17 dealer stands: player wins"
        );
    }
}
