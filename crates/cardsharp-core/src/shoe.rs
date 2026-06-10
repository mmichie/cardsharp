//! Deal sources: the simulated multi-deck shoe and the injected card
//! stream used for parity testing.
//!
//! `Shoe` mirrors `cardsharp.common.shoe.Shoe` in non-CSM, perfect-shuffle
//! mode: the round-aware cut-card contract (`begin_round`/`end_round`), the
//! between-rounds shuffle, burn cards, and the mid-round
//! reshuffle-discards-only emergency path. CSM and realistic shuffles are
//! deliberately out of scope here (beads-9ro.8).

use crate::card::Rank;
use rand::seq::SliceRandom;
use rand_xoshiro::Xoshiro256PlusPlus;
use std::fmt;

/// The deal source ran out of cards. For a `Shoe` this is only possible
/// when every card is on the table mid-round; for a `CardStream` it simply
/// means the injected sequence is exhausted.
#[derive(Debug, Clone, Copy)]
pub struct OutOfCards;

impl fmt::Display for OutOfCards {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "deal source exhausted")
    }
}

impl std::error::Error for OutOfCards {}

pub trait DealSource {
    /// Open a round. The cut card never interrupts an open round; if it
    /// came out during the previous round the shuffle happens here.
    fn begin_round(&mut self);
    fn end_round(&mut self);
    fn deal(&mut self) -> Result<Rank, OutOfCards>;
    /// Cards left to deal, mirroring `Shoe.cards_remaining` (the counting
    /// integration derives decks_remaining and reshuffle detection from
    /// this, so the formula must match the Python shoe's).
    fn cards_remaining(&self) -> usize;
}

pub struct Shoe {
    cards: Vec<Rank>,
    next: usize,
    round_start: usize,
    in_round: bool,
    cut_card_reached: bool,
    reshuffle_point: usize,
    total_cards: usize,
    burn_cards: usize,
    rng: Xoshiro256PlusPlus,
    /// Cumulative shuffle count (test support: shuffle timing depends only
    /// on consumption counts, so the parity suite compares these epochs
    /// against the Python shoe without any RNG coupling).
    pub shuffles: u64,
    /// Cumulative count of mid-round discard reshuffles (test support).
    pub mid_round_reshuffles: u64,
}

impl Shoe {
    pub fn new(num_decks: u32, penetration: f64, burn_cards: u32, rng: Xoshiro256PlusPlus) -> Self {
        let mut cards = Vec::with_capacity(52 * num_decks as usize);
        for _ in 0..num_decks {
            for _ in 0..4 {
                cards.extend_from_slice(&Rank::ALL);
            }
        }
        let total_cards = cards.len();
        let mut shoe = Shoe {
            cards,
            next: 0,
            round_start: 0,
            in_round: false,
            cut_card_reached: false,
            reshuffle_point: (total_cards as f64 * penetration) as usize,
            total_cards,
            burn_cards: burn_cards as usize,
            rng,
            shuffles: 0,
            mid_round_reshuffles: 0,
        };
        shoe.shuffle();
        shoe
    }

    /// Zero the test-support counters (so traces exclude the construction
    /// shuffle, matching how the Python harness counts).
    pub fn reset_counters(&mut self) {
        self.shuffles = 0;
        self.mid_round_reshuffles = 0;
    }

    fn shuffle(&mut self) {
        self.shuffles += 1;
        self.cards.shuffle(&mut self.rng);
        self.next = 0;
        self.round_start = 0;
        self.cut_card_reached = false;
        if self.burn_cards > 0 {
            let to_burn = self.burn_cards.min(self.cards.len());
            self.next += to_burn;
            self.round_start = self.next;
        }
    }

    /// Casino procedure when the shoe physically runs out mid-round: cards
    /// on the table stay on the table; the discards (everything not dealt
    /// during the current round) are reshuffled and dealing continues.
    fn reshuffle_discards_mid_round(&mut self) -> Result<(), OutOfCards> {
        self.mid_round_reshuffles += 1;
        let in_play: Vec<Rank> = self.cards[self.round_start..self.next].to_vec();
        let mut pool: Vec<Rank> = Vec::with_capacity(self.cards.len() - in_play.len());
        pool.extend_from_slice(&self.cards[..self.round_start]);
        pool.extend_from_slice(&self.cards[self.next..]);
        if pool.is_empty() {
            return Err(OutOfCards);
        }
        pool.shuffle(&mut self.rng);
        self.next = in_play.len();
        self.round_start = 0;
        self.cut_card_reached = false;
        let mut cards = in_play;
        cards.extend_from_slice(&pool);
        self.cards = cards;
        Ok(())
    }
}

impl DealSource for Shoe {
    fn begin_round(&mut self) {
        if self.cut_card_reached || self.next >= self.reshuffle_point {
            self.shuffle();
        }
        self.in_round = true;
        self.round_start = self.next;
    }

    fn end_round(&mut self) {
        self.in_round = false;
    }

    fn deal(&mut self) -> Result<Rank, OutOfCards> {
        if self.in_round {
            if self.next >= self.cards.len() {
                self.reshuffle_discards_mid_round()?;
            }
        } else if self.next >= self.reshuffle_point || self.next >= self.total_cards {
            // Legacy path for callers that do not bracket rounds; kept for
            // exact behavioral parity with the Python shoe.
            self.cut_card_reached = true;
            self.shuffle();
        }
        let card = self.cards[self.next];
        self.next += 1;
        if self.next >= self.reshuffle_point {
            self.cut_card_reached = true;
        }
        Ok(card)
    }

    fn cards_remaining(&self) -> usize {
        self.total_cards.saturating_sub(self.next)
    }
}

/// A fixed card sequence injected from Python for parity testing. Never
/// shuffles; dealing past the end reports `OutOfCards` so the caller can
/// discard the incomplete round.
pub struct CardStream {
    cards: Vec<Rank>,
    next: usize,
}

impl CardStream {
    pub fn new(cards: Vec<Rank>) -> Self {
        CardStream { cards, next: 0 }
    }

    pub fn consumed(&self) -> usize {
        self.next
    }
}

impl DealSource for CardStream {
    fn begin_round(&mut self) {}

    fn end_round(&mut self) {}

    fn deal(&mut self) -> Result<Rank, OutOfCards> {
        let card = self.cards.get(self.next).copied().ok_or(OutOfCards)?;
        self.next += 1;
        Ok(card)
    }

    fn cards_remaining(&self) -> usize {
        self.cards.len() - self.next
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::SeedableRng;

    fn shoe(num_decks: u32, penetration: f64) -> Shoe {
        Shoe::new(
            num_decks,
            penetration,
            0,
            Xoshiro256PlusPlus::seed_from_u64(7),
        )
    }

    #[test]
    fn shoe_contains_full_composition() {
        let s = shoe(6, 0.75);
        assert_eq!(s.cards.len(), 312);
        let aces = s.cards.iter().filter(|r| **r == Rank::Ace).count();
        assert_eq!(aces, 24);
    }

    #[test]
    fn cut_card_does_not_interrupt_a_round() {
        let mut s = shoe(1, 0.5);
        s.begin_round();
        // Deal through the cut card within one round: no shuffle may occur,
        // so all 52 cards remain dealable in order.
        let mut seen = Vec::new();
        for _ in 0..40 {
            seen.push(s.deal().unwrap());
        }
        assert!(s.cut_card_reached);
        assert_eq!(seen.len(), 40);
        s.end_round();
        // Next round begins with a shuffle.
        s.begin_round();
        assert_eq!(s.next, 0);
        assert!(!s.cut_card_reached);
    }

    #[test]
    fn mid_round_exhaustion_reshuffles_discards_only() {
        let mut s = shoe(1, 1.0);
        s.begin_round();
        for _ in 0..50 {
            s.deal().unwrap();
        }
        s.end_round();
        // 2 cards remain; the next round needs more than that.
        s.begin_round();
        for _ in 0..10 {
            s.deal().unwrap();
        }
        // The round survived by recycling discards; cards dealt this round
        // were preserved at the front.
        assert_eq!(s.round_start, 0);
        assert!(s.next >= 10);
    }

    #[test]
    fn stream_reports_exhaustion() {
        let mut stream = CardStream::new(vec![Rank::Ace, Rank::King]);
        assert!(stream.deal().is_ok());
        assert!(stream.deal().is_ok());
        assert!(stream.deal().is_err());
        assert_eq!(stream.consumed(), 2);
    }
}
