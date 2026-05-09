"""Statistical validation of house edge against the solver's exact value.

Two layers of validation:

1. Point-estimate convergence (TestHouseEdge): runs a large simulation with
   the solver's optimal strategy and asserts the measured edge falls within
   4 standard errors of solve(rules).house_edge. Pulling the expected value
   from the solver -- rather than a hard-coded published number -- makes
   the tests robust to rule-set tweaks and catches simulator bugs whose
   magnitude is below published precision.

2. CI calibration (TestCICalibration, slow): runs K independent simulations
   of the same rule set with different seeds and counts how often the
   reported 95% CI from house_edge_with_ci contains the solver's exact HE.
   Under correct CI math, ~95% of the CIs should cover the truth. The test
   asserts coverage is within a binomial-acceptance window wide enough to
   avoid sampling-noise flakes but narrow enough to detect gross
   miscalibration of the delta-method variance formula.
"""

import logging
import math
import random

import pytest

from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.solver import solve
from cardsharp.blackjack.state import _state_placing_bets
from cardsharp.blackjack.stats import SimulationStats
from cardsharp.blackjack.strategy import BasicStrategy, SolverStrategy
from cardsharp.common.io_interface import DummyIOInterface


# Suppress per-decision debug logging so simulations run at full speed.
# The simulator binary does the same thing in --simulate mode; tests need
# the same so a calibration sweep finishes in seconds rather than minutes.
logging.disable(logging.CRITICAL)


# Module-scoped solver cache. solve() takes ~8s per rule set; tests reuse
# results across multiple test methods.
_solver_cache: dict = {}


def _cache_key(rules):
    return (
        rules.num_decks,
        rules.dealer_hit_soft_17,
        rules.blackjack_payout,
        rules.allow_double_down,
        rules.allow_split,
        rules.allow_double_after_split,
        rules.allow_resplitting,
        rules.allow_surrender,
        rules.allow_late_surrender,
        rules.allow_early_surrender,
        rules.dealer_peek,
        rules.max_splits,
        rules.resplit_aces,
    )


def _cached_solver(rules):
    key = _cache_key(rules)
    if key not in _solver_cache:
        _solver_cache[key] = solve(rules)
    return _solver_cache[key]


def _make_game(rules, strategy):
    io = DummyIOInterface()
    game = BlackjackGame(rules, io)
    player = Player("Sim", io, strategy, initial_money=10_000_000)
    game.add_player(player)
    game.set_state(_state_placing_bets)
    return game, player


def _simulate(rules, num_rounds, seed=42, strategy=None):
    """Run num_rounds and return (house_edge, std_err).

    Defaults to SolverStrategy so the simulator plays the rule-aware
    optimal table. With BasicStrategy passed in, the simulator plays the
    rule-blind CSV table -- useful for relative-ordering tests where the
    same strategy is used on both sides of the comparison.
    """
    random.seed(seed)
    if strategy is None:
        strategy = SolverStrategy(_cached_solver(rules))

    game, player = _make_game(rules, strategy)

    results = []
    for _ in range(num_rounds):
        money_before = player.money
        game.play_round()
        money_after = player.money
        net = money_after - money_before
        wager = player.initial_bets if player.initial_bets > 0 else rules.min_bet
        results.append(net / wager)
        game.reset()

    mean = sum(results) / len(results)
    variance = sum((r - mean) ** 2 for r in results) / (len(results) - 1)
    std_err = math.sqrt(variance / len(results))
    return -mean, std_err


def _simulate_stats(rules, num_rounds, seed, strategy):
    """Run num_rounds and return a populated SimulationStats.

    Returning the same accumulator type the production simulator uses lets
    the calibration test exercise the *real* delta-method CI from
    SimulationStats.house_edge_with_ci -- not a re-derivation -- so a bug
    in that formula will surface here.
    """
    random.seed(seed)
    game, player = _make_game(rules, strategy)

    stats = SimulationStats()
    for _ in range(num_rounds):
        money_before = player.money
        game.play_round()
        money_after = player.money
        net = money_after - money_before
        wager = player.initial_bets if player.initial_bets > 0 else rules.min_bet
        stats.record_round(net, wager, wager)
        game.reset()
    return stats


def _rules_h17():
    return Rules(
        num_decks=6,
        dealer_hit_soft_17=True,
        allow_double_down=True,
        allow_split=True,
        allow_surrender=True,
        allow_late_surrender=True,
        allow_double_after_split=False,
        allow_resplitting=False,
        dealer_peek=True,
        blackjack_payout=1.5,
        penetration=0.75,
    )


def _rules_s17():
    return Rules(
        num_decks=6,
        dealer_hit_soft_17=False,
        allow_double_down=True,
        allow_split=True,
        allow_surrender=True,
        allow_late_surrender=True,
        allow_double_after_split=False,
        allow_resplitting=False,
        dealer_peek=True,
        blackjack_payout=1.5,
        penetration=0.75,
    )


class TestHouseEdge:
    """Validate simulated HE against the solver's exact HE.

    Each test asserts the measured edge is within 4 standard errors of
    solve(rules).house_edge. The solver is the ground truth for the rule
    set; a 4-sigma bound gives ~99.99% confidence against false failures
    while still catching simulator bugs that shift the edge by 0.1% or more.
    """

    NUM_ROUNDS = 200_000

    def test_six_deck_h17(self):
        """6-deck H17, no DAS, late surrender."""
        rules = _rules_h17()
        edge, se = _simulate(rules, self.NUM_ROUNDS)
        expected = _cached_solver(rules).house_edge
        tolerance = max(4 * se, 0.001)
        assert abs(edge - expected) < tolerance, (
            f"6-deck H17 edge {edge:.4%} (SE={se:.4%}) outside "
            f"solver {expected:.4%} +/- {tolerance:.4%}"
        )

    def test_six_deck_s17(self):
        """6-deck S17, no DAS, late surrender."""
        rules = _rules_s17()
        edge, se = _simulate(rules, self.NUM_ROUNDS)
        expected = _cached_solver(rules).house_edge
        tolerance = max(4 * se, 0.001)
        assert abs(edge - expected) < tolerance, (
            f"6-deck S17 edge {edge:.4%} (SE={se:.4%}) outside "
            f"solver {expected:.4%} +/- {tolerance:.4%}"
        )

    def test_s17_lower_than_h17(self):
        """S17 should have a lower house edge than H17 (same rules otherwise).

        Relative ordering -- doesn't depend on exact numbers. Uses
        BasicStrategy so the strategy is identical on both sides; only the
        rule difference moves the edge.
        """
        h17_edge, _ = _simulate(
            _rules_h17(), 100_000, seed=99, strategy=BasicStrategy()
        )
        s17_edge, _ = _simulate(
            _rules_s17(), 100_000, seed=99, strategy=BasicStrategy()
        )
        assert s17_edge < h17_edge, (
            f"S17 edge ({s17_edge:.4%}) should be lower than "
            f"H17 edge ({h17_edge:.4%})"
        )

    def test_6_to_5_worse_than_3_to_2(self):
        """6:5 blackjack payout should produce a higher house edge than 3:2.

        The 6:5 payout adds ~1.4% to the house edge -- one of the largest
        single-rule effects. Easy to detect even with moderate sample size.
        """
        base = dict(
            num_decks=6,
            dealer_hit_soft_17=True,
            allow_double_down=True,
            allow_split=True,
            allow_surrender=True,
            allow_late_surrender=True,
            dealer_peek=True,
            penetration=0.75,
        )

        edge_3_2, _ = _simulate(
            Rules(blackjack_payout=1.5, **base),
            100_000,
            seed=77,
            strategy=BasicStrategy(),
        )
        edge_6_5, _ = _simulate(
            Rules(blackjack_payout=1.2, **base),
            100_000,
            seed=77,
            strategy=BasicStrategy(),
        )

        assert edge_6_5 > edge_3_2 + 0.005, (
            f"6:5 edge ({edge_6_5:.4%}) should be >0.5% higher than "
            f"3:2 edge ({edge_3_2:.4%})"
        )


@pytest.mark.slow
class TestCICalibration:
    """Verify that house_edge_with_ci's 95% CI is well-calibrated.

    Runs K independent simulations of the same rule set, each with a
    different seed, and counts how often the reported 95% CI contains
    solve(rules).house_edge. Under correct calibration, coverage is
    Binomial(K, 0.95) -- so observed coverage that falls below a tight
    binomial lower-tail threshold flags a bug in the delta-method
    variance formula or the surrounding accumulators.

    With K=100 and threshold >=89:
      - False-positive rate at p=0.95: 0.4%
      - Power at p=0.85: 84%  (rejects gross miscalibration)
      - Power at p=0.80: 99%
    """

    K = 100
    N_PER_TRIAL = 20_000
    BASE_SEED = 0xC0FFEE
    MIN_COVERED = 89  # binom.ppf(0.005, 100, 0.95) + 1, rounded up

    def test_coverage_within_binomial_window(self):
        rules = _rules_h17()
        sol = _cached_solver(rules)
        truth = sol.house_edge

        covered = 0
        widths = []
        for trial in range(self.K):
            seed = self.BASE_SEED + trial
            # Build a fresh strategy per trial: SolverStrategy is stateless
            # but cheap to construct, so we don't need to share one.
            strategy = SolverStrategy(sol)
            stats = _simulate_stats(rules, self.N_PER_TRIAL, seed, strategy)

            ci = stats.house_edge_with_ci(0.95)
            assert ci is not None, f"trial {trial}: CI returned None"
            _, lo, hi, half = ci
            widths.append(half)
            if lo <= truth <= hi:
                covered += 1

        avg_half = sum(widths) / len(widths)
        assert covered >= self.MIN_COVERED, (
            f"95% CI coverage = {covered}/{self.K} = {covered / self.K:.1%}; "
            f"expected >= {self.MIN_COVERED}/{self.K} = "
            f"{self.MIN_COVERED / self.K:.1%}. Truth (solver) = "
            f"{truth:.4%}. Mean CI half-width = {avg_half:.4%}. "
            f"This indicates the delta-method CI in "
            f"SimulationStats.house_edge_with_ci is biased."
        )
