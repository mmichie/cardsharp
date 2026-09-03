//! Card ranks.
//!
//! Suits never affect outcomes in classic blackjack (the bonus-payout code
//! in the Python engine is unreachable when the classic variant supplies a
//! payout calculator), so the core tracks ranks only. Rank codes match
//! `cardsharp.common.card.Rank` values (Ace=1 .. King=13) so card streams
//! cross the boundary without translation.

use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Rank {
    Ace,
    Two,
    Three,
    Four,
    Five,
    Six,
    Seven,
    Eight,
    Nine,
    Ten,
    Jack,
    Queen,
    King,
}

impl Rank {
    /// Decode from the Python `Rank.value` (1..=13). Jokers (0) are not
    /// part of any blackjack deck and are rejected.
    pub fn from_code(code: u8) -> Result<Self, InvalidRank> {
        Ok(match code {
            1 => Rank::Ace,
            2 => Rank::Two,
            3 => Rank::Three,
            4 => Rank::Four,
            5 => Rank::Five,
            6 => Rank::Six,
            7 => Rank::Seven,
            8 => Rank::Eight,
            9 => Rank::Nine,
            10 => Rank::Ten,
            11 => Rank::Jack,
            12 => Rank::Queen,
            13 => Rank::King,
            other => return Err(InvalidRank(other)),
        })
    }

    pub fn code(self) -> u8 {
        match self {
            Rank::Ace => 1,
            Rank::Two => 2,
            Rank::Three => 3,
            Rank::Four => 4,
            Rank::Five => 5,
            Rank::Six => 6,
            Rank::Seven => 7,
            Rank::Eight => 8,
            Rank::Nine => 9,
            Rank::Ten => 10,
            Rank::Jack => 11,
            Rank::Queen => 12,
            Rank::King => 13,
        }
    }

    /// Blackjack value with aces counted high (the hand decides ace
    /// demotion). Matches `Card.bj_value` in the Python engine.
    pub fn bj_value(self) -> u32 {
        match self {
            Rank::Ace => 11,
            Rank::Two => 2,
            Rank::Three => 3,
            Rank::Four => 4,
            Rank::Five => 5,
            Rank::Six => 6,
            Rank::Seven => 7,
            Rank::Eight => 8,
            Rank::Nine => 9,
            Rank::Ten | Rank::Jack | Rank::Queen | Rank::King => 10,
        }
    }

    /// All thirteen ranks, one suit's worth.
    pub const ALL: [Rank; 13] = [
        Rank::Ace,
        Rank::Two,
        Rank::Three,
        Rank::Four,
        Rank::Five,
        Rank::Six,
        Rank::Seven,
        Rank::Eight,
        Rank::Nine,
        Rank::Ten,
        Rank::Jack,
        Rank::Queen,
        Rank::King,
    ];
}

#[derive(Debug, Clone, Copy)]
pub struct InvalidRank(pub u8);

impl fmt::Display for InvalidRank {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "invalid rank code {} (expected 1..=13)", self.0)
    }
}

impl std::error::Error for InvalidRank {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codes_round_trip() {
        for code in 1..=13u8 {
            assert_eq!(Rank::from_code(code).unwrap().code(), code);
        }
        assert!(Rank::from_code(0).is_err());
        assert!(Rank::from_code(14).is_err());
    }

    #[test]
    fn ten_cards_share_value() {
        for rank in [Rank::Ten, Rank::Jack, Rank::Queen, Rank::King] {
            assert_eq!(rank.bj_value(), 10);
        }
        assert_eq!(Rank::Ace.bj_value(), 11);
    }
}
