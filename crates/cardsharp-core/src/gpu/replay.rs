//! Host-side f64 replay of the money flow and statistics for GPU rounds.
//!
//! The kernel plays the cards and reports one packed u32 outcome word per
//! (round, seat); this module re-executes every monetary operation of
//! round.rs in the same f64 expressions and the same per-seat program
//! order, then feeds `SimStats::record_round` per round exactly as
//! `sim::run_shard` does. Per-seat order matters because some payout
//! expressions (e.g. `bet * (1.0 + blackjack_payout)` with a 6:5 payout)
//! are not exactly representable, making later additions on that seat's
//! money order-sensitive; operations on different seats never touch the
//! same accumulator, so seat-vs-seat interleaving is free.
//!
//! Record word layout (must match kernel.wgsl):
//!   bits 0..2   bet-ramp multiplier index (counting only)
//!   bit  3      insurance taken
//!   bit  4      player blackjack flag (as the engine sets it)
//!   bits 5..7   number of hands (1..=4)
//!   bit  8      dealer blackjack
//!   bits 10+5h  per hand h: winner(2) | doubled(1) | surrendered(1) | split(1)

use crate::rules::Rules;
use crate::stats::SimStats;

/// Counting bet ramp, mirroring `Counter::bet_amount`.
const MULTS: [f64; 5] = [1.0, 4.0, 8.0, 12.0, 20.0];

const W_PLAYER: u32 = 0;
const W_DEALER: u32 = 1;
const W_DRAW: u32 = 2;

pub(crate) struct RoundReplayer<'a> {
    pub rules: &'a Rules,
    pub n_players: usize,
    pub initial_bankroll: f64,
    pub counting: bool,
}

impl RoundReplayer<'_> {
    /// Replay one round from its per-seat record words, updating `stats`
    /// exactly as `sim::accumulate` would have from the CPU round.
    pub fn replay_round(&self, stats: &mut SimStats, words: &[u32]) {
        debug_assert_eq!(words.len(), self.n_players);
        let peek = self.rules.dealer_peek;
        let dealer_bj = (words[0] >> 8) & 1 == 1;

        let mut round_net = 0.0f64;
        let mut round_initial = 0.0f64;
        let mut round_total = 0.0f64;
        let mut wins = 0u64;
        let mut losses = 0u64;
        let mut draws = 0u64;

        for &word in words {
            let mult = (word & 7) as usize;
            let insured = (word >> 3) & 1 == 1;
            let blackjack = (word >> 4) & 1 == 1;
            let n_hands = (((word >> 5) & 7) as usize).clamp(1, 4);
            let mut winners = [0u32; 4];
            let mut doubled = [false; 4];
            let mut surrendered = [false; 4];
            let mut split = [false; 4];
            for h in 0..n_hands {
                let hb = word >> (10 + 5 * h);
                winners[h] = hb & 3;
                doubled[h] = (hb >> 2) & 1 == 1;
                surrendered[h] = (hb >> 3) & 1 == 1;
                split[h] = (hb >> 4) & 1 == 1;
            }

            // PlacingBetsState: TableDecider::bet.
            let bet = if self.counting {
                (self.rules.min_bet * MULTS[mult])
                    .min(self.rules.max_bet)
                    .min(self.initial_bankroll)
            } else {
                self.rules.min_bet
            };
            let mut money = self.initial_bankroll - bet;
            let initial_bets = bet;
            let mut total_bets = bet;
            let mut bets = [0.0f64; 4];
            let mut original_bets = [0.0f64; 4];
            bets[0] = bet;
            original_bets[0] = bet;

            // OfferInsuranceState: buy_insurance(bets[0] / 2).
            let mut insurance = 0.0f64;
            if insured {
                insurance = bets[0] / 2.0;
                money -= insurance;
                total_bets += insurance;
            }

            // Play-phase exact operations (split posts, double posts,
            // surrender refunds -- early and late alike). All stay on the
            // eighth-unit lattice, so grouping them per hand is
            // bit-equivalent to the engine's interleaved order.
            for h in 0..n_hands {
                if h > 0 {
                    bets[h] = bet;
                    original_bets[h] = bet;
                    money -= bet;
                    total_bets += bet;
                }
                if doubled[h] {
                    money -= bets[h];
                    total_bets += bets[h];
                    bets[h] *= 2.0;
                }
                if surrendered[h] {
                    let refund = bets[h] / 2.0;
                    money += refund;
                    bets[h] = 0.0;
                }
            }

            if peek && dealer_bj {
                // handle_dealer_blackjack: insurance pays, naturals push.
                if insurance > 0.0 {
                    let total = insurance * (1.0 + self.rules.insurance_payout);
                    money += total;
                    insurance = 0.0;
                }
                if !surrendered[0] && winners[0] == W_DRAW {
                    money += bets[0];
                    bets[0] = 0.0;
                }
            } else if peek {
                // Peek confirmed no dealer blackjack: insurance is lost
                // (already debited); naturals are paid immediately with
                // the play_round expression `bet + bet * payout`.
                insurance = 0.0;
                if blackjack {
                    let amount = bets[0] + bets[0] * self.rules.blackjack_payout;
                    money += amount;
                    bets[0] = 0.0;
                }
            }

            // resolve_no_peek_insurance (before handle_payouts).
            if !peek && insurance > 0.0 {
                if dealer_bj {
                    let payout = insurance * (1.0 + self.rules.insurance_payout);
                    money += payout;
                }
                insurance = 0.0;
            }
            let _ = insurance;

            // handle_payouts: void late surrenders against a revealed
            // no-peek dealer blackjack (early surrender, decided before
            // the check, holds).
            if !peek && dealer_bj && !self.rules.allow_early_surrender {
                for h in 0..n_hands {
                    if surrendered[h] && original_bets[h] > 0.0 {
                        let original = original_bets[h];
                        let half = original / 2.0;
                        money -= half;
                        bets[h] = original;
                        winners[h] = W_DEALER;
                    }
                }
            }

            // handle_payouts: the per-hand settlement.
            for h in 0..n_hands {
                let bet_h = bets[h];
                if bet_h == 0.0 {
                    continue;
                }
                let is_blackjack = blackjack && !split[h];
                match winners[h] {
                    W_PLAYER => {
                        let amount = if is_blackjack {
                            bet_h * (1.0 + self.rules.blackjack_payout)
                        } else {
                            bet_h * 2.0
                        };
                        money += amount;
                        bets[h] = 0.0;
                    }
                    W_DRAW => {
                        money += bet_h;
                        bets[h] = 0.0;
                    }
                    _ => {}
                }
            }

            // OBO: exposure capped at the initial wager under a no-peek
            // dealer blackjack.
            if !peek && dealer_bj && self.rules.allow_obo {
                let losing_total: f64 = (0..n_hands)
                    .filter(|h| winners[*h] == W_DEALER)
                    .map(|h| bets[h])
                    .sum();
                if losing_total > initial_bets {
                    let refund = losing_total - initial_bets;
                    money += refund;
                }
            }

            // sim::accumulate inputs, folded in seat order.
            round_net += money - self.initial_bankroll;
            round_initial += initial_bets;
            round_total += total_bets;
            for winner in winners.iter().take(n_hands) {
                match *winner {
                    W_PLAYER => wins += 1,
                    W_DEALER => losses += 1,
                    _ => draws += 1,
                }
            }
        }

        // SimStats::count_round + record_round, exactly as accumulate does.
        stats.games_played += 1;
        stats.player_wins += wins;
        stats.dealer_wins += losses;
        stats.draws += draws;
        if round_initial > 0.0 {
            stats.record_round(round_net, round_initial, round_total);
        }
    }
}
