//! Aggregate statistics, mirroring `cardsharp.blackjack.stats.SimulationStats`.
//!
//! The Welford updates replicate `record_round` operation-for-operation in
//! f64, so a batch aggregated here is bit-compatible with one aggregated by
//! the Python class given identical per-round inputs. `to_dict` emits the
//! exact `report()` key set, ready for `SimulationStats.from_dict`.

use crate::round::Winner;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyDict;

#[derive(Debug, Default, Clone)]
pub struct SimStats {
    pub games_played: u64,
    pub player_wins: u64,
    pub dealer_wins: u64,
    pub draws: u64,
    pub n_rounds: u64,
    pub net_mean: f64,
    pub net_m2: f64,
    pub bet_mean: f64,
    pub bet_m2: f64,
    pub net_bet_c: f64,
    pub net_sum: f64,
    pub bet_sum: f64,
    pub total_bet_sum: f64,
}

impl SimStats {
    pub fn new() -> Self {
        Self::default()
    }

    /// Mirrors `SimulationStats.update`: one game per round, one tally per
    /// resolved hand (split hands produce multiple tallies; surrendered
    /// hands are tallied by the same hand-value comparison the reference
    /// engine applies).
    pub fn count_round(&mut self, winners_per_player: &[Vec<Winner>]) {
        self.games_played += 1;
        for winners in winners_per_player {
            for winner in winners {
                match winner {
                    Winner::Player => self.player_wins += 1,
                    Winner::Dealer => self.dealer_wins += 1,
                    Winner::Draw => self.draws += 1,
                }
            }
        }
    }

    /// Mirrors `SimulationStats.merge` (Chan parallel Welford), used to
    /// fold per-shard stats in deterministic shard order so results are
    /// identical regardless of thread count.
    pub fn merge(&mut self, other: &SimStats) {
        self.games_played += other.games_played;
        self.player_wins += other.player_wins;
        self.dealer_wins += other.dealer_wins;
        self.draws += other.draws;

        let n_a = self.n_rounds;
        let n_b = other.n_rounds;
        let n = n_a + n_b;
        if n_b > 0 {
            if n_a == 0 {
                self.n_rounds = other.n_rounds;
                self.net_mean = other.net_mean;
                self.bet_mean = other.bet_mean;
                self.net_m2 = other.net_m2;
                self.bet_m2 = other.bet_m2;
                self.net_bet_c = other.net_bet_c;
            } else {
                let (n_a, n_b, n) = (n_a as f64, n_b as f64, n as f64);
                let d_net = other.net_mean - self.net_mean;
                let d_bet = other.bet_mean - self.bet_mean;
                self.net_m2 = self.net_m2 + other.net_m2 + d_net * d_net * n_a * n_b / n;
                self.bet_m2 = self.bet_m2 + other.bet_m2 + d_bet * d_bet * n_a * n_b / n;
                self.net_bet_c = self.net_bet_c + other.net_bet_c + d_net * d_bet * n_a * n_b / n;
                self.net_mean += d_net * n_b / n;
                self.bet_mean += d_bet * n_b / n;
                self.n_rounds += other.n_rounds;
            }
        }

        self.net_sum += other.net_sum;
        self.bet_sum += other.bet_sum;
        self.total_bet_sum += other.total_bet_sum;
    }

    /// Mirrors `SimulationStats.record_round` (no control variate).
    pub fn record_round(&mut self, net: f64, initial_bet: f64, total_bet: f64) {
        self.n_rounds += 1;
        let n = self.n_rounds as f64;
        let dx = net - self.net_mean;
        let dy = initial_bet - self.bet_mean;
        self.net_mean += dx / n;
        self.bet_mean += dy / n;
        // M2 updates use post-update means, as in the reference.
        self.net_m2 += dx * (net - self.net_mean);
        self.bet_m2 += dy * (initial_bet - self.bet_mean);
        self.net_bet_c += dx * (initial_bet - self.bet_mean);
        self.net_sum += net;
        self.bet_sum += initial_bet;
        self.total_bet_sum += total_bet;
    }

    /// Emit the exact `SimulationStats.report()` dictionary shape. The
    /// control-variate fields are zero/None: the CV estimator stays on the
    /// Python side.
    #[cfg(feature = "python")]
    pub fn to_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        d.set_item("games_played", self.games_played)?;
        d.set_item("player_wins", self.player_wins)?;
        d.set_item("dealer_wins", self.dealer_wins)?;
        d.set_item("draws", self.draws)?;
        d.set_item("n_rounds", self.n_rounds)?;
        d.set_item("net_mean", self.net_mean)?;
        d.set_item("net_M2", self.net_m2)?;
        d.set_item("bet_mean", self.bet_mean)?;
        d.set_item("bet_M2", self.bet_m2)?;
        d.set_item("net_bet_C", self.net_bet_c)?;
        d.set_item("net_sum", self.net_sum)?;
        d.set_item("bet_sum", self.bet_sum)?;
        d.set_item("total_bet_sum", self.total_bet_sum)?;
        d.set_item("cv_n", 0u64)?;
        d.set_item("cv_x_mean", 0.0f64)?;
        d.set_item("cv_x_M2", 0.0f64)?;
        d.set_item("cv_y_mean", 0.0f64)?;
        d.set_item("cv_y_M2", 0.0f64)?;
        d.set_item("cv_xy_C", 0.0f64)?;
        d.set_item("cv_mu_y", py.None())?;
        Ok(d)
    }
}
