//! Hi-Lo card counting, mirroring `cardsharp.blackjack.strategy.CountingStrategy`.
//!
//! Timing semantics are preserved exactly from the reference engine:
//!
//! - Dealt cards enter a pending queue and are folded into the running
//!   count only when a PLAY decision is made (the Python strategy walks
//!   `game.visible_cards` inside `decide_action`). Bets and the insurance
//!   decision therefore use the round-START count, while play decisions
//!   see everything dealt so far -- including the dealer's hole card, a
//!   reference-engine quirk the parity suite pins.
//! - After each round the remainder of the queue is folded in; if the
//!   shoe was reshuffled (cards remaining went UP), the count resets and
//!   the round's cards are recounted from zero, then decks_remaining is
//!   refreshed as max(0.5, cards_remaining / 52).
//! - Play deviations (the Illustrious 18) arrive as data from Python so
//!   the strategy module stays the single source of truth; they return
//!   raw actions without validity resolution, exactly as the reference
//!   does (an inapplicable deviation is forced to stand by the state
//!   machine's invalid-action path).
//!
//! Known divergence, documented: after a mid-round shoe exhaustion the
//! reference engine's id-based dedup skips re-dealt physical cards for
//! the remainder of that round; this mirror counts them. Reachable only
//! at penetration ~1.0, outside every supported counting configuration.

use crate::card::Rank;
use crate::hand::Hand;
use crate::strategy::Action;
use std::fmt;

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;

#[derive(Debug, Clone, Copy)]
pub struct Deviation {
    pub hand_value: u32,
    pub is_soft: bool,
    pub dealer_value: u32,
    pub threshold: f64,
    pub above: Option<Action>,
    pub below: Option<Action>,
}

/// A deviation table carried an action code outside the encoding.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct InvalidActionCode(pub u8);

impl fmt::Display for InvalidActionCode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "deviation action code {} not in {{0=Hit,1=Stand,2=Double}}",
            self.0
        )
    }
}

impl std::error::Error for InvalidActionCode {}

/// Decode a deviation-table action code. Only the Python constructor
/// feeds codes in; a Rust caller builds `Deviation`s directly.
#[cfg(feature = "python")]
fn action_from_code(code: u8) -> Result<Action, InvalidActionCode> {
    Ok(match code {
        0 => Action::Hit,
        1 => Action::Stand,
        2 => Action::Double,
        other => return Err(InvalidActionCode(other)),
    })
}

/// Counting configuration crossing the Python boundary: the deviation
/// table (from `strategy._COUNTING_DEVIATIONS`) plus the deck count the
/// strategy was constructed with.
#[cfg_attr(feature = "python", pyclass)]
#[derive(Debug, Clone)]
pub struct CountingConfig {
    pub deviations: Vec<Deviation>,
    pub initial_decks: f64,
}

#[cfg(feature = "python")]
#[pymethods]
impl CountingConfig {
    #[new]
    #[allow(clippy::type_complexity)]
    fn new(
        deviations: Vec<(u32, bool, u32, f64, Option<u8>, Option<u8>)>,
        initial_decks: f64,
    ) -> PyResult<Self> {
        let to_action = |code: Option<u8>| -> PyResult<Option<Action>> {
            code.map(action_from_code)
                .transpose()
                .map_err(|e| PyValueError::new_err(e.to_string()))
        };
        let deviations = deviations
            .into_iter()
            .map(
                |(hand_value, is_soft, dealer_value, threshold, above, below)| {
                    Ok(Deviation {
                        hand_value,
                        is_soft,
                        dealer_value,
                        threshold,
                        above: to_action(above)?,
                        below: to_action(below)?,
                    })
                },
            )
            .collect::<PyResult<Vec<_>>>()?;
        Ok(CountingConfig {
            deviations,
            initial_decks,
        })
    }
}

pub struct Counter {
    config: CountingConfig,
    count: i64,
    decks_remaining: f64,
    /// Cards dealt this round, not yet folded into the count.
    pending: Vec<Rank>,
    /// Every card dealt this round (for the post-reshuffle recount).
    round_cards: Vec<Rank>,
}

impl Counter {
    pub fn new(config: CountingConfig) -> Self {
        let initial_decks = config.initial_decks;
        Counter {
            config,
            count: 0,
            decks_remaining: initial_decks,
            pending: Vec::with_capacity(16),
            round_cards: Vec::with_capacity(16),
        }
    }

    fn hi_lo(card: Rank) -> i64 {
        match card {
            Rank::Two | Rank::Three | Rank::Four | Rank::Five | Rank::Six => 1,
            Rank::Seven | Rank::Eight | Rank::Nine => 0,
            Rank::Ten | Rank::Jack | Rank::Queen | Rank::King | Rank::Ace => -1,
        }
    }

    /// A card was dealt (any seat, including the dealer's hole card).
    pub fn saw_card(&mut self, card: Rank) {
        self.pending.push(card);
        self.round_cards.push(card);
    }

    fn drain_pending(&mut self) {
        for card in self.pending.drain(..) {
            self.count += Self::hi_lo(card);
        }
    }

    fn true_count(&self) -> f64 {
        self.count as f64 / self.decks_remaining.max(0.5)
    }

    /// Mirrors `CountingStrategy.get_bet_amount`: truncate the true count
    /// toward zero and ramp 1x/4x/8x/12x/20x of the minimum bet.
    pub fn bet_amount(&self, min_bet: f64, max_bet: f64, player_money: f64) -> f64 {
        let tc = self.true_count().trunc() as i64;
        let multiplier = match tc {
            i64::MIN..=1 => 1.0,
            2 => 4.0,
            3 => 8.0,
            4 => 12.0,
            _ => 20.0,
        };
        (min_bet * multiplier).min(max_bet).min(player_money)
    }

    /// Mirrors `CountingStrategy.decide_insurance`: insure at TC >= 3.
    /// Uses the round-start count (no drain), as the reference does.
    pub fn wants_insurance(&self) -> bool {
        self.true_count() >= 3.0
    }

    /// A play decision is being made: fold in everything dealt so far,
    /// then consult the deviation table. `None` falls through to the
    /// strategy chart. Mirrors `CountingStrategy.decide_action` +
    /// `_count_based_decision`.
    pub fn decide_deviation(&mut self, hand: &Hand, dealer_up: Rank) -> Option<Action> {
        self.drain_pending();
        let true_count = self.true_count();
        let hand_value = hand.value();
        let is_soft = hand.is_soft();
        let dealer_value = dealer_up.bj_value();

        for d in &self.config.deviations {
            if hand_value == d.hand_value && is_soft == d.is_soft && dealer_value == d.dealer_value
            {
                if let Some(above) = d.above
                    && true_count >= d.threshold
                {
                    if above == Action::Double && hand.len() != 2 {
                        return Some(Action::Hit);
                    }
                    return Some(above);
                }
                if let Some(below) = d.below
                    && true_count < d.threshold
                {
                    return Some(below);
                }
            }
        }
        None
    }

    /// Round teardown, mirroring the counting block in `play_game`: fold
    /// the rest of the round's cards in (or reset and recount them all if
    /// the shoe was reshuffled), then refresh decks_remaining.
    pub fn finish_round(&mut self, remaining_before: usize, remaining_after: usize) {
        let reshuffled = remaining_after > remaining_before;
        if reshuffled {
            self.count = 0;
            self.decks_remaining = self.config.initial_decks;
            self.pending.clear();
            for &card in &self.round_cards {
                self.count += Self::hi_lo(card);
            }
        } else {
            self.drain_pending();
        }
        self.round_cards.clear();
        self.decks_remaining = (remaining_after as f64 / 52.0).max(0.5);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn counter() -> Counter {
        Counter::new(CountingConfig {
            deviations: vec![Deviation {
                hand_value: 16,
                is_soft: false,
                dealer_value: 10,
                threshold: 0.0,
                above: Some(Action::Stand),
                below: Some(Action::Hit),
            }],
            initial_decks: 6.0,
        })
    }

    #[test]
    fn bets_use_round_start_count() {
        let mut c = counter();
        // High count established last round.
        for _ in 0..24 {
            c.saw_card(Rank::Five);
        }
        c.finish_round(312, 288);
        let tc_bet = c.bet_amount(10.0, 1000.0, 1000.0);
        assert!(tc_bet > 10.0);
        // Cards dealt this round do not affect the bet until a decision.
        c.saw_card(Rank::Ten);
        assert_eq!(c.bet_amount(10.0, 1000.0, 1000.0), tc_bet);
    }

    #[test]
    fn deviation_stands_sixteen_versus_ten_at_positive_count() {
        let mut c = counter();
        for _ in 0..12 {
            c.saw_card(Rank::Two);
        }
        let mut hand = Hand::new();
        hand.add(Rank::Ten);
        hand.add(Rank::Six);
        assert_eq!(c.decide_deviation(&hand, Rank::Ten), Some(Action::Stand));
    }

    #[test]
    fn reshuffle_resets_and_recounts_the_round() {
        let mut c = counter();
        for _ in 0..5 {
            c.saw_card(Rank::Two);
        }
        c.finish_round(312, 290); // normal round: count = +5
        assert_eq!(c.count, 5);
        for _ in 0..10 {
            c.saw_card(Rank::Ten);
        }
        c.finish_round(50, 300); // remaining went up: reshuffle
        assert_eq!(c.count, -10); // prior +5 discarded; this round recounted
    }
}
