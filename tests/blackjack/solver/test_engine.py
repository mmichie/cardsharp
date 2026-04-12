"""Tests for the solver engine: house edge and strategy generation."""

import os
import pytest

from cardsharp.blackjack.solver import solve
from cardsharp.blackjack.rules import Rules


class TestHouseEdge:

    def test_infinite_h17_reasonable_range(self):
        """Infinite-deck H17 house edge should be in a reasonable range."""
        rules = Rules(
            num_decks=99,  # triggers infinite-deck mode
            dealer_hit_soft_17=True,
            dealer_peek=True,
            allow_surrender=True,
            allow_late_surrender=True,
            allow_double_after_split=False,
        )
        result = solve(rules)
        assert 0.005 < result.house_edge < 0.012, (
            f"H17 edge {result.house_edge:.4%} outside expected range"
        )

    def test_infinite_s17_reasonable_range(self):
        """Infinite-deck S17 house edge should be lower than H17."""
        rules = Rules(
            num_decks=99,
            dealer_hit_soft_17=False,
            dealer_peek=True,
            allow_surrender=True,
            allow_late_surrender=True,
            allow_double_after_split=False,
        )
        result = solve(rules)
        assert 0.003 < result.house_edge < 0.010

    def test_6deck_h17_matches_published(self):
        """6-deck H17 DAS no-surrender should be close to WoO Appendix 9.

        WoO: 0.6151% (with resplit-to-4). Our no-resplit adds ~0.07%.
        """
        rules = Rules(
            num_decks=6,
            dealer_hit_soft_17=True,
            dealer_peek=True,
            allow_surrender=False,
            allow_double_after_split=True,
        )
        result = solve(rules)
        # WoO: 0.6151% + ~0.07% no-resplit = ~0.685%
        assert 0.005 < result.house_edge < 0.009, (
            f"6d H17 edge {result.house_edge:.4%}"
        )

    def test_s17_lower_than_h17(self):
        """S17 must have lower house edge than H17 (fundamental principle)."""
        base = dict(
            dealer_peek=True,
            allow_surrender=True,
            allow_late_surrender=True,
            allow_double_after_split=False,
        )
        h17 = solve(Rules(dealer_hit_soft_17=True, **base))
        s17 = solve(Rules(dealer_hit_soft_17=False, **base))
        assert s17.house_edge < h17.house_edge

    def test_6_to_5_worse_than_3_to_2(self):
        """6:5 BJ payout should increase house edge by ~1.3%."""
        base = dict(
            dealer_hit_soft_17=True,
            dealer_peek=True,
            allow_surrender=True,
            allow_late_surrender=True,
        )
        edge_32 = solve(Rules(blackjack_payout=1.5, **base)).house_edge
        edge_65 = solve(Rules(blackjack_payout=1.2, **base)).house_edge
        diff = edge_65 - edge_32
        assert 0.010 < diff < 0.020, (
            f"6:5 vs 3:2 diff = {diff:.4%}, expected ~1.3-1.4%"
        )

    def test_das_lowers_edge(self):
        """DAS (double after split) should lower house edge."""
        base = dict(
            dealer_hit_soft_17=True,
            dealer_peek=True,
            allow_surrender=True,
            allow_late_surrender=True,
        )
        no_das = solve(Rules(allow_double_after_split=False, **base)).house_edge
        with_das = solve(Rules(allow_double_after_split=True, **base)).house_edge
        assert with_das < no_das

    def test_no_surrender_raises_edge(self):
        """Removing surrender should increase house edge."""
        base = dict(
            dealer_hit_soft_17=True,
            dealer_peek=True,
        )
        with_surr = solve(Rules(allow_surrender=True, allow_late_surrender=True, **base)).house_edge
        no_surr = solve(Rules(allow_surrender=False, **base)).house_edge
        assert no_surr > with_surr

    def test_no_double_raises_edge(self):
        """Removing doubling should increase house edge significantly."""
        base = dict(
            dealer_hit_soft_17=True,
            dealer_peek=True,
            allow_surrender=True,
            allow_late_surrender=True,
        )
        with_dbl = solve(Rules(allow_double_down=True, **base)).house_edge
        no_dbl = solve(Rules(allow_double_down=False, **base)).house_edge
        assert no_dbl > with_dbl + 0.005  # doubling saves at least 0.5%

    def test_no_split_raises_edge(self):
        """Removing splitting should increase house edge."""
        base = dict(
            dealer_hit_soft_17=True,
            dealer_peek=True,
            allow_surrender=True,
            allow_late_surrender=True,
        )
        with_split = solve(Rules(allow_split=True, **base)).house_edge
        no_split = solve(Rules(allow_split=False, **base)).house_edge
        assert no_split > with_split


class TestStrategyGeneration:

    def test_strategy_has_all_rows(self):
        """Generated strategy should have all standard rows."""
        result = solve(Rules(num_decks=99, dealer_peek=True))
        s = result.strategy
        for total in range(4, 22):
            assert f"Hard{total}" in s
        for total in range(13, 22):
            assert f"Soft{total}" in s
        for pair in range(2, 11):
            assert f"Pair{pair}" in s
        assert "PairA" in s

    def test_strategy_always_stand_hard_20(self):
        """Hard 20 should always stand."""
        result = solve(Rules(num_decks=99, dealer_peek=True))
        assert all(a == "S" for a in result.strategy["Hard20"])

    def test_strategy_always_split_aces(self):
        """Pair of aces should always split."""
        result = solve(Rules(dealer_peek=True, allow_split=True))
        assert all(a == "P" for a in result.strategy["PairA"])

    def test_strategy_always_split_eights(self):
        """Pair of 8s should always split (or surrender vs A in H17)."""
        result = solve(Rules(
            dealer_peek=True, allow_split=True,
            allow_surrender=True, allow_late_surrender=True,
            dealer_hit_soft_17=True,
        ))
        for a in result.strategy["Pair8"]:
            assert a in ("P", "R")  # split or surrender

    def test_strategy_never_split_tens(self):
        """Pair of 10s should always stand."""
        result = solve(Rules(dealer_peek=True, allow_split=True))
        assert all(a == "S" for a in result.strategy["Pair10"])

    def test_csv_diff_minimal(self):
        """Solver strategy should closely match basic_strategy.csv.

        Use infinite deck (num_decks=99) to match the CSV, which was
        derived from infinite-deck analysis. A few differences are
        expected for marginal plays.
        """
        rules = Rules(
            num_decks=99,
            dealer_hit_soft_17=True,
            dealer_peek=True,
            allow_surrender=True,
            allow_late_surrender=True,
            allow_double_after_split=False,
        )
        result = solve(rules)
        csv_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..",
            "cardsharp", "blackjack", "basic_strategy.csv",
        )
        diffs = result.diff_strategy(csv_path)
        # Allow up to 5 marginal differences
        assert len(diffs) <= 5, (
            f"Too many diffs ({len(diffs)}) between solver and CSV:\n"
            + "\n".join(diffs)
        )


class TestSolverResult:

    def test_print_strategy(self, capsys):
        """print_strategy should produce output without errors."""
        result = solve(Rules(num_decks=99, dealer_peek=True))
        result.print_strategy()
        captured = capsys.readouterr()
        assert "House edge" in captured.out
        assert "Hard" in captured.out

    def test_to_csv(self, tmp_path):
        """to_csv should write a valid CSV file."""
        result = solve(Rules(num_decks=99, dealer_peek=True))
        csv_file = tmp_path / "strategy.csv"
        result.to_csv(str(csv_file))
        assert csv_file.exists()
        content = csv_file.read_text()
        assert "Hard" in content
        assert "Soft" in content
        assert "Pair" in content

    def test_ev_table_populated(self):
        """EV table should have entries for all state combinations."""
        result = solve(Rules(num_decks=99, dealer_peek=True))
        # 55 player card combos × 10 upcards = 550
        assert len(result.ev_table) == 550

    def test_deterministic(self):
        """Running solver twice should produce identical results."""
        rules = Rules(dealer_peek=True, dealer_hit_soft_17=True)
        r1 = solve(rules)
        r2 = solve(rules)
        assert r1.house_edge == r2.house_edge
