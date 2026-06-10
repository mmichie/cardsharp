//! Python entry points: `simulate_batch` and `play_card_stream`.

use crate::card::Rank;
use crate::round::{RoundConfig, RoundResult, play_round};
use crate::rules::Rules;
use crate::shoe::{CardStream, Shoe};
use crate::stats::SimStats;
use crate::strategy::StrategyTable;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use rand::SeedableRng;
use rand_xoshiro::Xoshiro256PlusPlus;

fn parse_table(table: &[u8]) -> PyResult<StrategyTable> {
    StrategyTable::from_bytes(table).map_err(|e| PyValueError::new_err(e.to_string()))
}

fn parse_stream(cards: &[u8]) -> PyResult<Vec<Rank>> {
    cards
        .iter()
        .map(|c| Rank::from_code(*c).map_err(|e| PyValueError::new_err(e.to_string())))
        .collect()
}

/// Simulate `n_rounds` of classic blackjack against a fresh shoe seeded
/// with `seed`. Returns a dict shaped exactly like
/// `SimulationStats.report()`, consumable by `SimulationStats.from_dict`.
#[pyfunction]
#[pyo3(signature = (rules, table, n_rounds, seed, n_players = 1, initial_bankroll = 1000.0, always_insure = false))]
#[allow(clippy::too_many_arguments)]
pub fn simulate_batch<'py>(
    py: Python<'py>,
    rules: PyRef<'py, Rules>,
    table: &[u8],
    n_rounds: u64,
    seed: u64,
    n_players: usize,
    initial_bankroll: f64,
    always_insure: bool,
) -> PyResult<Bound<'py, PyDict>> {
    if n_players < 1 {
        return Err(PyValueError::new_err("n_players must be at least 1"));
    }
    let table = parse_table(table)?;
    let rules: Rules = rules.clone();
    let cfg = RoundConfig {
        n_players,
        initial_bankroll,
        always_insure,
    };

    let rng = Xoshiro256PlusPlus::seed_from_u64(seed);
    let mut shoe = Shoe::new(rules.num_decks, rules.penetration, rules.burn_cards, rng);
    let mut stats = SimStats::new();

    for _ in 0..n_rounds {
        let result = play_round(&mut shoe, &rules, &table, &cfg)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        accumulate(&mut stats, &result);
    }

    stats.to_dict(py)
}

fn accumulate(stats: &mut SimStats, result: &RoundResult) {
    let winners: Vec<_> = result.players.iter().map(|p| p.winners.clone()).collect();
    stats.count_round(&winners);

    let net: f64 = result.players.iter().map(|p| p.net()).sum();
    let initial: f64 = result.players.iter().map(|p| p.initial_bets).sum();
    let total: f64 = result.players.iter().map(|p| p.total_bets).sum();
    if initial > 0.0 {
        stats.record_round(net, initial, total);
    }
}

/// One player's view of a completed round, for parity testing.
#[pyclass(get_all)]
#[derive(Debug, Clone)]
pub struct PlayerRecord {
    /// Final hands as rank codes (Ace=1 .. King=13), in play order.
    /// Stored as u32 so PyO3 renders them as lists of ints (Vec<u8>
    /// would convert to Python bytes).
    pub hands: Vec<Vec<u32>>,
    /// Resolved actions per hand, as `Action.value` strings -- the same
    /// thing the reference engine's `action_history` records.
    pub actions: Vec<Vec<String>>,
    /// Per-hand outcomes: "player" / "dealer" / "draw".
    pub winners: Vec<String>,
    /// Per-hand bets as they stand after payouts (paid hands are zeroed).
    pub bets: Vec<f64>,
    pub original_bets: Vec<f64>,
    pub net: f64,
    pub initial_bet: f64,
    pub total_bet: f64,
    pub blackjack: bool,
    pub money: f64,
}

#[pyclass(get_all)]
#[derive(Debug, Clone)]
pub struct RoundRecord {
    pub players: Vec<PlayerRecord>,
    /// Dealer's final hand as rank codes; index 0 is the upcard.
    pub dealer_cards: Vec<u32>,
    /// Cards consumed from the stream by this round.
    pub cards_consumed: u32,
}

/// Play rounds from a fixed injected card sequence (no shuffling, ever)
/// and return a full record of every completed round. Stops cleanly when
/// the stream cannot finish another round; the partial round is discarded.
///
/// The parity suite feeds the same sequence to the Python engine via a
/// pre-loaded `Shoe` and asserts the records match.
#[pyfunction]
#[pyo3(signature = (rules, table, cards, n_players = 1, initial_bankroll = 1000.0, always_insure = false, max_rounds = None))]
pub fn play_card_stream(
    rules: PyRef<'_, Rules>,
    table: &[u8],
    cards: Vec<u8>,
    n_players: usize,
    initial_bankroll: f64,
    always_insure: bool,
    max_rounds: Option<u64>,
) -> PyResult<Vec<RoundRecord>> {
    if n_players < 1 {
        return Err(PyValueError::new_err("n_players must be at least 1"));
    }
    let table = parse_table(table)?;
    let rules: Rules = rules.clone();
    let cfg = RoundConfig {
        n_players,
        initial_bankroll,
        always_insure,
    };

    let mut stream = CardStream::new(parse_stream(&cards)?);
    let mut records = Vec::new();

    loop {
        if let Some(max) = max_rounds
            && records.len() as u64 >= max
        {
            break;
        }
        let before = stream.consumed();
        match play_round(&mut stream, &rules, &table, &cfg) {
            Ok(result) => {
                let consumed = (stream.consumed() - before) as u32;
                records.push(make_record(result, consumed));
            }
            Err(_) => break, // stream exhausted mid-round: discard partial
        }
    }
    Ok(records)
}

/// Test support for the parity suite: drive a shoe through rounds of fixed
/// consumption and report when shuffles happen.
///
/// Shuffle timing depends only on card COUNTS (penetration crossings and
/// exhaustion), never on card values, so these epochs are directly
/// comparable with the Python shoe's despite the different RNGs. Returns,
/// per round, the cumulative (shuffles_before_dealing, mid_round_reshuffles
/// _after_dealing) counters; the construction shuffle is excluded.
#[pyfunction]
#[pyo3(signature = (num_decks, penetration, burn_cards, deals_per_round, seed = 0))]
pub fn trace_shoe(
    num_decks: u32,
    penetration: f64,
    burn_cards: u32,
    deals_per_round: Vec<u32>,
    seed: u64,
) -> PyResult<Vec<(u64, u64)>> {
    use crate::shoe::DealSource;

    let rng = Xoshiro256PlusPlus::seed_from_u64(seed);
    let mut shoe = Shoe::new(num_decks, penetration, burn_cards, rng);
    shoe.reset_counters();

    let mut trace = Vec::with_capacity(deals_per_round.len());
    for deals in deals_per_round {
        shoe.begin_round();
        let shuffles_before = shoe.shuffles;
        for _ in 0..deals {
            shoe.deal()
                .map_err(|e| PyValueError::new_err(e.to_string()))?;
        }
        shoe.end_round();
        trace.push((shuffles_before, shoe.mid_round_reshuffles));
    }
    Ok(trace)
}

fn make_record(result: RoundResult, cards_consumed: u32) -> RoundRecord {
    let players = result
        .players
        .iter()
        .map(|p| PlayerRecord {
            hands: p
                .hands
                .iter()
                .map(|h| h.ranks().iter().map(|r| r.code() as u32).collect())
                .collect(),
            actions: p
                .action_history
                .iter()
                .map(|hist| hist.iter().map(|a| a.as_str().to_string()).collect())
                .collect(),
            winners: p.winners.iter().map(|w| w.as_str().to_string()).collect(),
            bets: p.bets.clone(),
            original_bets: p.original_bets.clone(),
            net: p.net(),
            initial_bet: p.initial_bets,
            total_bet: p.total_bets,
            blackjack: p.blackjack,
            money: p.money,
        })
        .collect();

    RoundRecord {
        players,
        dealer_cards: result
            .dealer
            .ranks()
            .iter()
            .map(|r| r.code() as u32)
            .collect(),
        cards_consumed,
    }
}
