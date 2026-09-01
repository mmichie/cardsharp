//! Game rules, mirroring `cardsharp.blackjack.rules.Rules` under the
//! classic variant (whose `ClassicActionValidator` is what the Python
//! engine actually consults; the `Rules` fallback methods differ subtly
//! and are not replicated).

use crate::hand::Hand;
use std::fmt;

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum DoubleOn {
    // The serde spellings are the canonical strings `parse` accepts and
    // `as_str` emits, so a serialized rule set reads the same in JSON as
    // it does through the Python constructor.
    #[cfg_attr(feature = "serde", serde(rename = "any"))]
    Any,
    #[cfg_attr(feature = "serde", serde(rename = "9-11"))]
    NineToEleven,
    #[cfg_attr(feature = "serde", serde(rename = "10-11"))]
    TenToEleven,
}

/// `DoubleOn::parse` rejected its input. Native so the rules layer owes
/// nothing to PyO3; the boundary turns it into a `ValueError` carrying the
/// same sentence the pyclass constructor always raised.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InvalidDoubleOn(pub String);

impl fmt::Display for InvalidDoubleOn {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "double_on must be 'any', '9-11', or '10-11', got '{}'",
            self.0
        )
    }
}

impl std::error::Error for InvalidDoubleOn {}

impl DoubleOn {
    pub fn parse(s: &str) -> Result<Self, InvalidDoubleOn> {
        match s {
            "any" => Ok(DoubleOn::Any),
            "9-11" => Ok(DoubleOn::NineToEleven),
            "10-11" => Ok(DoubleOn::TenToEleven),
            other => Err(InvalidDoubleOn(other.to_string())),
        }
    }

    /// The canonical string form, and the one `parse` round-trips.
    pub fn as_str(self) -> &'static str {
        match self {
            DoubleOn::Any => "any",
            DoubleOn::NineToEleven => "9-11",
            DoubleOn::TenToEleven => "10-11",
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

/// A rule set failed validation. Mirrors, exactly, the three sentences the
/// pyclass constructor has always raised.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InvalidRules {
    NumDecks,
    Penetration,
    DoubleOn(InvalidDoubleOn),
}

impl fmt::Display for InvalidRules {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            InvalidRules::NumDecks => write!(f, "num_decks must be at least 1"),
            InvalidRules::Penetration => write!(f, "penetration must be in (0, 1]"),
            InvalidRules::DoubleOn(e) => e.fmt(f),
        }
    }
}

impl std::error::Error for InvalidRules {}

impl From<InvalidDoubleOn> for InvalidRules {
    fn from(e: InvalidDoubleOn) -> Self {
        InvalidRules::DoubleOn(e)
    }
}

/// Classic-blackjack rule set. Field defaults mirror the Python `Rules`
/// constructor so a facade can pass through `Rules.to_dict()` directly,
/// and `Default` carries the same values so a Rust caller can write
/// `Rules { num_decks: 6, ..Default::default() }`.
///
/// **The field order below is the canonical order** -- `digest` hashes the
/// fields in exactly this sequence. Reordering them changes every digest.
#[cfg_attr(feature = "python", pyclass)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
#[derive(Debug, Clone, PartialEq)]
pub struct Rules {
    pub blackjack_payout: f64,
    pub dealer_hit_soft_17: bool,
    pub allow_split: bool,
    pub allow_double_down: bool,
    pub allow_insurance: bool,
    pub allow_surrender: bool,
    pub allow_early_surrender: bool,
    pub allow_double_after_split: bool,
    pub allow_resplitting: bool,
    pub dealer_peek: bool,
    pub num_decks: u32,
    pub min_bet: f64,
    pub max_bet: f64,
    pub max_splits: u32,
    pub insurance_payout: f64,
    pub five_card_charlie: bool,
    pub penetration: f64,
    pub burn_cards: u32,
    pub resplit_aces: bool,
    pub hit_split_aces: bool,
    pub allow_obo: bool,
    pub use_csm: bool,
    pub double_on: DoubleOn,
}

impl Default for Rules {
    /// The same defaults the pyclass constructor's signature declares.
    fn default() -> Self {
        Rules {
            blackjack_payout: 1.5,
            dealer_hit_soft_17: true,
            allow_split: true,
            allow_double_down: true,
            allow_insurance: true,
            allow_surrender: true,
            allow_early_surrender: false,
            allow_double_after_split: false,
            allow_resplitting: false,
            dealer_peek: false,
            num_decks: 1,
            min_bet: 1.0,
            max_bet: 100.0,
            max_splits: 3,
            insurance_payout: 2.0,
            five_card_charlie: false,
            penetration: 0.75,
            burn_cards: 0,
            resplit_aces: false,
            hit_split_aces: false,
            allow_obo: true,
            use_csm: false,
            double_on: DoubleOn::Any,
        }
    }
}

#[cfg(feature = "python")]
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
        use_csm = false,
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
        use_csm: bool,
        double_on: &str,
    ) -> PyResult<Self> {
        let rules = Rules {
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
            use_csm,
            double_on: DoubleOn::parse(double_on)
                .map_err(|e| PyValueError::new_err(e.to_string()))?,
        };
        rules
            .validate()
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(rules)
    }

    // Read-only attribute surface. These live here rather than as
    // `#[pyo3(get)]` on the fields so the struct definition itself carries
    // no PyO3 attributes and compiles unchanged with `python` off.
    #[getter]
    fn blackjack_payout(&self) -> f64 {
        self.blackjack_payout
    }
    #[getter]
    fn dealer_hit_soft_17(&self) -> bool {
        self.dealer_hit_soft_17
    }
    #[getter]
    fn allow_split(&self) -> bool {
        self.allow_split
    }
    #[getter]
    fn allow_double_down(&self) -> bool {
        self.allow_double_down
    }
    #[getter]
    fn allow_insurance(&self) -> bool {
        self.allow_insurance
    }
    #[getter]
    fn allow_surrender(&self) -> bool {
        self.allow_surrender
    }
    #[getter]
    fn allow_early_surrender(&self) -> bool {
        self.allow_early_surrender
    }
    #[getter]
    fn allow_double_after_split(&self) -> bool {
        self.allow_double_after_split
    }
    #[getter]
    fn allow_resplitting(&self) -> bool {
        self.allow_resplitting
    }
    #[getter]
    fn dealer_peek(&self) -> bool {
        self.dealer_peek
    }
    #[getter]
    fn num_decks(&self) -> u32 {
        self.num_decks
    }
    #[getter]
    fn min_bet(&self) -> f64 {
        self.min_bet
    }
    #[getter]
    fn max_bet(&self) -> f64 {
        self.max_bet
    }
    #[getter]
    fn max_splits(&self) -> u32 {
        self.max_splits
    }
    #[getter]
    fn insurance_payout(&self) -> f64 {
        self.insurance_payout
    }
    #[getter]
    fn five_card_charlie(&self) -> bool {
        self.five_card_charlie
    }
    #[getter]
    fn penetration(&self) -> f64 {
        self.penetration
    }
    #[getter]
    fn burn_cards(&self) -> u32 {
        self.burn_cards
    }
    #[getter]
    fn resplit_aces(&self) -> bool {
        self.resplit_aces
    }
    #[getter]
    fn hit_split_aces(&self) -> bool {
        self.hit_split_aces
    }
    #[getter]
    fn allow_obo(&self) -> bool {
        self.allow_obo
    }
    #[getter]
    fn use_csm(&self) -> bool {
        self.use_csm
    }

    /// The canonical string, matching what the constructor accepts.
    #[getter(double_on)]
    fn double_on_str(&self) -> &'static str {
        self.double_on.as_str()
    }

    /// See `Rules::digest`. Exposed so a Python caller can stamp a stored
    /// round with the rules it was dealt under.
    #[pyo3(name = "digest")]
    fn digest_py(&self) -> u64 {
        self.digest()
    }
}

impl Rules {
    /// The two constraints the constructor has always enforced.
    pub fn validate(&self) -> Result<(), InvalidRules> {
        if self.num_decks < 1 {
            return Err(InvalidRules::NumDecks);
        }
        if !(self.penetration > 0.0 && self.penetration <= 1.0) {
            return Err(InvalidRules::Penetration);
        }
        Ok(())
    }

    /// A stable 64-bit fingerprint of the rule set, so a stored round can
    /// prove it resumes under the rules it was dealt with.
    ///
    /// FNV-1a over the fields in the struct's declaration order, which is
    /// the canonical order: booleans as one byte, integers little-endian,
    /// floats as `to_bits` (two rule sets whose payouts differ in the last
    /// ulp are different rule sets), `double_on` as its canonical string.
    /// FNV rather than `DefaultHasher` because the standard hasher's
    /// output is explicitly not guaranteed stable across Rust releases,
    /// and this value is meant to be written down.
    ///
    /// **Adding a field changes every digest, and that is the point**: a
    /// round stored under a rule set that did not yet have the field
    /// cannot claim to resume under one that does. Widening the struct is
    /// therefore a deliberate invalidation of every stored digest.
    pub fn digest(&self) -> u64 {
        const OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
        const PRIME: u64 = 0x0000_0100_0000_01b3;

        let mut hash = OFFSET;
        let mut eat = |bytes: &[u8]| {
            for b in bytes {
                hash ^= u64::from(*b);
                hash = hash.wrapping_mul(PRIME);
            }
        };

        eat(&self.blackjack_payout.to_bits().to_le_bytes());
        eat(&[u8::from(self.dealer_hit_soft_17)]);
        eat(&[u8::from(self.allow_split)]);
        eat(&[u8::from(self.allow_double_down)]);
        eat(&[u8::from(self.allow_insurance)]);
        eat(&[u8::from(self.allow_surrender)]);
        eat(&[u8::from(self.allow_early_surrender)]);
        eat(&[u8::from(self.allow_double_after_split)]);
        eat(&[u8::from(self.allow_resplitting)]);
        eat(&[u8::from(self.dealer_peek)]);
        eat(&self.num_decks.to_le_bytes());
        eat(&self.min_bet.to_bits().to_le_bytes());
        eat(&self.max_bet.to_bits().to_le_bytes());
        eat(&self.max_splits.to_le_bytes());
        eat(&self.insurance_payout.to_bits().to_le_bytes());
        eat(&[u8::from(self.five_card_charlie)]);
        eat(&self.penetration.to_bits().to_le_bytes());
        eat(&self.burn_cards.to_le_bytes());
        eat(&[u8::from(self.resplit_aces)]);
        eat(&[u8::from(self.hit_split_aces)]);
        eat(&[u8::from(self.allow_obo)]);
        eat(&[u8::from(self.use_csm)]);
        eat(self.double_on.as_str().as_bytes());
        hash
    }

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

#[cfg(test)]
mod tests {
    use super::*;

    /// The digest is written down by callers, so its value for the default
    /// rule set is pinned. A change here is a change to every stored
    /// digest and must be deliberate.
    #[test]
    fn the_default_rule_set_has_a_pinned_digest() {
        assert_eq!(Rules::default().digest(), 0x9a92_3dad_61bb_a79f);
    }

    #[test]
    fn the_digest_is_stable_across_calls_and_clones() {
        let rules = Rules {
            num_decks: 6,
            double_on: DoubleOn::NineToEleven,
            ..Default::default()
        };
        assert_eq!(rules.digest(), rules.digest());
        assert_eq!(rules.digest(), rules.clone().digest());
    }

    #[test]
    fn every_field_moves_the_digest() {
        let base = Rules::default();
        let mut seen = vec![base.digest()];
        let variants = [
            Rules {
                blackjack_payout: 1.2,
                ..base.clone()
            },
            Rules {
                dealer_hit_soft_17: false,
                ..base.clone()
            },
            Rules {
                allow_split: false,
                ..base.clone()
            },
            Rules {
                allow_double_down: false,
                ..base.clone()
            },
            Rules {
                allow_insurance: false,
                ..base.clone()
            },
            Rules {
                allow_surrender: false,
                ..base.clone()
            },
            Rules {
                allow_early_surrender: true,
                ..base.clone()
            },
            Rules {
                allow_double_after_split: true,
                ..base.clone()
            },
            Rules {
                allow_resplitting: true,
                ..base.clone()
            },
            Rules {
                dealer_peek: true,
                ..base.clone()
            },
            Rules {
                num_decks: 6,
                ..base.clone()
            },
            Rules {
                min_bet: 5.0,
                ..base.clone()
            },
            Rules {
                max_bet: 500.0,
                ..base.clone()
            },
            Rules {
                max_splits: 1,
                ..base.clone()
            },
            Rules {
                insurance_payout: 3.0,
                ..base.clone()
            },
            Rules {
                five_card_charlie: true,
                ..base.clone()
            },
            Rules {
                penetration: 0.5,
                ..base.clone()
            },
            Rules {
                burn_cards: 1,
                ..base.clone()
            },
            Rules {
                resplit_aces: true,
                ..base.clone()
            },
            Rules {
                hit_split_aces: true,
                ..base.clone()
            },
            Rules {
                allow_obo: false,
                ..base.clone()
            },
            Rules {
                use_csm: true,
                ..base.clone()
            },
            Rules {
                double_on: DoubleOn::TenToEleven,
                ..base.clone()
            },
        ];
        // One variant per field, so a field left out of `digest` shows up
        // here as a collision rather than as silently interchangeable
        // rule sets.
        assert_eq!(variants.len(), 23);
        for variant in variants {
            let digest = variant.digest();
            assert!(
                !seen.contains(&digest),
                "digest collision: {variant:?} hashes to {digest:#x}"
            );
            seen.push(digest);
        }
    }

    #[test]
    fn double_on_round_trips_through_its_canonical_string() {
        for variant in [DoubleOn::Any, DoubleOn::NineToEleven, DoubleOn::TenToEleven] {
            assert_eq!(DoubleOn::parse(variant.as_str()).unwrap(), variant);
        }
        assert_eq!(
            DoubleOn::parse("12-13").unwrap_err().to_string(),
            "double_on must be 'any', '9-11', or '10-11', got '12-13'"
        );
    }

    #[test]
    fn validate_rejects_what_the_constructor_always_rejected() {
        assert_eq!(
            Rules {
                num_decks: 0,
                ..Default::default()
            }
            .validate()
            .unwrap_err()
            .to_string(),
            "num_decks must be at least 1"
        );
        assert_eq!(
            Rules {
                penetration: 0.0,
                ..Default::default()
            }
            .validate()
            .unwrap_err()
            .to_string(),
            "penetration must be in (0, 1]"
        );
        assert!(
            Rules {
                penetration: 1.5,
                ..Default::default()
            }
            .validate()
            .is_err()
        );
        assert!(Rules::default().validate().is_ok());
    }
}
