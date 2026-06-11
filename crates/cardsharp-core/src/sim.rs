//! Python entry points: `simulate_batch` and `play_card_stream`.

use crate::card::Rank;
use crate::counting::{Counter, CountingConfig};
use crate::round::{RoundConfig, RoundResult, play_round};
use crate::rules::Rules;
use crate::shoe::{CardStream, DealSource, Shoe, ShoeOptions, ShuffleStyle};
use crate::stats::SimStats;
use crate::strategy::StrategyTable;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use rand::SeedableRng;
use rand_xoshiro::Xoshiro256PlusPlus;
use rayon::prelude::*;

fn parse_table(table: &[u8]) -> PyResult<StrategyTable> {
    StrategyTable::from_bytes(table).map_err(|e| PyValueError::new_err(e.to_string()))
}

fn parse_stream(cards: &[u8]) -> PyResult<Vec<Rank>> {
    cards
        .iter()
        .map(|c| Rank::from_code(*c).map_err(|e| PyValueError::new_err(e.to_string())))
        .collect()
}

/// Rounds per shard. Each shard runs against its own freshly shuffled
/// shoe with a seed derived deterministically from the master seed, so a
/// batch's result is a pure function of (seed, n_rounds, config) -- the
/// thread count cannot change it. The fresh-shoe boundary every
/// SHARD_ROUNDS matches what multiprocess Python workers already did.
const SHARD_ROUNDS: u64 = 250_000;

/// SplitMix64: stable, explicit derivation of per-shard seeds from the
/// master seed (independent of any RNG crate internals).
fn splitmix64(state: &mut u64) -> u64 {
    *state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

/// Per-deal accumulator for the EV diagnostic: X = net / initial_bet
/// bucketed by the round's deal state (c1, c2, upcard) in solver card
/// values (Ace=1, ten-classes collapsed to 10). A flat 10x10x10 grid
/// indexed by ((lo-1)*10 + (hi-1))*10 + (up-1); only lo <= hi cells
/// ever populate. The Python side subtracts the solver's per-deal EV
/// from these raw X moments (the deal EV is a constant per cell, so
/// the d = X - Y moments derive exactly from the X moments).
#[derive(Clone)]
pub struct PerDealTable {
    cells: Vec<(u64, f64, f64)>, // (n, sum_x, sum_x2)
}

impl PerDealTable {
    fn new() -> Self {
        PerDealTable {
            cells: vec![(0, 0.0, 0.0); 1000],
        }
    }

    fn solver_value(rank: Rank) -> usize {
        (rank.code() as usize).min(10)
    }

    fn record(&mut self, c1: Rank, c2: Rank, up: Rank, x: f64) {
        let a = Self::solver_value(c1);
        let b = Self::solver_value(c2);
        let (lo, hi) = if a <= b { (a, b) } else { (b, a) };
        let up = Self::solver_value(up);
        let cell = &mut self.cells[((lo - 1) * 10 + (hi - 1)) * 10 + (up - 1)];
        cell.0 += 1;
        cell.1 += x;
        cell.2 += x * x;
    }

    /// Element-wise fold in shard order: float sums stay deterministic
    /// regardless of thread count, like SimStats::merge.
    fn merge(&mut self, other: &PerDealTable) {
        for (a, b) in self.cells.iter_mut().zip(&other.cells) {
            a.0 += b.0;
            a.1 += b.1;
            a.2 += b.2;
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn run_shard(
    rules: &Rules,
    table: &StrategyTable,
    cfg: &RoundConfig,
    counting: Option<&CountingConfig>,
    shoe_options: &ShoeOptions,
    rounds: u64,
    shard_seed: u64,
    per_deal: bool,
) -> Result<(SimStats, Option<PerDealTable>), crate::shoe::OutOfCards> {
    let rng = Xoshiro256PlusPlus::seed_from_u64(shard_seed);
    let mut shoe = Shoe::new(shoe_options.clone(), rng);
    let mut stats = SimStats::new();
    let mut deals = per_deal.then(PerDealTable::new);
    // The count is per-shard, matching the per-worker count of the old
    // multiprocess Python runs (each shard starts a fresh shoe anyway).
    let mut counter = counting.map(|c| Counter::new(c.clone()));
    for _ in 0..rounds {
        let remaining_before = shoe.cards_remaining();
        let result = play_round(&mut shoe, rules, table, cfg, counter.as_mut())?;
        if let Some(c) = counter.as_mut() {
            c.finish_round(remaining_before, shoe.cards_remaining());
        }
        accumulate(&mut stats, &result);
        if let Some(d) = deals.as_mut() {
            // per_deal requires n_players == 1, so the round net (or its
            // Rao-Blackwellized version) IS player 0's net.
            let player = &result.players[0];
            let x = result.conditional_net.unwrap_or_else(|| player.net()) / player.initial_bets;
            let (c1, c2) = result.first_cards[0];
            d.record(c1, c2, result.dealer.ranks()[0], x);
        }
    }
    Ok((stats, deals))
}

/// Simulate `n_rounds` of classic blackjack, sharded across threads.
/// Returns a dict shaped exactly like `SimulationStats.report()`,
/// consumable by `SimulationStats.from_dict`.
///
/// `threads` = 0 uses all available cores; any value yields bit-identical
/// results for a given seed (shards are self-contained and merged in
/// shard order). The GIL is released for the duration of the simulation.
///
/// With `per_deal=true` (single player only), the report additionally
/// carries a "per_deal" list of 1000 `(n, sum_x, sum_x2)` cells, X =
/// net/initial_bet bucketed by (c1, c2, upcard) in solver card values,
/// indexed `((lo-1)*10 + (hi-1))*10 + (up-1)` -- the raw material of the
/// per-deal EV diagnostic (cardsharp/tools/deal_ev_diagnostic.py).
#[pyfunction]
#[pyo3(signature = (rules, table, n_rounds, seed, n_players = 1, initial_bankroll = 1000.0, always_insure = false, threads = 0, counting = None, shuffle_type = "perfect", shuffle_count = None, conditional_settlement = false, per_deal = false))]
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
    threads: usize,
    counting: Option<PyRef<'py, CountingConfig>>,
    shuffle_type: &str,
    shuffle_count: Option<u32>,
    conditional_settlement: bool,
    per_deal: bool,
) -> PyResult<Bound<'py, PyDict>> {
    if n_players < 1 {
        return Err(PyValueError::new_err("n_players must be at least 1"));
    }
    if per_deal && n_players != 1 {
        return Err(PyValueError::new_err(
            "per_deal requires n_players=1: the deal key is a single \
             player's first two cards plus the dealer upcard",
        ));
    }
    if conditional_settlement && (!rules.dealer_peek || rules.use_csm) {
        return Err(PyValueError::new_err(
            "conditional_settlement requires dealer_peek=true and a non-CSM shoe \
             (see settle.rs scope notes)",
        ));
    }
    let table = parse_table(table)?;
    let rules: Rules = rules.clone();
    let counting: Option<CountingConfig> = counting.map(|c| c.clone());
    let shoe_options = ShoeOptions {
        num_decks: rules.num_decks,
        penetration: rules.penetration,
        burn_cards: rules.burn_cards,
        use_csm: rules.use_csm,
        shuffle_style: ShuffleStyle::from_name(shuffle_type).map_err(PyValueError::new_err)?,
        shuffle_count,
    };
    let cfg = RoundConfig {
        n_players,
        initial_bankroll,
        always_insure,
        conditional_settlement,
    };

    // Fixed-size shards with explicitly derived seeds: the shard layout
    // depends only on (seed, n_rounds), never on the thread count.
    let mut seed_state = seed;
    let n_shards = n_rounds.div_ceil(SHARD_ROUNDS).max(1);
    let shards: Vec<(u64, u64)> = (0..n_shards)
        .map(|i| {
            let rounds = if i == n_shards - 1 {
                n_rounds - i * SHARD_ROUNDS
            } else {
                SHARD_ROUNDS
            };
            (rounds, splitmix64(&mut seed_state))
        })
        .collect();

    type ShardOut = (SimStats, Option<PerDealTable>);
    let (stats, deals) = py
        .detach(|| -> Result<ShardOut, crate::shoe::OutOfCards> {
            let run_all = || -> Result<Vec<ShardOut>, crate::shoe::OutOfCards> {
                shards
                    .par_iter()
                    .map(|(rounds, shard_seed)| {
                        run_shard(
                            &rules,
                            &table,
                            &cfg,
                            counting.as_ref(),
                            &shoe_options,
                            *rounds,
                            *shard_seed,
                            per_deal,
                        )
                    })
                    .collect()
            };
            let shard_stats = if threads == 0 {
                run_all()?
            } else {
                rayon::ThreadPoolBuilder::new()
                    .num_threads(threads)
                    .build()
                    .expect("failed to build thread pool")
                    .install(run_all)?
            };
            // Deterministic ordered fold (par_iter + collect preserves
            // shard order).
            let mut total = SimStats::new();
            let mut total_deals = per_deal.then(PerDealTable::new);
            for (s, d) in &shard_stats {
                total.merge(s);
                if let (Some(td), Some(d)) = (total_deals.as_mut(), d.as_ref()) {
                    td.merge(d);
                }
            }
            Ok((total, total_deals))
        })
        .map_err(|e| PyValueError::new_err(e.to_string()))?;

    let out = stats.to_dict(py)?;
    if let Some(d) = deals {
        out.set_item("per_deal", d.cells)?;
    }
    Ok(out)
}

fn accumulate(stats: &mut SimStats, result: &RoundResult) {
    let winners: Vec<_> = result.players.iter().map(|p| p.winners.clone()).collect();
    stats.count_round(&winners);

    // Win/loss/draw counts above stay REALIZED; the financial estimator
    // uses the Rao-Blackwellized net when conditional settlement is on.
    let net: f64 = result
        .conditional_net
        .unwrap_or_else(|| result.players.iter().map(|p| p.net()).sum());
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
    /// The first two cards as dealt (rank codes), before any split or
    /// hit reshapes the hands -- the player's half of the deal key.
    pub first_cards: Vec<u32>,
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
    /// Rao-Blackwellized round net when conditional settlement is on.
    pub conditional_net: Option<f64>,
}

/// Play rounds from a fixed injected card sequence (no shuffling, ever)
/// and return a full record of every completed round. Stops cleanly when
/// the stream cannot finish another round; the partial round is discarded.
///
/// The parity suite feeds the same sequence to the Python engine via a
/// pre-loaded `Shoe` and asserts the records match.
#[pyfunction]
#[pyo3(signature = (rules, table, cards, n_players = 1, initial_bankroll = 1000.0, always_insure = false, max_rounds = None, counting = None, conditional_settlement = false))]
#[allow(clippy::too_many_arguments)]
pub fn play_card_stream(
    rules: PyRef<'_, Rules>,
    table: &[u8],
    cards: Vec<u8>,
    n_players: usize,
    initial_bankroll: f64,
    always_insure: bool,
    max_rounds: Option<u64>,
    counting: Option<PyRef<'_, CountingConfig>>,
    conditional_settlement: bool,
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
        conditional_settlement,
    };

    let mut stream = CardStream::new(parse_stream(&cards)?);
    let mut counter = counting.map(|c| Counter::new(c.clone()));
    let mut records = Vec::new();

    loop {
        if let Some(max) = max_rounds
            && records.len() as u64 >= max
        {
            break;
        }
        let before = stream.consumed();
        let remaining_before = stream.cards_remaining();
        match play_round(&mut stream, &rules, &table, &cfg, counter.as_mut()) {
            Ok(result) => {
                if let Some(c) = counter.as_mut() {
                    c.finish_round(remaining_before, stream.cards_remaining());
                }
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
    let rng = Xoshiro256PlusPlus::seed_from_u64(seed);
    let mut shoe = Shoe::new(
        ShoeOptions::classic(num_decks, penetration, burn_cards),
        rng,
    );
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
        .enumerate()
        .map(|(i, p)| PlayerRecord {
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
            first_cards: {
                let (a, b) = result.first_cards[i];
                vec![a.code() as u32, b.code() as u32]
            },
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
        conditional_net: result.conditional_net,
    }
}

/// Paired-difference accumulator across two rule variants played on
/// common random numbers, mirroring `cardsharp.blackjack.comparison`.
#[derive(Default, Clone)]
struct PairedStats {
    a: SimStats,
    b: SimStats,
    diff_n: u64,
    diff_mean: f64,
    diff_m2: f64,
}

impl PairedStats {
    fn record_diff(&mut self, diff: f64) {
        self.diff_n += 1;
        let delta = diff - self.diff_mean;
        self.diff_mean += delta / self.diff_n as f64;
        self.diff_m2 += delta * (diff - self.diff_mean);
    }

    /// Chan merge in shard order, keeping results thread-count invariant.
    fn merge(&mut self, other: &PairedStats) {
        self.a.merge(&other.a);
        self.b.merge(&other.b);
        let n_a = self.diff_n;
        let n_b = other.diff_n;
        if n_b == 0 {
            return;
        }
        if n_a == 0 {
            self.diff_n = other.diff_n;
            self.diff_mean = other.diff_mean;
            self.diff_m2 = other.diff_m2;
            return;
        }
        let n = n_a + n_b;
        let (fa, fb, fn_) = (n_a as f64, n_b as f64, n as f64);
        let d = other.diff_mean - self.diff_mean;
        self.diff_m2 = self.diff_m2 + other.diff_m2 + d * d * fa * fb / fn_;
        self.diff_mean += d * fb / fn_;
        self.diff_n = n;
    }
}

#[allow(clippy::too_many_arguments)]
fn run_paired_shard(
    rules_a: &Rules,
    table_a: &StrategyTable,
    rules_b: &Rules,
    table_b: &StrategyTable,
    cfg: &RoundConfig,
    rounds: u64,
    shard_seed: u64,
) -> Result<PairedStats, crate::shoe::OutOfCards> {
    let mut stats = PairedStats::default();
    let mut seed_state = shard_seed;

    for _ in 0..rounds {
        // One seed per round: both variants shuffle identical decks, so
        // they see the same deal and the same hit cards until their rules
        // make play diverge -- the CRN guarantee from comparison.py.
        let round_seed = splitmix64(&mut seed_state);
        let mut round_he = [0.0f64; 2];
        for (slot, (rules, table)) in [(rules_a, table_a), (rules_b, table_b)]
            .into_iter()
            .enumerate()
        {
            let rng = Xoshiro256PlusPlus::seed_from_u64(round_seed);
            let mut shoe = Shoe::new(
                ShoeOptions::classic(rules.num_decks, rules.penetration, rules.burn_cards),
                rng,
            );
            let result = play_round(&mut shoe, rules, table, cfg, None)?;
            let net: f64 = result
                .conditional_net
                .unwrap_or_else(|| result.players.iter().map(|p| p.net()).sum());
            let initial: f64 = result.players.iter().map(|p| p.initial_bets).sum();
            let total: f64 = result.players.iter().map(|p| p.total_bets).sum();
            let side = if slot == 0 {
                &mut stats.a
            } else {
                &mut stats.b
            };
            let winners: Vec<_> = result.players.iter().map(|p| p.winners.clone()).collect();
            side.count_round(&winners);
            if initial > 0.0 {
                side.record_round(net, initial, total);
            }
            round_he[slot] = if initial > 0.0 { -net / initial } else { 0.0 };
        }
        stats.record_diff(round_he[0] - round_he[1]);
    }
    Ok(stats)
}

/// Compare two rule variants with Common Random Numbers at core speed:
/// every round, both variants play against identically shuffled decks,
/// so the variance of (HE_A - HE_B) reflects only rule divergence, not
/// shuffle noise. Mirrors `cardsharp.blackjack.comparison.compare_rules`
/// (per-round fresh shoes; counting is unsupported because per-round
/// resets destroy the count). Returns per-variant report dicts plus the
/// paired-difference Welford state, all thread-count invariant.
#[pyfunction]
#[pyo3(signature = (rules_a, table_a, rules_b, table_b, n_rounds, seed, n_players = 1, initial_bankroll = 10_000_000.0, threads = 0, conditional_settlement = false))]
#[allow(clippy::too_many_arguments)]
pub fn simulate_paired<'py>(
    py: Python<'py>,
    rules_a: PyRef<'py, Rules>,
    table_a: &[u8],
    rules_b: PyRef<'py, Rules>,
    table_b: &[u8],
    n_rounds: u64,
    seed: u64,
    n_players: usize,
    initial_bankroll: f64,
    threads: usize,
    conditional_settlement: bool,
) -> PyResult<Bound<'py, PyDict>> {
    if n_players < 1 {
        return Err(PyValueError::new_err("n_players must be at least 1"));
    }
    let rules_a: Rules = rules_a.clone();
    let rules_b: Rules = rules_b.clone();
    if conditional_settlement
        && (!rules_a.dealer_peek || !rules_b.dealer_peek || rules_a.use_csm || rules_b.use_csm)
    {
        return Err(PyValueError::new_err(
            "conditional_settlement requires dealer_peek=true and non-CSM shoes \
             for both variants",
        ));
    }
    let table_a = parse_table(table_a)?;
    let table_b = parse_table(table_b)?;
    let cfg = RoundConfig {
        n_players,
        initial_bankroll,
        always_insure: false,
        conditional_settlement,
    };

    let mut seed_state = seed;
    let n_shards = n_rounds.div_ceil(SHARD_ROUNDS).max(1);
    let shards: Vec<(u64, u64)> = (0..n_shards)
        .map(|i| {
            let rounds = if i == n_shards - 1 {
                n_rounds - i * SHARD_ROUNDS
            } else {
                SHARD_ROUNDS
            };
            (rounds, splitmix64(&mut seed_state))
        })
        .collect();

    let stats = py
        .detach(|| -> Result<PairedStats, crate::shoe::OutOfCards> {
            let run_all = || -> Result<Vec<PairedStats>, crate::shoe::OutOfCards> {
                shards
                    .par_iter()
                    .map(|(rounds, shard_seed)| {
                        run_paired_shard(
                            &rules_a,
                            &table_a,
                            &rules_b,
                            &table_b,
                            &cfg,
                            *rounds,
                            *shard_seed,
                        )
                    })
                    .collect()
            };
            let shard_stats = if threads == 0 {
                run_all()?
            } else {
                rayon::ThreadPoolBuilder::new()
                    .num_threads(threads)
                    .build()
                    .expect("failed to build thread pool")
                    .install(run_all)?
            };
            let mut total = PairedStats::default();
            for s in &shard_stats {
                total.merge(s);
            }
            Ok(total)
        })
        .map_err(|e| PyValueError::new_err(e.to_string()))?;

    let out = PyDict::new(py);
    out.set_item("a", stats.a.to_dict(py)?)?;
    out.set_item("b", stats.b.to_dict(py)?)?;
    out.set_item("diff_n", stats.diff_n)?;
    out.set_item("diff_mean", stats.diff_mean)?;
    out.set_item("diff_M2", stats.diff_m2)?;
    Ok(out)
}
