"""End-to-end reproducibility and CI tests for the simulator.

Verifies that:
  - Seeding makes a single-CPU run bit-for-bit reproducible.
  - Per-round Welford state populated by play_game agrees with a direct
    re-computation from the per-round earnings.
  - The reported CI from the production stats accumulator falls close
    to the published 6-deck S17 house edge for a sufficiently large
    sample (smoke check that the integration is wired up correctly).
"""

import random

import pytest

from cardsharp.blackjack.blackjack import play_game
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.stats import SimulationStats
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.common.io_interface import DummyIOInterface
from cardsharp.common.shoe import Shoe


def _run(num_rounds, seed):
    random.seed(seed)
    rules = Rules(num_decks=6, dealer_hit_soft_17=False, blackjack_payout=1.5)
    strategy = BasicStrategy()
    io = DummyIOInterface()
    shoe = Shoe(num_decks=6, penetration=0.75)

    earnings = []
    agg = SimulationStats()
    for _ in range(num_rounds):
        e, _bets, _ib, result, shoe = play_game(
            rules, io, ["P"], strategy, shoe, initial_bankroll=10_000
        )
        agg.merge(SimulationStats.from_dict(result))
        earnings.append(e)
    return earnings, agg


def test_same_seed_reproduces_results():
    """Same seed -> identical per-round earnings sequence."""
    e1, s1 = _run(200, seed=2026)
    e2, s2 = _run(200, seed=2026)

    assert e1 == e2, "Seeded runs must produce identical earnings"
    assert s1.report() == s2.report()


def test_different_seeds_produce_different_results():
    """Different seeds -> different streams (sanity check on seeding)."""
    e1, _ = _run(200, seed=1)
    e2, _ = _run(200, seed=2)
    # Two random streams should differ on at least one round; the chance
    # of all 200 matching is astronomically small.
    assert e1 != e2


def test_per_round_welford_matches_recomputation():
    """The aggregated net_mean must match a direct recomputation from
    the per-round earnings list."""
    earnings, agg = _run(300, seed=42)

    # Filter zero-bet rounds (consistent with play_game's gating)
    # Here every round has a bet, so all earnings count.
    expected_mean = sum(earnings) / len(earnings)

    # Allow tiny floating-point drift from accumulator vs two-pass
    assert agg.net_mean == pytest.approx(expected_mean, rel=1e-10, abs=1e-10)
    assert agg.n_rounds == len(earnings)


def test_house_edge_ci_contains_published_value_large_sample():
    """With ~50K rounds of 6-deck S17 the CI should bracket published HE.

    Published 6-deck S17 (no DAS, late surrender, peek) is ~0.4%; the
    standard error at this N is roughly 0.5%, so a 99% CI of half-width
    ~1.3% will include the truth with very high probability.
    """
    random.seed(2020)
    rules = Rules(
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
    strategy = BasicStrategy()
    io = DummyIOInterface()
    shoe = Shoe(num_decks=6, penetration=0.75)

    agg = SimulationStats()
    for _ in range(50_000):
        e, _bets, _ib, result, shoe = play_game(
            rules, io, ["P"], strategy, shoe, initial_bankroll=10_000_000
        )
        agg.merge(SimulationStats.from_dict(result))

    he_result = agg.house_edge_with_ci(0.99)
    assert he_result is not None
    he, lo, hi, half = he_result

    # Sanity: HE within (-1%, 3%); CI half-width sub-2%.
    assert -0.01 < he < 0.03
    assert half < 0.02
    # 99% CI should contain the published ~0.4% value
    assert lo < 0.005 < hi or lo < 0.004 < hi
