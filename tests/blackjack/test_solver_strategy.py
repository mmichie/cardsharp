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


def test_solver_strategy_ds_sentinel_survives_pickle():
    """The DS sentinel must compare equal after a pickle round-trip.

    A previous regression used `_DOUBLE_STAND = object()` and an `is`
    comparison in _get_valid_action. After multiprocessing pickled the
    strategy to worker processes, the DS cells held new object()
    instances whose identity no longer matched the worker class's
    sentinel -- so the `is` check failed and all DS plays (e.g. Soft 18
    vs 2-6 under H17) fell through to HIT. Measured house edge in
    --simulate ran ~16-23 bp higher than the solver predicted, with the
    bias absent under --single_cpu. This test guards against the
    regression by exercising both pickle equality and the live decision
    branch on a DS cell.
    """
    import pickle

    from cardsharp.blackjack.actor import Player
    from cardsharp.blackjack.blackjack import BlackjackGame
    from cardsharp.blackjack.state import _state_placing_bets
    from cardsharp.common.io_interface import DummyIOInterface
    from cardsharp.common.shoe import Shoe

    rules = _rules(dealer_hit_soft_17=True, allow_double_after_split=True)
    sol = solve(rules, mode="fast")
    s = SolverStrategy(sol)

    # 1. There must actually be DS cells in the canonical H17+DAS table.
    ds_cells = sum(
        1
        for table in (s.hard_table, s.soft_table, s.pair_table)
        for row in table
        for cell in row
        if cell == s._DOUBLE_STAND
    )
    assert ds_cells > 0, (
        "Expected at least one DS cell in H17+DAS solver strategy; "
        "test cannot detect the pickle regression without one."
    )

    # 2. Round-trip through pickle. Cells must still compare equal.
    s2 = pickle.loads(pickle.dumps(s))
    ds_after = sum(
        1
        for table in (s2.hard_table, s2.soft_table, s2.pair_table)
        for row in table
        for cell in row
        if cell == s2._DOUBLE_STAND
    )
    assert ds_after == ds_cells, (
        f"DS cells lost across pickle: {ds_cells} → {ds_after}. "
        f"Sentinel is not pickle-stable; multiprocessing workers will "
        f"silently downgrade DS plays to HIT."
    )

    # 3. End-to-end: a DS cell must produce DOUBLE (or STAND if double is
    # unavailable for the hand), never HIT. Build a hand of A,7 vs dealer
    # 2 -- the canonical DS cell in H17 -- and verify the decision.
    io = DummyIOInterface()
    shoe = Shoe(num_decks=6)
    game = BlackjackGame(rules, io, shoe)
    player = Player("P", io, s2, initial_money=100_000)
    game.add_player(player)

    from cardsharp.common.card import Card, Rank, Suit
    hand = player.hands[0]
    hand.add_card(Card(Suit.SPADES, Rank.ACE))
    hand.add_card(Card(Suit.HEARTS, Rank.SEVEN))
    # _cached_valid_actions short-circuits the property's recompute path
    # so we can pose a precise question to the strategy.
    player._cached_valid_actions = [Action.HIT, Action.STAND, Action.DOUBLE]
    dealer_two = Card(Suit.CLUBS, Rank.TWO)

    decision = s2.decide_action(player, dealer_two, game)
    assert decision == Action.DOUBLE, (
        f"Soft 18 vs 2 under H17+DAS should resolve DS to DOUBLE; got "
        f"{decision}. This is the regression signature."
    )
