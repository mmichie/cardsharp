"""Tests for the strategy factory in cardsharp.blackjack.strategy."""

import pytest

from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.strategy import (
    AggressiveStrategy,
    BasicStrategy,
    CountingStrategy,
    MartingaleStrategy,
    SolverStrategy,
    create_strategy,
    register_strategy,
    STRATEGY_FACTORIES,
)


def test_create_basic_strategy():
    s = create_strategy("basic")
    assert isinstance(s, BasicStrategy)


def test_create_counting_strategy_uses_rules_num_decks():
    rules = Rules(num_decks=8)
    s = create_strategy("count", rules=rules)
    assert isinstance(s, CountingStrategy)
    assert s.initial_decks == 8


def test_create_counting_strategy_uses_explicit_num_decks():
    """Explicit num_decks kwarg overrides what's in rules."""
    rules = Rules(num_decks=6)
    s = create_strategy("count", rules=rules, num_decks=2)
    assert s.initial_decks == 2


def test_create_counting_strategy_defaults_when_no_context():
    """Without rules or num_decks, falls back to a sensible default."""
    s = create_strategy("count")
    assert isinstance(s, CountingStrategy)
    # Default is 6 (typical 6-deck shoe)
    assert s.initial_decks == 6


def test_create_aggressive_via_aliases():
    """Both 'aggro' and 'aggressive' resolve to AggressiveStrategy."""
    s1 = create_strategy("aggro")
    s2 = create_strategy("aggressive")
    assert isinstance(s1, AggressiveStrategy)
    assert isinstance(s2, AggressiveStrategy)


def test_create_martingale_via_aliases():
    s1 = create_strategy("martin")
    s2 = create_strategy("martingale")
    assert isinstance(s1, MartingaleStrategy)
    assert isinstance(s2, MartingaleStrategy)


def test_create_solver_strategy_requires_rules():
    """SolverStrategy needs rules to call solve(); raises without."""
    with pytest.raises(ValueError, match="solver strategy requires"):
        create_strategy("solver")


def test_create_solver_strategy_with_rules():
    rules = Rules(num_decks=6, dealer_hit_soft_17=True, blackjack_payout=1.5)
    s = create_strategy("solver", rules=rules)
    assert isinstance(s, SolverStrategy)
    # The solver-derived tables should be populated.
    assert s.hard_table[16 - 4][9] is not None  # Hard 16 vs A
    assert s._s17_applied is True  # Solver tables don't need patching


def test_create_strategy_unknown_name_raises():
    with pytest.raises(ValueError, match="Unknown strategy"):
        create_strategy("not_a_strategy")


def test_create_strategy_case_insensitive():
    assert isinstance(create_strategy("BASIC"), BasicStrategy)
    assert isinstance(create_strategy("Solver", rules=Rules(num_decks=6)),
                      SolverStrategy)


def test_register_custom_strategy():
    """Third-party strategies can register their own builders."""
    sentinel = BasicStrategy()

    def _build_sentinel(rules=None, **_):
        return sentinel

    try:
        register_strategy("custom_test_xyz", _build_sentinel)
        s = create_strategy("custom_test_xyz")
        assert s is sentinel
    finally:
        # Clean up the registry so other tests aren't affected
        STRATEGY_FACTORIES.pop("custom_test_xyz", None)


def test_factory_registry_has_expected_keys():
    expected = {
        "basic", "count", "counting", "aggro", "aggressive",
        "martin", "martingale", "solver",
    }
    assert expected.issubset(set(STRATEGY_FACTORIES))
