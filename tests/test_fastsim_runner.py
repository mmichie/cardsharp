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


def test_python_engine_can_be_requested_explicitly():
    choice = resolve_engine(make_rules(), BasicStrategy(), requested="python")
    assert not choice.use_core


def test_counting_strategy_is_not_encodable():
    assert not strategy_is_encodable(CountingStrategy())
    choice = resolve_engine(make_rules(), CountingStrategy(), requested="auto")
    assert not choice.use_core
    assert "not table-encodable" in choice.reason


def test_cv_and_vis_force_the_reference_engine():
    rules, strategy = make_rules(), BasicStrategy()
    assert not resolve_engine(rules, strategy, needs_cv=True).use_core
    assert not resolve_engine(rules, strategy, needs_per_round=True).use_core


def test_csm_and_realistic_shuffles_force_the_reference_engine():
    assert not resolve_engine(make_rules(use_csm=True), BasicStrategy()).use_core
    assert not resolve_engine(
        make_rules(), BasicStrategy(), shuffle_type="riffle"
    ).use_core


def test_requested_fast_raises_with_blockers():
    with pytest.raises(RuntimeError, match="not table-encodable"):
        resolve_engine(make_rules(), CountingStrategy(), requested="fast")


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
