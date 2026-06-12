"""Tests for the fastsim run surface (engine resolution and fallback).

Unlike tests/test_fastsim_core.py, most of this file does NOT require the
Rust extension: resolution policy and the Python fallback path must work
on a pure-Python install, which is exactly what the main CI job runs.
"""

import logging
import os

import pytest

os.environ["BLACKJACK_DISABLE_LOGGING"] = "1"

from cardsharp.blackjack.decision_logger import decision_logger  # noqa: E402
from cardsharp.blackjack.rules import Rules  # noqa: E402
from cardsharp.blackjack.strategy import (  # noqa: E402
    BasicStrategy,
    CountingStrategy,
    MartingaleStrategy,
)
from cardsharp.fastsim import (  # noqa: E402
    CORE_AVAILABLE,
    resolve_engine,
    simulate,
    strategy_is_encodable,
)

decision_logger.set_level(logging.ERROR)

needs_core = pytest.mark.skipif(
    not CORE_AVAILABLE, reason="cardsharp-core extension not built"
)


def make_rules(**overrides):
    kwargs = dict(
        num_decks=6,
        dealer_peek=True,
        allow_double_after_split=True,
        min_bet=10,
        max_bet=1000,
        penetration=0.75,
        dealer_hit_soft_17=True,
    )
    kwargs.update(overrides)
    return Rules(**kwargs)


# --- Rules-surface tripwire (beads-366) -------------------------------------
#
# The one silent drift path between engines: a field added to the Python
# Rules that the facade neither maps nor refuses would be honored by the
# reference engine and silently ignored by the core. Every Rules field
# must therefore be classified below. A new field fails this test until
# someone decides: map it (port the behavior to the core), refuse it
# (resolve_engine falls back with a reason), or prove it inert and add a
# parity fuzz config exercising it.

CORE_MAPPED = {
    "blackjack_payout",
    "dealer_hit_soft_17",
    "allow_split",
    "allow_double_down",
    "allow_insurance",
    "allow_surrender",
    "allow_early_surrender",
    "allow_double_after_split",
    "allow_resplitting",
    "dealer_peek",
    "num_decks",
    "min_bet",
    "max_bet",
    "max_splits",
    "insurance_payout",
    "five_card_charlie",
    "penetration",
    "burn_cards",
    "resplit_aces",
    "hit_split_aces",
    "allow_obo",
    "use_csm",
    "double_on",
}

CORE_REFUSED = {
    "variant",  # classic only; rules_kwargs raises otherwise
}

# Fields proven to have no effect on classic strategy-driven rounds; each
# claim is exercised by a dedicated parity fuzz config in
# tests/test_fastsim_parity.py so it cannot rot silently.
ENGINE_INERT = {
    "allow_late_surrender": "only read by Rules.can_surrender's non-variant "
    "fallback, which is dead under the classic action validator",
    "time_limit": "only read on the IOInterface (interactive) decision path, "
    "never when a strategy decides",
    "bonus_payouts": "the classic variant's payout calculator bypasses the "
    "bonus-combination branch entirely",
}


def rules_surface():
    import inspect

    init_params = set(inspect.signature(Rules.__init__).parameters) - {"self"}
    return init_params | set(Rules().to_dict().keys())


def test_every_rules_field_is_classified_for_the_fast_core():
    surface = rules_surface()
    classified = CORE_MAPPED | CORE_REFUSED | set(ENGINE_INERT)
    unclassified = surface - classified
    assert not unclassified, (
        f"New Rules field(s) {sorted(unclassified)} are not classified for "
        f"the fast core. Decide: add to CORE_MAPPED (and port the behavior "
        f"to cardsharp_core + rules_kwargs + parity coverage), CORE_REFUSED "
        f"(and make rules_kwargs/resolve_engine reject it), or ENGINE_INERT "
        f"(with proof and a parity fuzz config)."
    )
    stale = classified - surface
    assert not stale, f"Classified field(s) {sorted(stale)} no longer exist on Rules"


def test_core_mapped_set_matches_rules_kwargs_output():
    from cardsharp.fastsim import rules_kwargs

    assert set(rules_kwargs(make_rules())) == CORE_MAPPED


# -----------------------------------------------------------------------------


def test_python_engine_can_be_requested_explicitly():
    choice = resolve_engine(make_rules(), BasicStrategy(), requested="python")
    assert not choice.use_core


def test_counting_strategy_is_encodable():
    assert strategy_is_encodable(CountingStrategy(num_decks=6))


def test_martingale_strategy_is_not_encodable():
    assert not strategy_is_encodable(MartingaleStrategy())
    choice = resolve_engine(make_rules(), MartingaleStrategy(), requested="auto")
    assert not choice.use_core
    assert "not table-encodable" in choice.reason


@needs_core
def test_cv_runs_on_the_core_single_seat_only():
    """Since beads-i2s.5 the control variate runs on the core's per-deal
    accumulator; only multi-seat CV still needs the reference engine."""
    rules, strategy = make_rules(), BasicStrategy()
    assert resolve_engine(rules, strategy, needs_cv=True).use_core
    assert not resolve_engine(rules, strategy, needs_cv=True, n_players=2).use_core


def test_vis_forces_the_reference_engine():
    rules, strategy = make_rules(), BasicStrategy()
    assert not resolve_engine(rules, strategy, needs_per_round=True).use_core


@needs_core
def test_csm_and_realistic_shuffles_run_on_the_core():
    assert resolve_engine(make_rules(use_csm=True), BasicStrategy()).use_core
    assert resolve_engine(make_rules(), BasicStrategy(), shuffle_type="riffle").use_core


def test_unknown_shuffle_type_falls_back():
    choice = resolve_engine(make_rules(), BasicStrategy(), shuffle_type="wash")
    assert not choice.use_core
    assert "unknown shuffle_type" in choice.reason


def test_requested_fast_raises_with_blockers():
    with pytest.raises(RuntimeError, match="not table-encodable"):
        resolve_engine(make_rules(), MartingaleStrategy(), requested="fast")


def test_simulate_python_fallback_produces_stats():
    run = simulate(
        make_rules(), BasicStrategy(), num_rounds=200, seed=7, engine="python"
    )
    assert run.engine == "python"
    assert run.stats.n_rounds == 200
    assert run.stats.games_played == 200
    assert run.stats.bet_sum == 200 * 10


@needs_core
def test_basic_strategy_resolves_to_fast_core():
    choice = resolve_engine(make_rules(), BasicStrategy(), requested="auto")
    assert choice.use_core


@needs_core
def test_simulate_fast_engine_round_count_and_determinism():
    rules, strategy = make_rules(), BasicStrategy()
    a = simulate(rules, strategy, num_rounds=50_000, seed=11, engine="fast")
    b = simulate(rules, strategy, num_rounds=50_000, seed=11, engine="fast")
    assert a.engine == "fast"
    assert a.stats.n_rounds == 50_000
    assert a.stats.report() == b.stats.report()


@needs_core
def test_solver_strategy_without_ev_table_is_encodable():
    from cardsharp.blackjack.solver import solve
    from cardsharp.blackjack.strategy import SolverStrategy

    rules = make_rules(num_decks=6)
    sol = solve(rules, mode="fast")
    strategy = SolverStrategy(sol)
    assert strategy_is_encodable(strategy)
    run = simulate(rules, strategy, num_rounds=20_000, seed=3, engine="fast")
    assert run.engine == "fast"

    cd_strategy = SolverStrategy(sol, use_ev_table=True)
    assert not strategy_is_encodable(cd_strategy)


@needs_core
def test_run_fast_per_deal_returns_stats_and_cells():
    """Facade for the per-deal EV diagnostic: stats lift into
    SimulationStats (per_deal key consumed, not leaked) and the cells
    cover every simulated round."""
    from cardsharp.fastsim import run_fast_per_deal

    rules = make_rules(penetration=0.01)  # fresh shoe: the diagnostic's mode
    stats, cells = run_fast_per_deal(rules, BasicStrategy(), 5_000, seed=31)
    assert stats.n_rounds == 5_000
    assert len(cells) == 1000
    assert sum(n for n, _, _ in cells) == 5_000


@needs_core
def test_attach_cv_from_cells_matches_per_round_welford():
    """The CV accumulators derived from per-deal cells must equal what
    per-round Welford accumulation produces on the same rounds (Y is
    constant within a cell, so the reconstruction is exact algebra)."""
    from cardsharp.blackjack.stats import SimulationStats
    from cardsharp.fastsim import attach_cv_from_cells

    # Three synthetic deal cells with hand-picked X samples.
    rounds = {
        (5, 9, 6): [1.0, -1.0, -1.0, 1.0, 1.5],
        (10, 10, 10): [0.0, 1.0, -1.0],
        (1, 10, 2): [1.5, 1.5],
    }
    deal_ev = {(5, 9, 6): -0.05, (10, 10, 10): 0.55, (1, 10, 2): 1.45}
    mu_y = -0.006

    # Reference: the Python engine's per-round accumulation.
    reference = SimulationStats()
    reference.cv_mu_y = mu_y
    for key, xs in rounds.items():
        for x in xs:
            reference.record_round(x * 10.0, 10.0, 10.0, cv_y=deal_ev[key])

    # Cells as the core would report them.
    cells = [(0, 0.0, 0.0)] * 1000
    cells = list(cells)
    for (lo, hi, up), xs in rounds.items():
        idx = (lo - 1) * 100 + (hi - 1) * 10 + (up - 1)
        cells[idx] = (len(xs), sum(xs), sum(x * x for x in xs))

    derived = SimulationStats()
    attach_cv_from_cells(derived, cells, deal_ev, mu_y)

    assert derived.cv_n == reference.cv_n
    for field in ("cv_x_mean", "cv_y_mean", "cv_x_M2", "cv_y_M2", "cv_xy_C"):
        assert getattr(derived, field) == pytest.approx(
            getattr(reference, field), abs=1e-12
        ), field

    ref_est = reference.control_variate_he_with_ci()
    der_est = derived.control_variate_he_with_ci()
    assert der_est["he"] == pytest.approx(ref_est["he"], abs=1e-12)
    assert der_est["half"] == pytest.approx(ref_est["half"], abs=1e-12)


@needs_core
def test_run_fast_cv_against_solver():
    """End-to-end: fresh-shoe CV on the core lands near the solver's
    table EV with a substantially tighter CI than the plain estimator."""
    from cardsharp.blackjack.blackjack import build_deal_ev_table
    from cardsharp.blackjack.solver import solve, strategy_house_edge
    from cardsharp.blackjack.strategy import SolverStrategy
    from cardsharp.fastsim import run_fast_cv

    rules = make_rules(penetration=0.01)  # fresh shoe: the solver's model
    sol = solve(rules, mode="auto")
    deal_ev = build_deal_ev_table(sol.ev_table, rules)
    strategy = SolverStrategy(sol)  # pure table: encodable

    stats = run_fast_cv(
        rules, strategy, 400_000, seed=4242, deal_ev_table=deal_ev, mu_y=-sol.house_edge
    )
    est = stats.control_variate_he_with_ci()
    assert est is not None
    assert stats.cv_n == 400_000

    # The CV estimate converges to the achievable table EV; allow the
    # documented few-bp achievability gap above the CD reference plus
    # 4-sigma noise.
    table_he = strategy_house_edge(sol, rules)
    assert abs(est["he"] - table_he) < 0.0010 + 4 * est["half"], (
        f"CV HE {est['he']:.5f} vs table {table_he:.5f} "
        f"(half-width {est['half']:.5f})"
    )
    # A real variance reduction over the plain estimator. The deal-EV
    # control variate buys ~20% at 6 decks (the 2026-06-09 Python-engine
    # measurement: +/-4.5bp CV vs +/-5.1bp plain at 20M rounds); floor
    # well below that to leave room for estimation noise.
    assert est["reduction_pct"] > 10.0
    assert est["half"] < est["baseline_half"]


@needs_core
def test_fast_cv_matches_python_cv_statistically():
    """Cross-engine: the core's cell-derived CV and the Python engine's
    per-round CV are the same estimator -- estimates agree within joint
    noise and the variance reductions land in the same range."""
    import random as _random

    from cardsharp.blackjack.blackjack import build_deal_ev_table, play_game
    from cardsharp.blackjack.solver import solve
    from cardsharp.blackjack.stats import SimulationStats
    from cardsharp.blackjack.strategy import SolverStrategy
    from cardsharp.common.io_interface import DummyIOInterface
    from cardsharp.common.shoe import Shoe
    from cardsharp.fastsim import run_fast_cv

    rules = make_rules(penetration=0.01)
    sol = solve(rules, mode="auto")
    deal_ev = build_deal_ev_table(sol.ev_table, rules)
    mu_y = -sol.house_edge

    fast = run_fast_cv(
        rules, SolverStrategy(sol), 300_000, seed=77, deal_ev_table=deal_ev, mu_y=mu_y
    )
    fast_est = fast.control_variate_he_with_ci()

    _random.seed(77)
    py_stats = SimulationStats()
    py_stats.cv_mu_y = mu_y
    strategy = SolverStrategy(sol)
    shoe = Shoe(num_decks=rules.num_decks, penetration=rules.penetration)
    io = DummyIOInterface()
    for _ in range(30_000):
        _net, _total, _initial, report, shoe = play_game(
            rules, io, ["P"], strategy, shoe, 1000, ev_table=deal_ev
        )
        py_stats.merge(SimulationStats.from_dict(report))
    py_est = py_stats.control_variate_he_with_ci()

    joint = 1.2 * (fast_est["half"] + py_est["half"])
    assert abs(fast_est["he"] - py_est["he"]) < joint, (
        f"fast {fast_est['he']:.5f}+/-{fast_est['half']:.5f} vs "
        f"python {py_est['he']:.5f}+/-{py_est['half']:.5f}"
    )
    assert abs(fast_est["reduction_pct"] - py_est["reduction_pct"]) < 15.0
