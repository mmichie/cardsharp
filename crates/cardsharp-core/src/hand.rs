//! A blackjack hand, mirroring `cardsharp.blackjack.hand.BlackjackHand`.

use crate::card::Rank;

#[derive(Debug, Clone)]
pub struct Hand {
    ranks: Vec<Rank>,
    is_split: bool,
}

impl Hand {
    pub fn new() -> Self {
        Hand {
            ranks: Vec::with_capacity(4),
            is_split: false,
        }
    }

    pub fn add(&mut self, rank: Rank) {
        self.ranks.push(rank);
    }

    /// Remove the last card (used only when splitting a pair).
    pub fn pop(&mut self) -> Option<Rank> {
        self.ranks.pop()
    }

    pub fn len(&self) -> usize {
        self.ranks.len()
    }

    pub fn is_empty(&self) -> bool {
        self.ranks.is_empty()
    }

    pub fn ranks(&self) -> &[Rank] {
        &self.ranks
    }

    pub fn is_split(&self) -> bool {
        self.is_split
    }

    pub fn mark_split(&mut self) {
        self.is_split = true;
    }

    pub fn contains_ace(&self) -> bool {
        self.ranks.contains(&Rank::Ace)
    }

    fn num_aces(&self) -> u32 {
        self.ranks.iter().filter(|r| **r == Rank::Ace).count() as u32
    }

    fn non_ace_sum(&self) -> u32 {
        self.ranks
            .iter()
            .filter(|r| **r != Rank::Ace)
            .map(|r| r.bj_value())
            .sum()
    }

    /// Optimal hand value: aces start at 1 and are promoted to 11 while
    /// that keeps the total at or below 21. Mirrors `BlackjackHand.value`.
    pub fn value(&self) -> u32 {
        let num_aces = self.num_aces();
        let mut value = self.non_ace_sum() + num_aces;
        for _ in 0..num_aces {
            if value + 10 <= 21 {
                value += 10;
            } else {
                break;
            }
        }
        value
    }

    /// Soft hand: an ace is currently counted as 11. Mirrors
    /// `BlackjackHand.is_soft`.
    pub fn is_soft(&self) -> bool {
        let num_aces = self.num_aces();
        if num_aces == 0 {
            return false;
        }
        let min_value = self.non_ace_sum() + num_aces;
        let value = self.value();
        value > min_value && value <= 21
    }

    /// Natural blackjack: exactly two cards, not a split hand, an ace plus
    /// a ten-value card. Mirrors `BlackjackHand.is_blackjack`.
    pub fn is_blackjack(&self) -> bool {
        if self.ranks.len() != 2 || self.is_split {
            return false;
        }
        let has_ace = self.contains_ace();
        let has_ten = self.ranks.iter().any(|r| r.bj_value() == 10);
        has_ace && has_ten
    }

    /// Two cards of identical rank (K-K yes, K-Q no). This is the
    /// strategy-level pair test (`BlackjackHand.can_split`); whether the
    /// split is legal is a separate rules question.
    pub fn is_rank_pair(&self) -> bool {
        self.ranks.len() == 2 && self.ranks[0] == self.ranks[1]
    }
}

impl Default for Hand {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hand(ranks: &[Rank]) -> Hand {
        let mut h = Hand::new();
        for r in ranks {
            h.add(*r);
        }
        h
    }

    #[test]
    fn values() {
        assert_eq!(hand(&[Rank::Ace, Rank::King]).value(), 21);
        assert_eq!(hand(&[Rank::Ace, Rank::Ace]).value(), 12);
        assert_eq!(hand(&[Rank::Ace, Rank::Ace, Rank::Nine]).value(), 21);
        assert_eq!(hand(&[Rank::Ten, Rank::Nine, Rank::Five]).value(), 24);
        assert_eq!(hand(&[Rank::Ace, Rank::Five]).value(), 16);
    }

    #[test]
    fn softness() {
        assert!(hand(&[Rank::Ace, Rank::Six]).is_soft());
        assert!(!hand(&[Rank::Ace, Rank::Six, Rank::Ten]).is_soft());
        assert!(!hand(&[Rank::Ten, Rank::Seven]).is_soft());
    }

    #[test]
    fn blackjack_requires_natural() {
        assert!(hand(&[Rank::Ace, Rank::Queen]).is_blackjack());
        let mut split = hand(&[Rank::Ace, Rank::King]);
        split.mark_split();
        assert!(!split.is_blackjack());
        assert!(!hand(&[Rank::Ace, Rank::Five, Rank::Five]).is_blackjack());
    }

    #[test]
    fn pairs_compare_rank_not_value() {
        assert!(hand(&[Rank::King, Rank::King]).is_rank_pair());
        assert!(!hand(&[Rank::King, Rank::Queen]).is_rank_pair());
    }
}
