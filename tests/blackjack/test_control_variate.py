"""Tests for the solver-EV control variate.

The control-variate-adjusted estimator is unbiased for E[X] and has
lower variance than the raw mean. Tests:
  - Welford state for X, Y, and the X*Y co-moment is correct
  - Merge of two CV accumulators equals single-pass accumulation
  - With Y identical to X, beta=1 and variance reduces to ~0
  - With Y constant (zero variance), the estimator falls back gracefully
  - Production sim with --cv: baseline and CV estimates agree within CIs,
    and CV CI is strictly tighter (positive variance reduction)
"""

import random

import pytest

from cardsharp.blackjack.blackjack import (
    build_deal_ev_table,
    play_game,
)
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.stats import SimulationStats
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.common.io_interface import DummyIOInterface
from cardsharp.common.shoe import Shoe


def test_record_round_with_cv_y_updates_cv_state():
    """Passing cv_y must update CV accumulators alongside the regular ones."""
    s = SimulationStats()
    s.record_round(net=2.0, initial_bet=10.0, total_bet=10.0, cv_y=0.15)
    s.record_round(net=-5.0, initial_bet=10.0, total_bet=10.0, cv_y=-0.1)
    s.record_round(net=15.0, initial_bet=10.0, total_bet=20.0, cv_y=0.5)

    assert s.cv_n == 3
    expected_x_mean = (0.2 + (-0.5) + 1.5) / 3.0
    expected_y_mean = (0.15 + (-0.1) + 0.5) / 3.0
    assert s.cv_x_mean == pytest.approx(expected_x_mean, rel=1e-12, abs=1e-12)
    assert s.cv_y_mean == pytest.approx(expected_y_mean, rel=1e-12, abs=1e-12)


def test_record_round_without_cv_y_skips_cv_state():
    """When cv_y is None, CV accumulators must remain unchanged."""
    s = SimulationStats()
    s.record_round(net=2.0, initial_bet=10.0, total_bet=10.0)
    s.record_round(net=-5.0, initial_bet=10.0, total_bet=10.0)
    assert s.cv_n == 0
    assert s.cv_x_mean == 0.0
    assert s.cv_y_mean == 0.0


def test_cv_merge_matches_single_pass():
    """Splitting and merging CV accumulators must reproduce single-pass state."""
    rng = random.Random(11)
    pairs = [(rng.gauss(-0.05, 1.0), rng.gauss(-0.05, 0.5)) for _ in range(800)]

    full = SimulationStats()
    for x, y in pairs:
        full.record_round(net=x, initial_bet=1.0, total_bet=1.0, cv_y=y)

    a = SimulationStats()
    for x, y in pairs[:250]:
        a.record_round(net=x, initial_bet=1.0, total_bet=1.0, cv_y=y)
    b = SimulationStats()
    for x, y in pairs[250:]:
        b.record_round(net=x, initial_bet=1.0, total_bet=1.0, cv_y=y)
    a.merge(b)

    assert a.cv_n == full.cv_n
    assert a.cv_x_mean == pytest.approx(full.cv_x_mean, rel=1e-12, abs=1e-12)
    assert a.cv_y_mean == pytest.approx(full.cv_y_mean, rel=1e-12, abs=1e-12)
    assert a.cv_x_M2 == pytest.approx(full.cv_x_M2, rel=1e-9, abs=1e-9)
    assert a.cv_y_M2 == pytest.approx(full.cv_y_M2, rel=1e-9, abs=1e-9)
    assert a.cv_xy_C == pytest.approx(full.cv_xy_C, rel=1e-9, abs=1e-9)


def test_cv_estimate_perfect_correlation_collapses_variance():
    """If X == Y exactly and mu_Y is known, CV variance must be ~0."""
    s = SimulationStats()
    s.cv_mu_y = 0.0  # known true mean
    rng = random.Random(7)
    for _ in range(500):
        v = rng.gauss(0.0, 1.0)
        s.record_round(net=v, initial_bet=1.0, total_bet=1.0, cv_y=v)
    res = s.control_variate_he_with_ci(0.95)
    assert res is not None
    # beta should be exactly 1; CV variance should be near zero
    assert res["beta"] == pytest.approx(1.0, abs=1e-12)
    assert res["half"] < 1e-9
    # And HE should be exactly -mu_Y = 0
    assert res["he"] == pytest.approx(0.0, abs=1e-12)
    assert res["reduction_pct"] > 99.999


def test_cv_estimate_returns_none_without_mu_y():
    s = SimulationStats()
    for i in range(10):
        s.record_round(net=i, initial_bet=1.0, total_bet=1.0, cv_y=i * 0.5)
    # cv_mu_y not set
    assert s.control_variate_he_with_ci() is None


def test_cv_estimate_returns_none_with_zero_y_variance():
    s = SimulationStats()
    s.cv_mu_y = 0.0
    for i in range(10):
        s.record_round(net=i, initial_bet=1.0, total_bet=1.0, cv_y=0.0)
    # var_y = 0 -> beta undefined -> return None
    assert s.control_variate_he_with_ci() is None


def test_build_deal_ev_table_keys_match_solver():
    """deal_ev_table must have an entry for every (c1<=c2, up) the solver
    populated."""
    from cardsharp.blackjack.solver import solve

    rules = Rules(num_decks=6, dealer_hit_soft_17=True, blackjack_payout=1.5)
    sol = solve(rules, mode="fast")
    deal_ev = build_deal_ev_table(sol.ev_table, rules)

    # Every (c1, c2, up) in the solver table must be in the deal table
    for key in sol.ev_table:
        assert key in deal_ev, f"missing key {key}"
    # Values are bounded: outcome per bet is in [-1, max bj_payout]
    for key, ev in deal_ev.items():
        assert -1.0 <= ev <= rules.blackjack_payout + 0.01


def test_build_deal_ev_table_weighted_average_recovers_solver_he():
    """Deal-weighted average of the deal-EV table must equal -solver_HE
    (matching the formula the solver itself uses to compute house edge)."""
    from cardsharp.blackjack.solver import solve
    from cardsharp.blackjack.solver.types import Deck

    rules = Rules(num_decks=6, dealer_hit_soft_17=True, blackjack_payout=1.5)
    sol = solve(rules, mode="fast")
    deal_ev = build_deal_ev_table(sol.ev_table, rules)

    deck = Deck.finite(6)
    weighted = 0.0
    # Replicate the solver's deal-weighting (with c1<=c2 and a 2x factor for c1!=c2)
    for c1 in range(1, 11):
        for c2 in range(c1, 11):
            for up in range(1, 11):
                key = (c1, c2, up)
                if key not in deal_ev:
                    continue
                from cardsharp.blackjack.solver.types import CARD_IDX
                p1 = deck._counts[CARD_IDX[c1]] / deck._total
                deck1 = deck.remove_card(c1)
                p2 = deck1._counts[CARD_IDX[c2]] / deck1._total
                deck2 = deck1.remove_card(c2)
                p3 = deck2._counts[CARD_IDX[up]] / deck2._total
                ordering = 1 if c1 == c2 else 2
                p_deal = p1 * p2 * p3 * ordering
                weighted += p_deal * deal_ev[key]
    # Solver house_edge = -E[X]; weighted = E[X] under fresh shoe
    assert weighted == pytest.approx(-sol.house_edge, abs=1e-9)


def test_play_game_with_ev_table_records_cv_y():
    """Calling play_game with an ev_table populates cv_n and cv_y_mean."""
    from cardsharp.blackjack.solver import solve

    random.seed(2026)
    rules = Rules(num_decks=6, dealer_hit_soft_17=True, blackjack_payout=1.5)
    sol = solve(rules, mode="fast")
    deal_ev = build_deal_ev_table(sol.ev_table, rules)

    strategy = BasicStrategy()
    io = DummyIOInterface()
    shoe = Shoe(num_decks=6, penetration=0.75)

    agg = SimulationStats()
    agg.cv_mu_y = -sol.house_edge
    for _ in range(500):
        e, _b, _ib, result, shoe = play_game(
            rules, io, ["P"], strategy, shoe, 10_000, ev_table=deal_ev
        )
        agg.merge(SimulationStats.from_dict(result))

    assert agg.cv_n > 0
    # Y_bar should be close to mu_Y for a fresh-shoe approximation
    assert abs(agg.cv_y_mean - agg.cv_mu_y) < 0.05


def test_cv_estimator_unbiased_and_reduces_variance():
    """End-to-end: CV-adjusted HE agrees with baseline within CIs and the
    CV CI is strictly tighter."""
    from cardsharp.blackjack.solver import solve

    random.seed(2026)
    rules = Rules(num_decks=6, dealer_hit_soft_17=True, blackjack_payout=1.5)
    sol = solve(rules, mode="fast")
    deal_ev = build_deal_ev_table(sol.ev_table, rules)

    strategy = BasicStrategy()
    io = DummyIOInterface()
    shoe = Shoe(num_decks=6, penetration=0.75)

    agg = SimulationStats()
    agg.cv_mu_y = -sol.house_edge
    for _ in range(20_000):
        e, _b, _ib, result, shoe = play_game(
            rules, io, ["P"], strategy, shoe, 10_000_000, ev_table=deal_ev
        )
        agg.merge(SimulationStats.from_dict(result))

    baseline = agg.house_edge_with_ci(0.95)
    cv = agg.control_variate_he_with_ci(0.95)
    assert baseline is not None and cv is not None
    base_he, _, _, base_half = baseline
    # CV reduces variance
    assert cv["half"] < base_half
    assert cv["reduction_pct"] > 5.0  # at least 5% reduction empirically
    # Estimates agree within ~3 standard errors of either CI
    assert abs(cv["he"] - base_he) < 3.0 * max(cv["half"], base_half)
    # beta should be close to 1 since Y = E[X | deal]
    assert 0.7 < cv["beta"] < 1.3
