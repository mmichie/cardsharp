//! Deal sources: the simulated multi-deck shoe and the injected card
//! stream used for parity testing.
//!
//! `Shoe` mirrors `cardsharp.common.shoe.Shoe`: the round-aware cut-card
//! contract (`begin_round`/`end_round`), the between-rounds shuffle, burn
//! cards, the mid-round reshuffle-discards-only emergency path, the CSM
//! (continuous shuffling machine) mode, and the realistic shuffle
//! procedures (GSR riffle, strip). Shuffle realism and CSM card selection
//! are RNG-bound, so they are validated statistically and by mechanical
//! invariants rather than by cross-engine stream parity.

use crate::card::Rank;
use rand::Rng;
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
    /// Exact rank composition of the cards left to deal, in Rank::ALL
    /// order. Conditional settlement draws the dealer's outcome
    /// distribution from this.
    fn remaining_rank_counts(&self) -> [u32; 13];
}

/// Shuffle procedure, mirroring `Shoe.shuffle_type`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ShuffleStyle {
    /// Fisher-Yates: cryptographically fair ordering.
    Perfect,
    /// Gilbert-Shannon-Reeds riffle: binomial cut, proportional interleave.
    Riffle,
    /// Strip shuffle (running cut): 3-15 card packets restacked on top.
    Strip,
}

impl ShuffleStyle {
    pub fn from_name(name: &str) -> Result<Self, String> {
        match name {
            "perfect" => Ok(ShuffleStyle::Perfect),
            "riffle" => Ok(ShuffleStyle::Riffle),
            "strip" => Ok(ShuffleStyle::Strip),
            other => Err(format!(
                "shuffle_type must be 'perfect', 'riffle', or 'strip', got '{other}'"
            )),
        }
    }

    /// Default pass count per shuffle, mirroring the Python defaults
    /// (one perfect pass; four dealer riffles; six strips).
    fn default_count(self) -> u32 {
        match self {
            ShuffleStyle::Perfect => 1,
            ShuffleStyle::Riffle => 4,
            ShuffleStyle::Strip => 6,
        }
    }
}

#[derive(Debug, Clone)]
pub struct ShoeOptions {
    pub num_decks: u32,
    pub penetration: f64,
    pub burn_cards: u32,
    pub use_csm: bool,
    pub shuffle_style: ShuffleStyle,
    pub shuffle_count: Option<u32>,
}

impl ShoeOptions {
    /// Standard cut-card shoe with a perfect shuffle.
    pub fn classic(num_decks: u32, penetration: f64, burn_cards: u32) -> Self {
        ShoeOptions {
            num_decks,
            penetration,
            burn_cards,
            use_csm: false,
            shuffle_style: ShuffleStyle::Perfect,
            shuffle_count: None,
        }
    }
}

/// One GSR (Gilbert-Shannon-Reeds) riffle pass, mirroring
/// `Shoe._gsr_riffle_shuffle`: the cut point is Binomial(n, 1/2) and
/// cards drop from each half with probability proportional to the
/// half's remaining size.
fn gsr_riffle(cards: Vec<Rank>, rng: &mut Xoshiro256PlusPlus) -> Vec<Rank> {
    let n = cards.len();
    if n <= 1 {
        return cards;
    }
    let mut cut_point = 0usize;
    for _ in 0..n {
        if rng.random::<f64>() < 0.5 {
            cut_point += 1;
        }
    }
    let (left, right) = cards.split_at(cut_point);
    let mut result = Vec::with_capacity(n);
    let (mut li, mut ri) = (0usize, 0usize);
    while li < left.len() || ri < right.len() {
        let left_remaining = left.len() - li;
        let right_remaining = right.len() - ri;
        if left_remaining == 0 {
            result.extend_from_slice(&right[ri..]);
            break;
        }
        if right_remaining == 0 {
            result.extend_from_slice(&left[li..]);
            break;
        }
        let p_left = left_remaining as f64 / (left_remaining + right_remaining) as f64;
        if rng.random::<f64>() < p_left {
            result.push(left[li]);
            li += 1;
        } else {
            result.push(right[ri]);
            ri += 1;
        }
    }
    result
}

/// One strip-shuffle pass, mirroring `Shoe._strip_shuffle`: packets of
/// 3-15 cards are taken from the top and dropped on top of the result.
fn strip_shuffle(cards: Vec<Rank>, rng: &mut Xoshiro256PlusPlus) -> Vec<Rank> {
    let n = cards.len();
    if n <= 1 {
        return cards;
    }
    let mut result: Vec<Rank> = Vec::with_capacity(n);
    let mut taken = 0usize;
    while taken < n {
        let packet_size = (rng.random_range(3..=15usize)).min(n - taken);
        // Drop the packet on top of the result (prepend).
        result.splice(0..0, cards[taken..taken + packet_size].iter().copied());
        taken += packet_size;
    }
    result
}

pub struct Shoe {
    cards: Vec<Rank>,
    /// Used cards awaiting return to the machine (CSM mode only).
    discards: Vec<Rank>,
    next: usize,
    round_start: usize,
    in_round: bool,
    cut_card_reached: bool,
    reshuffle_point: usize,
    total_cards: usize,
    options: ShoeOptions,
    shuffle_passes: u32,
    rng: Xoshiro256PlusPlus,
    /// Cumulative shuffle count (test support: shuffle timing depends only
    /// on consumption counts, so the parity suite compares these epochs
    /// against the Python shoe without any RNG coupling).
    pub shuffles: u64,
    /// Cumulative count of mid-round discard reshuffles (test support).
    pub mid_round_reshuffles: u64,
}

impl Shoe {
    pub fn new(options: ShoeOptions, rng: Xoshiro256PlusPlus) -> Self {
        let mut cards = Vec::with_capacity(52 * options.num_decks as usize);
        for _ in 0..options.num_decks {
            for _ in 0..4 {
                cards.extend_from_slice(&Rank::ALL);
            }
        }
        let total_cards = cards.len();
        let shuffle_passes = options
            .shuffle_count
            .unwrap_or_else(|| options.shuffle_style.default_count());
        let mut shoe = Shoe {
            cards,
            discards: Vec::new(),
            next: 0,
            round_start: 0,
            in_round: false,
            cut_card_reached: false,
            reshuffle_point: (total_cards as f64 * options.penetration) as usize,
            total_cards,
            options,
            shuffle_passes,
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

    /// Apply the configured shuffle procedure, mirroring `_shuffle_cards`.
    fn run_shuffle_procedure(&mut self) {
        match self.options.shuffle_style {
            ShuffleStyle::Perfect => self.cards.shuffle(&mut self.rng),
            ShuffleStyle::Riffle => {
                for _ in 0..self.shuffle_passes {
                    let cards = std::mem::take(&mut self.cards);
                    self.cards = gsr_riffle(cards, &mut self.rng);
                }
            }
            ShuffleStyle::Strip => {
                for _ in 0..self.shuffle_passes {
                    let cards = std::mem::take(&mut self.cards);
                    self.cards = strip_shuffle(cards, &mut self.rng);
                }
            }
        }
    }

    fn shuffle(&mut self) {
        self.shuffles += 1;
        if self.options.use_csm && !self.discards.is_empty() {
            self.cards.append(&mut self.discards);
        }
        self.run_shuffle_procedure();
        self.next = 0;
        self.round_start = 0;
        self.cut_card_reached = false;
        if self.options.burn_cards > 0 && !self.options.use_csm {
            let to_burn = (self.options.burn_cards as usize).min(self.cards.len());
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
        // The pool is reshuffled with the configured procedure, as
        // `_reshuffle_discards_mid_round` delegates to `_shuffle_cards`.
        self.cards = pool;
        self.run_shuffle_procedure();
        let pool = std::mem::take(&mut self.cards);
        self.next = in_play.len();
        self.round_start = 0;
        self.cut_card_reached = false;
        let mut cards = in_play;
        cards.extend_from_slice(&pool);
        self.cards = cards;
        Ok(())
    }

    /// CSM single-card deal, mirroring the Python CSM fast path: uniform
    /// pick, swap-remove, immediate discard, and the partial refill when
    /// the machine runs low (which uses a PERFECT shuffle regardless of
    /// shuffle style, as the reference does).
    fn deal_csm(&mut self) -> Result<Rank, OutOfCards> {
        let mut cards_len = self.cards.len();
        if cards_len < 1 {
            if self.discards.is_empty() {
                return Err(OutOfCards);
            }
            self.cards.append(&mut self.discards);
            self.cards.shuffle(&mut self.rng);
            cards_len = self.cards.len();
        }

        let card_index = self.rng.random_range(0..cards_len);
        let card = self.cards[card_index];
        self.cards[card_index] = self.cards[cards_len - 1];
        self.cards.pop();
        self.discards.push(card);

        // Refill check uses the PRE-deal length, as the reference does.
        if (cards_len as f64) < self.total_cards as f64 * 0.2
            && (self.discards.len() as f64) > self.total_cards as f64 * 0.4
        {
            let num_to_return = self.discards.len() / 2;
            let returned: Vec<Rank> = self.discards.drain(..num_to_return).collect();
            self.cards.extend_from_slice(&returned);
            self.cards.shuffle(&mut self.rng);
        }

        Ok(card)
    }
}

impl DealSource for Shoe {
    fn begin_round(&mut self) {
        if !self.options.use_csm && (self.cut_card_reached || self.next >= self.reshuffle_point) {
            self.shuffle();
        }
        self.in_round = true;
        self.round_start = self.next;
    }

    fn end_round(&mut self) {
        self.in_round = false;
    }

    fn deal(&mut self) -> Result<Rank, OutOfCards> {
        if self.options.use_csm {
            return self.deal_csm();
        }
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
        if self.options.use_csm {
            self.cards.len()
        } else {
            self.total_cards.saturating_sub(self.next)
        }
    }

    fn remaining_rank_counts(&self) -> [u32; 13] {
        let mut counts = [0u32; 13];
        let undealt = if self.options.use_csm {
            &self.cards[..]
        } else {
            &self.cards[self.next..]
        };
        for card in undealt {
            counts[(card.code() - 1) as usize] += 1;
        }
        counts
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

    fn remaining_rank_counts(&self) -> [u32; 13] {
        let mut counts = [0u32; 13];
        for card in &self.cards[self.next..] {
            counts[(card.code() - 1) as usize] += 1;
        }
        counts
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::SeedableRng;
    use std::collections::HashMap;

    fn shoe(num_decks: u32, penetration: f64) -> Shoe {
        Shoe::new(
            ShoeOptions::classic(num_decks, penetration, 0),
            Xoshiro256PlusPlus::seed_from_u64(7),
        )
    }

    fn rank_counts(cards: &[Rank]) -> HashMap<u8, usize> {
        let mut counts = HashMap::new();
        for card in cards {
            *counts.entry(card.code()).or_insert(0) += 1;
        }
        counts
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
        let mut seen = Vec::new();
        for _ in 0..40 {
            seen.push(s.deal().unwrap());
        }
        assert!(s.cut_card_reached);
        assert_eq!(seen.len(), 40);
        s.end_round();
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
        s.begin_round();
        for _ in 0..10 {
            s.deal().unwrap();
        }
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

    #[test]
    fn riffle_and_strip_preserve_the_composition() {
        for style in [ShuffleStyle::Riffle, ShuffleStyle::Strip] {
            let mut options = ShoeOptions::classic(2, 0.75, 0);
            options.shuffle_style = style;
            let s = Shoe::new(options, Xoshiro256PlusPlus::seed_from_u64(11));
            assert_eq!(s.cards.len(), 104);
            let counts = rank_counts(&s.cards);
            assert!(counts.values().all(|&n| n == 8), "{style:?} lost cards");
        }
    }

    #[test]
    fn shuffles_are_deterministic_per_seed() {
        for style in [
            ShuffleStyle::Perfect,
            ShuffleStyle::Riffle,
            ShuffleStyle::Strip,
        ] {
            let mut options = ShoeOptions::classic(1, 0.9, 0);
            options.shuffle_style = style;
            let a = Shoe::new(options.clone(), Xoshiro256PlusPlus::seed_from_u64(3));
            let b = Shoe::new(options, Xoshiro256PlusPlus::seed_from_u64(3));
            assert_eq!(a.cards, b.cards);
        }
    }

    #[test]
    fn csm_conserves_the_composition_across_heavy_dealing() {
        let mut options = ShoeOptions::classic(2, 0.75, 0);
        options.use_csm = true;
        let mut s = Shoe::new(options, Xoshiro256PlusPlus::seed_from_u64(5));
        let mut dealt_high = 0usize;
        for _ in 0..5_000 {
            s.begin_round();
            for _ in 0..6 {
                if s.deal().unwrap().bj_value() >= 10 {
                    dealt_high += 1;
                }
            }
            s.end_round();
        }
        // Machine + discards always hold the full two decks.
        let mut all: Vec<Rank> = s.cards.clone();
        all.extend_from_slice(&s.discards);
        assert_eq!(all.len(), 104);
        let counts = rank_counts(&all);
        assert!(counts.values().all(|&n| n == 8));
        // Sanity: ten-class frequency over 30k cards is near 5/13.
        let high_rate = dealt_high as f64 / 30_000.0;
        assert!((high_rate - 5.0 / 13.0).abs() < 0.02, "rate {high_rate}");
    }

    #[test]
    fn csm_never_shuffles_at_round_boundaries() {
        let mut options = ShoeOptions::classic(1, 0.1, 0);
        options.use_csm = true;
        let mut s = Shoe::new(options, Xoshiro256PlusPlus::seed_from_u64(9));
        s.reset_counters();
        for _ in 0..50 {
            s.begin_round();
            for _ in 0..5 {
                s.deal().unwrap();
            }
            s.end_round();
        }
        assert_eq!(s.shuffles, 0); // refills are inline, not shuffle() calls
        assert!(!s.cut_card_reached);
    }
}
