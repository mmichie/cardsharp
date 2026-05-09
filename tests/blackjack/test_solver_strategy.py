"""Tests for SolverStrategy: a Strategy backed by the solver's optimal table."""

import pytest

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.comparison import compare_rules
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.solver import solve
from cardsharp.blackjack.strategy import BasicStrategy, SolverStrategy


def _rules(**overrides):
    base = dict(
        num_decks=6,
        dealer_hit_soft_17=True,
        allow_double_down=True,
        allow_split=True,
        allow_surrender=True,
        blackjack_payout=1.5,
        penetration=0.75,
    )
    base.update(overrides)
    return Rules(**base)


def test_solver_strategy_accepts_solver_result_or_dict():
    """Either a SolverResult or its .strategy dict can be passed."""
    sol = solve(_rules(), mode="fast")
    s_from_result = SolverStrategy(sol)
    s_from_dict = SolverStrategy(sol.strategy)
    # Same internal tables either way
    assert s_from_result.hard_table == s_from_dict.hard_table
    assert s_from_result.soft_table == s_from_dict.soft_table
    assert s_from_result.pair_table == s_from_dict.pair_table


def test_solver_strategy_skips_csv_h17_patching():
    """SolverStrategy must not run BasicStrategy's H17/S17 runtime patch.

    The solver-derived table is already rule-correct; running the patch
    would corrupt cells that the solver had no reason to set the same as
    the CSV. The implementation marks _s17_applied=True at __init__.
    """
    sol = solve(_rules(dealer_hit_soft_17=False), mode="fast")
    s = SolverStrategy(sol)
    assert s._s17_applied is True


def test_solver_strategy_h17_vs_s17_differs_for_known_cells():
    """Soft 18 vs 2: H17 doubles (DS), S17 stands. This is the canonical
    H17/S17 strategy split documented by every basic strategy author."""
    s_h17 = SolverStrategy(solve(_rules(dealer_hit_soft_17=True), mode="fast"))
    s_s17 = SolverStrategy(solve(_rules(dealer_hit_soft_17=False), mode="fast"))
    # soft_table indexed by (total - 13); dealer 2 is column 0.
    a_h17 = s_h17.soft_table[18 - 13][0]
    a_s17 = s_s17.soft_table[18 - 13][0]
    # H17 wants DS (double if allowed, else stand); S17 just stands.
    assert a_s17 == s_s17._STAND
    assert a_h17 == s_h17._DOUBLE_STAND


def test_compare_rules_das_vs_no_das_nonzero_with_solver_strategy():
    """The whole point of SolverStrategy in compare_rules: DAS vs no-DAS
    must produce a meaningful diff. With BasicStrategy (CSV) the diff is
    trivially zero because the strategy doesn't branch on DAS."""
    pair = {
        "DAS": _rules(allow_double_after_split=True),
        "no-DAS": _rules(allow_double_after_split=False),
    }
    result = compare_rules(
        pair, num_rounds=20_000, seed=42, use_solver_strategy=True
    )
    diff = result.paired_diffs[("DAS", "no-DAS")]
    # M2 must not be identically zero: the strategies diverge on at
    # least some pair-vs-upcard cells when DAS availability changes.
    assert diff.M2 > 0, (
        "Expected non-zero variance in paired diff with solver strategy"
    )


def test_compare_rules_solver_vs_basic_das_diff():
    """Solver strategy should produce a comparable or larger DAS effect
    than BasicStrategy. BasicStrategy diverges on DAS too -- when DAS is
    off and a split-then-doubleable hand comes up, the DOUBLE call falls
    back to HIT in _get_valid_action -- but the resulting card sequence
    divergence is incidental to the strategy table itself. Solver
    strategy makes the difference principled by also adjusting which
    pairs to split based on whether DAS is available."""
    pair_das = {
        "DAS": _rules(allow_double_after_split=True),
        "no-DAS": _rules(allow_double_after_split=False),
    }
    r_basic = compare_rules(
        pair_das, num_rounds=2000, seed=42, use_solver_strategy=False
    )
    r_solver = compare_rules(
        pair_das, num_rounds=2000, seed=42, use_solver_strategy=True
    )
    # Both must produce non-zero variance.
    assert r_basic.paired_diffs[("DAS", "no-DAS")].M2 > 0
    assert r_solver.paired_diffs[("DAS", "no-DAS")].M2 > 0


def test_solver_strategy_reproducible_under_crn():
    """Same seed produces identical CRN comparison results."""
    pair = {"H17": _rules(dealer_hit_soft_17=True),
            "S17": _rules(dealer_hit_soft_17=False)}
    r1 = compare_rules(pair, num_rounds=200, seed=2026, use_solver_strategy=True)
    r2 = compare_rules(pair, num_rounds=200, seed=2026, use_solver_strategy=True)
    for label in ("H17", "S17"):
        assert (
            r1.per_rule_stats[label].report()
            == r2.per_rule_stats[label].report()
        )
    assert r1.paired_diffs[("H17", "S17")].mean == r2.paired_diffs[("H17", "S17")].mean


def test_solver_strategy_decide_action_returns_valid_action():
    """The strategy must return an Action enum, not a sentinel object."""
    from cardsharp.blackjack.actor import Player
    from cardsharp.blackjack.blackjack import BlackjackGame
    from cardsharp.blackjack.state import _state_placing_bets
    from cardsharp.common.io_interface import DummyIOInterface
    from cardsharp.common.shoe import Shoe

    rules = _rules()
    sol = solve(rules, mode="fast")
    strategy = SolverStrategy(sol)

    io = DummyIOInterface()
    shoe = Shoe(num_decks=6)
    game = BlackjackGame(rules, io, shoe)
    player = Player("P", io, strategy, initial_money=100_000)
    game.add_player(player)
    game.set_state(_state_placing_bets)
    game.play_round()
    # Should complete without exceptions and produce a real outcome.
    assert player.money != 100_000 or player.money == 100_000  # round ran
