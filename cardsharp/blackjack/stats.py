"""
This module contains the SimulationStats class which is responsible for
tracking and updating the statistics of the blackjack game simulation.

It accumulates per-round outcomes via Welford's online algorithm so that
sample mean, variance, and a delta-method confidence interval for the
house edge can be reported without storing every round in memory. The
accumulator is mergeable (Chan's parallel formula), making it safe to
combine results from multiprocessing workers.
"""

import math
from statistics import NormalDist


class SimulationStats:
    """
    Holds win/loss counts and Welford accumulators for per-round
    financial outcomes.

    Two parallel views are maintained:
      - Aggregate sums (net_sum, bet_sum, total_bet_sum) for the
        existing "house edge over total action" metric.
      - Welford state (n_rounds, net_mean, net_M2, bet_mean, bet_M2,
        net_bet_C) for sample variance and a delta-method CI on
        -E[net]/E[initial_bet].
    """

    def __init__(self):
        # Win/loss counts (per hand resolution; splits produce >1 outcome)
        self.games_played = 0
        self.player_wins = 0
        self.dealer_wins = 0
        self.draws = 0

        # Welford state, per round (one initial deal -> resolution)
        self.n_rounds = 0
        self.net_mean = 0.0
        self.net_M2 = 0.0
        self.bet_mean = 0.0
        self.bet_M2 = 0.0
        self.net_bet_C = 0.0

        # Aggregate financial sums
        self.net_sum = 0.0
        self.bet_sum = 0.0
        self.total_bet_sum = 0.0

    def update(self, game):
        """Updates the statistics based on the current state of the game."""
        self.games_played += 1

        game.io_interface.output("Updating statistics...")
        for player in game.players:
            for winner in player.winner:
                if winner == "player":
                    self.player_wins += 1
                elif winner == "dealer":
                    self.dealer_wins += 1
                elif winner == "draw":
                    self.draws += 1

        # Reset the winners for next game
        for player in game.players:
            player.winner = []

    def record_round(self, net, initial_bet, total_bet):
        """Record one round's financial outcome.

        Updates Welford state for net and initial_bet and the co-moment
        between them; also accumulates aggregate sums.
        """
        self.n_rounds += 1
        n = self.n_rounds
        dx = net - self.net_mean
        dy = initial_bet - self.bet_mean
        self.net_mean += dx / n
        self.bet_mean += dy / n
        # M2 update uses post-update means
        self.net_M2 += dx * (net - self.net_mean)
        self.bet_M2 += dy * (initial_bet - self.bet_mean)
        # Co-moment update (Welford-style, post-update y mean)
        self.net_bet_C += dx * (initial_bet - self.bet_mean)
        # Aggregate sums (independent path, exact integer-ish arithmetic)
        self.net_sum += net
        self.bet_sum += initial_bet
        self.total_bet_sum += total_bet

    def merge(self, other):
        """Merge another SimulationStats into self (Chan parallel Welford)."""
        # Win/loss counts
        self.games_played += other.games_played
        self.player_wins += other.player_wins
        self.dealer_wins += other.dealer_wins
        self.draws += other.draws

        # Welford merge
        n_a = self.n_rounds
        n_b = other.n_rounds
        n = n_a + n_b
        if n_b > 0:
            if n_a == 0:
                self.n_rounds = other.n_rounds
                self.net_mean = other.net_mean
                self.bet_mean = other.bet_mean
                self.net_M2 = other.net_M2
                self.bet_M2 = other.bet_M2
                self.net_bet_C = other.net_bet_C
            else:
                d_net = other.net_mean - self.net_mean
                d_bet = other.bet_mean - self.bet_mean
                self.net_M2 = (
                    self.net_M2 + other.net_M2 + d_net * d_net * n_a * n_b / n
                )
                self.bet_M2 = (
                    self.bet_M2 + other.bet_M2 + d_bet * d_bet * n_a * n_b / n
                )
                self.net_bet_C = (
                    self.net_bet_C + other.net_bet_C
                    + d_net * d_bet * n_a * n_b / n
                )
                self.net_mean = self.net_mean + d_net * n_b / n
                self.bet_mean = self.bet_mean + d_bet * n_b / n
                self.n_rounds = n

        # Aggregate sums
        self.net_sum += other.net_sum
        self.bet_sum += other.bet_sum
        self.total_bet_sum += other.total_bet_sum

    def report(self):
        """Returns a dictionary containing the current statistics."""
        return {
            "games_played": self.games_played,
            "player_wins": self.player_wins,
            "dealer_wins": self.dealer_wins,
            "draws": self.draws,
            "n_rounds": self.n_rounds,
            "net_mean": self.net_mean,
            "net_M2": self.net_M2,
            "bet_mean": self.bet_mean,
            "bet_M2": self.bet_M2,
            "net_bet_C": self.net_bet_C,
            "net_sum": self.net_sum,
            "bet_sum": self.bet_sum,
            "total_bet_sum": self.total_bet_sum,
        }

    @classmethod
    def from_dict(cls, d):
        """Reconstruct a SimulationStats from a report() dict."""
        s = cls()
        s.games_played = d.get("games_played", 0)
        s.player_wins = d.get("player_wins", 0)
        s.dealer_wins = d.get("dealer_wins", 0)
        s.draws = d.get("draws", 0)
        s.n_rounds = d.get("n_rounds", 0)
        s.net_mean = d.get("net_mean", 0.0)
        s.net_M2 = d.get("net_M2", 0.0)
        s.bet_mean = d.get("bet_mean", 0.0)
        s.bet_M2 = d.get("bet_M2", 0.0)
        s.net_bet_C = d.get("net_bet_C", 0.0)
        s.net_sum = d.get("net_sum", 0.0)
        s.bet_sum = d.get("bet_sum", 0.0)
        s.total_bet_sum = d.get("total_bet_sum", 0.0)
        return s

    def house_edge_with_ci(self, confidence=0.95):
        """House edge with a delta-method CI on -E[net]/E[initial_bet].

        Returns a tuple (he, ci_low, ci_high, half_width) all expressed
        as fractions (multiply by 100 for percentage), or None if
        insufficient data (n<2 or zero mean bet).

        The delta method approximates Var(X̄/Ȳ) using a first-order
        Taylor expansion; for the typical case where bets are nearly
        constant the bet-variance and covariance terms are tiny and
        the result reduces to Var(net)/n divided by mean_bet^2.
        """
        n = self.n_rounds
        if n < 2 or self.bet_mean == 0:
            return None

        var_net = self.net_M2 / (n - 1)
        var_bet = self.bet_M2 / (n - 1)
        cov_nb = self.net_bet_C / (n - 1)
        mu_net = self.net_mean
        mu_bet = self.bet_mean

        he = -mu_net / mu_bet
        var_he = (
            var_net / (mu_bet * mu_bet)
            + (mu_net * mu_net) * var_bet / (mu_bet ** 4)
            - 2.0 * mu_net * cov_nb / (mu_bet ** 3)
        ) / n
        se = math.sqrt(max(0.0, var_he))
        z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
        half = z * se
        return he, he - half, he + half, half

    def per_round_ev_with_ci(self, confidence=0.95):
        """Mean net change per round with a normal-approximation CI.

        Returns (mean_net, ci_low, ci_high, half_width) in dollar units,
        or None if n<2.
        """
        n = self.n_rounds
        if n < 2:
            return None
        var_net = self.net_M2 / (n - 1)
        se = math.sqrt(var_net / n)
        z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
        half = z * se
        return self.net_mean, self.net_mean - half, self.net_mean + half, half

    def win_rate_with_ci(self, confidence=0.95):
        """Player win rate (excluding pushes) with a Wilson score CI.

        Note: treats hand resolutions as iid Bernoulli draws. Split hands
        share a dealer outcome and so are mildly correlated; the
        resulting CI is a slight under-estimate of true variance. For
        precise statistical claims prefer house_edge_with_ci, which
        operates on per-round outcomes.
        """
        n = self.player_wins + self.dealer_wins
        if n == 0:
            return None
        p = self.player_wins / n
        z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
        denom = 1.0 + z * z / n
        center = (p + z * z / (2.0 * n)) / denom
        half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
        return p, center - half, center + half, half
