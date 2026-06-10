//! Game rules, mirroring `cardsharp.blackjack.rules.Rules` under the
//! classic variant (whose `ClassicActionValidator` is what the Python
//! engine actually consults; the `Rules` fallback methods differ subtly
//! and are not replicated).

use crate::hand::Hand;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DoubleOn {
    Any,
    NineToEleven,
    TenToEleven,
}

impl DoubleOn {
    fn parse(s: &str) -> PyResult<Self> {
        match s {
            "any" => Ok(DoubleOn::Any),
            "9-11" => Ok(DoubleOn::NineToEleven),
            "10-11" => Ok(DoubleOn::TenToEleven),
            other => Err(PyValueError::new_err(format!(
                "double_on must be 'any', '9-11', or '10-11', got '{other}'"
            ))),
        }
    }

    fn allows(self, hand_value: u32) -> bool {
        match self {
            DoubleOn::Any => true,
            DoubleOn::NineToEleven => (9..=11).contains(&hand_value),
            DoubleOn::TenToEleven => (10..=11).contains(&hand_value),
        }
    }
}

/// Classic-blackjack rule set. Field defaults mirror the Python `Rules`
/// constructor so a facade can pass through `Rules.to_dict()` directly.
#[pyclass]
#[derive(Debug, Clone)]
pub struct Rules {
    #[pyo3(get)]
    pub blackjack_payout: f64,
    #[pyo3(get)]
    pub dealer_hit_soft_17: bool,
    #[pyo3(get)]
    pub allow_split: bool,
    #[pyo3(get)]
    pub allow_double_down: bool,
    #[pyo3(get)]
    pub allow_insurance: bool,
    #[pyo3(get)]
    pub allow_surrender: bool,
    #[pyo3(get)]
    pub allow_early_surrender: bool,
    #[pyo3(get)]
    pub allow_double_after_split: bool,
    #[pyo3(get)]
    pub allow_resplitting: bool,
    #[pyo3(get)]
    pub dealer_peek: bool,
    #[pyo3(get)]
    pub num_decks: u32,
    #[pyo3(get)]
    pub min_bet: f64,
    #[pyo3(get)]
    pub max_bet: f64,
    #[pyo3(get)]
    pub max_splits: u32,
    #[pyo3(get)]
    pub insurance_payout: f64,
    #[pyo3(get)]
    pub five_card_charlie: bool,
    #[pyo3(get)]
    pub penetration: f64,
    #[pyo3(get)]
    pub burn_cards: u32,
    #[pyo3(get)]
    pub resplit_aces: bool,
    #[pyo3(get)]
    pub hit_split_aces: bool,
    #[pyo3(get)]
    pub allow_obo: bool,
    pub double_on: DoubleOn,
}

#[pymethods]
impl Rules {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (
        blackjack_payout = 1.5,
        dealer_hit_soft_17 = true,
        allow_split = true,
        allow_double_down = true,
        allow_insurance = true,
        allow_surrender = true,
        allow_early_surrender = false,
        allow_double_after_split = false,
        allow_resplitting = false,
        dealer_peek = false,
        num_decks = 1,
        min_bet = 1.0,
        max_bet = 100.0,
        max_splits = 3,
        insurance_payout = 2.0,
        five_card_charlie = false,
        penetration = 0.75,
        burn_cards = 0,
        resplit_aces = false,
        hit_split_aces = false,
        allow_obo = true,
        double_on = "any",
    ))]
    fn new(
        blackjack_payout: f64,
        dealer_hit_soft_17: bool,
        allow_split: bool,
        allow_double_down: bool,
        allow_insurance: bool,
        allow_surrender: bool,
        allow_early_surrender: bool,
        allow_double_after_split: bool,
        allow_resplitting: bool,
        dealer_peek: bool,
        num_decks: u32,
        min_bet: f64,
        max_bet: f64,
        max_splits: u32,
        insurance_payout: f64,
        five_card_charlie: bool,
        penetration: f64,
        burn_cards: u32,
        resplit_aces: bool,
        hit_split_aces: bool,
        allow_obo: bool,
        double_on: &str,
    ) -> PyResult<Self> {
        if num_decks < 1 {
            return Err(PyValueError::new_err("num_decks must be at least 1"));
        }
        if !(penetration > 0.0 && penetration <= 1.0) {
            return Err(PyValueError::new_err("penetration must be in (0, 1]"));
        }
        Ok(Rules {
            blackjack_payout,
            dealer_hit_soft_17,
            allow_split,
            allow_double_down,
            allow_insurance,
            allow_surrender,
            allow_early_surrender,
            allow_double_after_split,
            allow_resplitting,
            dealer_peek,
            num_decks,
            min_bet,
            max_bet,
            max_splits,
            insurance_payout,
            five_card_charlie,
            penetration,
            burn_cards,
            resplit_aces,
            hit_split_aces,
            allow_obo,
            double_on: DoubleOn::parse(double_on)?,
        })
    }

    #[getter(double_on)]
    fn double_on_str(&self) -> &'static str {
        match self.double_on {
            DoubleOn::Any => "any",
            DoubleOn::NineToEleven => "9-11",
            DoubleOn::TenToEleven => "10-11",
        }
    }
}

impl Rules {
    /// Mirrors `Rules.can_split` (rank-equality pair, resplit gating,
    /// resplit-aces gating).
    pub fn can_split(&self, hand: &Hand) -> bool {
        if !self.allow_split {
            return false;
        }
        if !hand.is_rank_pair() {
            return false;
        }
        if !self.allow_resplitting && hand.is_split() {
            return false;
        }
        if hand.contains_ace() && hand.is_split() {
            return self.resplit_aces;
        }
        true
    }

    /// Mirrors `Rules.can_split_more`.
    pub fn can_split_more(&self, current_num_hands: usize) -> bool {
        current_num_hands < (self.max_splits as usize + 1)
    }

    /// Mirrors `ClassicActionValidator.can_double_down`.
    pub fn can_double_down(&self, hand: &Hand) -> bool {
        if !self.allow_double_down || hand.len() != 2 {
            return false;
        }
        if hand.is_split() && !self.allow_double_after_split {
            return false;
        }
        self.double_on.allows(hand.value())
    }

    /// Mirrors `ClassicActionValidator.can_surrender` (no early/late
    /// distinction at the action-validation level; `after_double` is
    /// always false because hands never carry a `doubled` attribute).
    pub fn can_surrender(&self, hand: &Hand, is_first_action: bool) -> bool {
        if !is_first_action {
            return false;
        }
        if hand.is_split() {
            return false;
        }
        self.allow_surrender
    }

    /// Mirrors `Rules.should_dealer_hit`.
    pub fn should_dealer_hit(&self, hand: &Hand) -> bool {
        let score = hand.value();
        let is_soft_17 = score == 17 && hand.is_soft();
        score < 17 || (is_soft_17 && self.dealer_hit_soft_17)
    }

    pub fn is_five_card_charlie(&self, hand: &Hand) -> bool {
        if !self.five_card_charlie {
            return false;
        }
        hand.len() >= 5 && hand.value() <= 21
    }
}
