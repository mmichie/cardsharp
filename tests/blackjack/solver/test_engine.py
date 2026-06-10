"""Tests for the solver engine: house edge and strategy generation."""

import os
import pytest

from cardsharp.blackjack.solver import solve, strategy_house_edge
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


class TestAutoMode:
    """Verify mode='auto' routes to the right path for each deck size.

    The auto router is the practical lever for accuracy in small-deck games:
    1-2 decks pick up combinatorial (matches WoO Appendix 9 within rounding),
    3-4 decks pick up exact (closes ~88% of the static-dealer-prob bias),
    5+ decks fall through to fast (where the bias is already <0.005%).
    """

    def _canonical_rules(self, num_decks):
        return Rules(
            num_decks=num_decks,
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

    def test_auto_six_deck_matches_fast(self):
        """At 6 decks, auto should fall through to fast mode (no slowdown,
        ~bit-equal HE). The fast path's bias is sub-noise for typical shoes."""
        rules = self._canonical_rules(6)
        he_auto = solve(rules, mode="auto").house_edge
        he_fast = solve(rules, mode="fast").house_edge
        assert he_auto == he_fast

    def test_auto_five_deck_matches_fast(self):
        """5 decks is the threshold; auto must stay on the fast path."""
        rules = self._canonical_rules(5)
        he_auto = solve(rules, mode="auto").house_edge
        he_fast = solve(rules, mode="fast").house_edge
        assert he_auto == he_fast

    def test_auto_infinite_matches_fast(self):
        """Infinite-deck (num_decks > 8) trivially routes to fast since
        deck composition doesn't change."""
        rules = Rules(num_decks=99, dealer_peek=True, dealer_hit_soft_17=True)
        he_auto = solve(rules, mode="auto").house_edge
        he_fast = solve(rules, mode="fast").house_edge
        assert he_auto == he_fast

    @pytest.mark.slow
    def test_auto_one_deck_routes_to_combinatorial(self):
        """1-deck auto should match combinatorial mode bit-equal, and
        should differ from fast mode by ~0.03% (the dealer-prob-staleness
        gap measured in the prior cross-mode comparison)."""
        rules = self._canonical_rules(1)
        he_auto = solve(rules, mode="auto").house_edge
        he_comb = solve(rules, mode="combinatorial").house_edge
        he_fast = solve(rules, mode="fast").house_edge
        assert he_auto == he_comb
        assert abs(he_fast - he_comb) > 0.0001  # gap is real (~0.03%)

    @pytest.mark.slow
    def test_auto_three_deck_routes_to_exact(self):
        """3-deck auto should pick exact mode and trim the fast-mode gap.

        Pinning equality to exact mode locks in the routing decision: if a
        future change reroutes 3-deck back to fast or to combinatorial, this
        test fails.
        """
        rules = self._canonical_rules(3)
        he_auto = solve(rules, mode="auto").house_edge
        he_exact = solve(rules, mode="exact").house_edge
        assert he_auto == he_exact


class TestCombinatorialPinned:
    """Lock in combinatorial-mode HE for canonical small-deck rule sets.

    The combinatorial solver is the gold standard (single-pass enumeration
    with inline dealer evaluation, matches WoO Appendix 9 within rounding).
    Pinning its output for known rule sets catches future regressions in
    the combinatorial path -- the path that auto-mode now relies on for
    1-2 deck accuracy.
    """

    @pytest.mark.slow
    def test_one_deck_h17_pinned(self):
        """1-deck H17, no DAS, peek, LS, no-resplit, 3:2 BJ.

        Expected HE = 0.001235 (Wizard of Odds Appendix 9 publishes
        0.18% for the canonical 1-deck game; the variance with our
        no-resplit / no-DAS configuration is small).
        """
        rules = Rules(
            num_decks=1, dealer_hit_soft_17=True, allow_double_down=True,
            allow_split=True, allow_surrender=True, allow_late_surrender=True,
            allow_double_after_split=False, allow_resplitting=False,
            dealer_peek=True, blackjack_payout=1.5, penetration=0.75,
        )
        he = solve(rules, mode="combinatorial").house_edge
        assert abs(he - 0.001235) < 5e-6, (
            f"1-deck H17 combinatorial HE = {he:.6f}, expected ~0.001235. "
            f"This indicates a regression in the combinatorial solver path."
        )

    @pytest.mark.slow
    def test_two_deck_h17_pinned(self):
        """2-deck H17, no DAS, peek, LS, no-resplit, 3:2 BJ."""
        rules = Rules(
            num_decks=2, dealer_hit_soft_17=True, allow_double_down=True,
            allow_split=True, allow_surrender=True, allow_late_surrender=True,
            allow_double_after_split=False, allow_resplitting=False,
            dealer_peek=True, blackjack_payout=1.5, penetration=0.75,
        )
        he = solve(rules, mode="combinatorial").house_edge
        assert abs(he - 0.004823) < 5e-6, (
            f"2-deck H17 combinatorial HE = {he:.6f}, expected ~0.004823. "
            f"This indicates a regression in the combinatorial solver path."
        )

    @pytest.mark.slow
    def test_one_deck_s17_pinned(self):
        """1-deck S17, no DAS, peek, LS, no-resplit, 3:2 BJ.

        S17 with 1-deck and player-friendly rules tips slightly negative
        (player advantage) -- a known property of single-deck S17 games.
        """
        rules = Rules(
            num_decks=1, dealer_hit_soft_17=False, allow_double_down=True,
            allow_split=True, allow_surrender=True, allow_late_surrender=True,
            allow_double_after_split=False, allow_resplitting=False,
            dealer_peek=True, blackjack_payout=1.5, penetration=0.75,
        )
        he = solve(rules, mode="combinatorial").house_edge
        assert abs(he - (-0.000565)) < 5e-6, (
            f"1-deck S17 combinatorial HE = {he:.6f}, expected ~-0.000565. "
            f"This indicates a regression in the combinatorial solver path."
        )


class TestStrategyHouseEdge:
    """strategy_house_edge: the EV of playing the collapsed TD table.

    result.house_edge models composition-dependent (CD) play at the first
    decision; the simulator plays the total-dependent (TD) table. The TD
    edge is the simulator's true convergence target, so it must (a) never
    beat CD optimal, and (b) sit within the published CD-vs-TD strategy
    gap of it (sub-bp at 6 decks, a few bp at 1 deck).
    """

    def _rules(self, num_decks):
        return Rules(
            num_decks=num_decks, dealer_hit_soft_17=True,
            allow_double_down=True, allow_split=True, allow_surrender=True,
            allow_late_surrender=True, allow_double_after_split=True,
            allow_resplitting=False, dealer_peek=True, blackjack_payout=1.5,
            penetration=0.75,
        )

    def test_six_deck_td_dominated_and_close(self):
        rules = self._rules(6)
        sol = solve(rules, mode="fast")
        td = strategy_house_edge(sol, rules)
        diff = td - sol.house_edge
        assert diff >= -1e-12, "TD table cannot beat per-composition optimal"
        assert diff < 0.0002, (
            f"6-deck TD-vs-CD gap {diff*1e4:.2f} bp; expected < 2 bp"
        )

    def test_infinite_deck_td_equals_cd(self):
        """With no card-removal effects every composition of a total has
        identical EVs, so the TD table is exactly optimal."""
        rules = Rules(
            num_decks=99, dealer_hit_soft_17=True, allow_double_down=True,
            allow_split=True, allow_surrender=True, allow_late_surrender=True,
            dealer_peek=True, blackjack_payout=1.5,
        )
        sol = solve(rules)
        td = strategy_house_edge(sol, rules)
        assert abs(td - sol.house_edge) < 1e-9

    @pytest.mark.slow
    def test_one_deck_td_gap_within_published_range(self):
        rules = self._rules(1)
        sol = solve(rules, mode="combinatorial")
        td = strategy_house_edge(sol, rules)
        diff = td - sol.house_edge
        assert diff >= -1e-12
        # Wizard of Odds puts the total CD-strategy gain at single deck
        # around 4 bp; the first-decision share must be in that ballpark.
        assert diff < 0.0008, (
            f"1-deck TD-vs-CD gap {diff*1e4:.2f} bp; expected < 8 bp"
        )


class TestWoOReference:
    """Solver HE vs Wizard of Odds blackjack calculator (external reference).

    Values pulled directly from
    https://wizardofodds.com/games/blackjack/calculator/ via Playwright
    on 2026-05-12. WoO publishes 5-decimal HE for arbitrary rule sets
    under three strategy modes; we compare against "Optimal results"
    (perfect composition-dependent strategy + reshuffle every hand),
    which is the closest match to what our solver computes (per-(cv1,
    cv2, upcard) best_ev aggregated across deal probabilities, no
    cross-round shoe depletion).

    Rule set fixed across all rows:
        double-after-split=No, double-on=any, resplit-to=2 hands,
        resplit-aces=No, hit-split-aces=No, OBO=Yes, surrender=Late,
        blackjack=3:2

    Measured gaps to WoO Optimal at session pull:
        1d H17: -7.3 bp   1d S17: -1.0 bp
        2d H17: -0.4 bp
        6d H17: +0.4 bp   6d S17: -0.5 bp

    Tolerance is set to 10 bp (0.10%) -- comfortable margin above the
    7-bp 1-deck H17 outlier (see investigation notes below) without
    flaking on legitimate sub-bp drift. A regression that adds 20+ bp
    of bias will fail.

    1-deck H17 gap investigation (2026-05-12 / 13, cardsharp-nl4):
        The 7-bp gap is reproducible and *specific to 1-deck H17*. Both
        DAS and no-DAS variants show the same ~7-8 bp gap, ruling out a
        DAS-specific bug:
            1d H17 no-DAS LS:  HE 0.12350% (gap -7.3 bp)
            1d H17 DAS    LS:  HE -0.00848% (gap -7.95 bp)
        Combinatorial vs exact mode at 1d H17 no-DAS LS agree within
        3 bp (0.12350% vs 0.12660%); 4 bp of the gap is shared, 3 bp
        lives in combinatorial-vs-exact split-EV-structure differences.
        Strategy choices match WoO's published basic strategy chart.

        Four-stage investigation ruled out the obvious causes:
        1. Memoization in _dealer_probs is correct: a no-memo
           reimplementation gives identical dealer outcome
           distributions across multiple probe states.
        2. Per-action EVs (stand / hit / double / split) match an
           independent brute-force reimplementation EXACTLY (to 1e-10)
           across 13 sampled cells including high-impact, borderline,
           H17-sensitive, and pair states.
        3. Split EV path-dependence (where real hand 2 plays from a
           deck depleted by hand 1's hits, but our solver and brute
           force both use deck2) was tested for (8,8) vs 10: proper
           path-dependent EV is -0.46234 vs our -0.46252. The shift is
           1.8 bp in the WRONG direction relative to WoO -- a
           path-dependent fix would move our HE further below WoO,
           not closer. So path-dependence is not the source.
        4. Dealer outcome distribution under H17 soft-17 hits at 1-deck
           composition matches Monte Carlo (N=2M, SE ~3 bp per outcome)
           on 5 probe states including A-upcard-with-hole-6 in player-
           depleted decks. Our recursion produces the same dealer prob
           distribution as random card sampling.

        Tested ES vs LS surrender semantics (Theory #1 from spitball
        list): if WoO modeled LS surrender as ES (unconditional -0.5),
        our HE would move to -0.247%, which is 37 bp *further* from WoO,
        not closer. So ES theory is wrong — WoO is in fact MORE
        pessimistic than LS, not less. Our solver's LS treatment is
        correct and matches the standard rule definition.

        Working hypothesis at session end: WoO's JS calculator likely
        has a small 1-deck H17 imprecision that does not appear at 2+
        decks. Possible mechanism: borderline-cell action choice
        differences (e.g., where our solver surrenders (7,10) vs A at
        EV -0.5000 because hit/stand are -0.5039+ inferior, WoO may
        compute slightly different per-cell EVs and choose stand
        instead). Without their source code we can't verify, but our
        per-component verification (Stages 1-4 above) strongly suggests
        we are *more* accurate than WoO at 1-deck H17 rather than less.
        The gap shrinks to sub-bp at 2+ decks (where we match WoO
        within rounding) and is comfortably below the 10-bp test
        tolerance.
    """

    TOLERANCE = 0.0010  # 10 basis points

    def _rules(self, num_decks, h17):
        return Rules(
            num_decks=num_decks,
            dealer_hit_soft_17=h17,
            allow_double_down=True,
            allow_split=True,
            allow_double_after_split=False,
            allow_resplitting=False,
            allow_surrender=True,
            allow_late_surrender=True,
            dealer_peek=True,
            blackjack_payout=1.5,
        )

    # WoO calculator output for "Optimal results" (composition-dependent
    # strategy + reshuffle every hand), 2026-05-12.
    WOO_OPTIMAL = {
        (1, True): 0.0013076,   # 1-deck H17
        (1, False): -0.0004632,  # 1-deck S17
        (2, True): 0.0048575,   # 2-deck H17
        (6, True): 0.0070486,   # 6-deck H17
        (6, False): 0.0050619,  # 6-deck S17
    }

    @pytest.mark.slow
    @pytest.mark.parametrize("num_decks,h17,woo_he", [
        (decks, h17, he) for (decks, h17), he in sorted(WOO_OPTIMAL.items())
    ])
    def test_woo_optimal(self, num_decks, h17, woo_he):
        rules = self._rules(num_decks, h17)
        # mode="auto" picks combinatorial for ≤2 decks (the most accurate
        # path for small shoes) and fast for 5+ (where bias is already
        # < 5 bp). exact mode at 3-4 decks is too slow to include here.
        he = solve(rules, mode="auto").house_edge
        gap = he - woo_he
        rule_label = f"{num_decks}d {'H17' if h17 else 'S17'}"
        assert abs(gap) < self.TOLERANCE, (
            f"{rule_label}: solver HE = {he*100:.4f}%, "
            f"WoO Optimal = {woo_he*100:.4f}%, gap = {gap*100:+.4f}% "
            f"(tolerance 10 bp)."
        )
