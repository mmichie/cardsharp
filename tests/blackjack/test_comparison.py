"""Tests for CRN-based rule comparison."""

import pytest

from cardsharp.blackjack.comparison import compare_rules, PairedDiff
from cardsharp.blackjack.rules import Rules


def _base_rules(**overrides):
    """Standard 6-deck rules with optional overrides."""
    base = dict(
        num_decks=6,
        dealer_hit_soft_17=True,
        allow_double_down=True,
        allow_split=True,
        allow_double_after_split=False,
        allow_resplitting=False,
        dealer_peek=True,
        blackjack_payout=1.5,
        penetration=0.75,
        allow_surrender=True,
        allow_late_surrender=True,
    )
    base.update(overrides)
    return Rules(**base)


def test_paired_diff_welford_basic():
    """PairedDiff.update should yield correct sample mean and variance."""
    diff = PairedDiff()
    values = [0.1, -0.05, 0.2, 0.15, -0.08]
    for v in values:
        diff.update(v)
    expected_mean = sum(values) / len(values)
    expected_var = sum((v - expected_mean) ** 2 for v in values) / (
        len(values) - 1
    )
    assert diff.n == len(values)
    assert diff.mean == pytest.approx(expected_mean, rel=1e-12, abs=1e-12)
    assert diff.M2 / (diff.n - 1) == pytest.approx(expected_var, rel=1e-10, abs=1e-10)


def test_crn_identical_rules_yields_zero_diff():
    """Two copies of the same rule set must produce zero variance.

    This is the strongest CRN correctness test: when the rules are
    identical, both runs see the same shuffles AND make the same
    decisions, so every round's outcome must match exactly.
    """
    rules = _base_rules()
    result = compare_rules(
        {"A": rules, "B": _base_rules()}, num_rounds=300, seed=42
    )
    diff = result.paired_diffs[("A", "B")]
    assert diff.n == 300
    assert diff.mean == 0.0
    assert diff.M2 == 0.0


def test_crn_reproducibility():
    """Same seed must give identical comparison results."""
    rules_h17 = _base_rules(dealer_hit_soft_17=True)
    rules_s17 = _base_rules(dealer_hit_soft_17=False)

    r1 = compare_rules(
        {"H17": rules_h17, "S17": rules_s17}, num_rounds=200, seed=2026
    )
    r2 = compare_rules(
        {"H17": rules_h17, "S17": rules_s17}, num_rounds=200, seed=2026
    )

    for label in ("H17", "S17"):
        assert (
            r1.per_rule_stats[label].report()
            == r2.per_rule_stats[label].report()
        )
    diff_pair = ("H17", "S17")
    assert r1.paired_diffs[diff_pair].mean == r2.paired_diffs[diff_pair].mean
    assert r1.paired_diffs[diff_pair].M2 == r2.paired_diffs[diff_pair].M2


def test_crn_h17_higher_edge_than_s17():
    """H17 should have a higher house edge than S17 (rule of thumb)."""
    rules_h17 = _base_rules(dealer_hit_soft_17=True)
    rules_s17 = _base_rules(dealer_hit_soft_17=False)

    result = compare_rules(
        {"H17": rules_h17, "S17": rules_s17}, num_rounds=10_000, seed=99
    )
    diff = result.paired_diffs[("H17", "S17")]
    res = diff.confidence_interval(0.95)
    assert res is not None
    m, lo, hi, half = res
    # H17 worse for player -> HE(H17) > HE(S17) -> diff > 0
    # With 10K paired rounds the CRN CI is tight enough to confirm sign
    assert m > 0
    assert lo > -0.005  # likely positive at 95% confidence


def test_compare_rules_multi_player_runs():
    """Multi-player CRN comparison runs end-to-end and produces stats
    consistent with single-player (within shared CIs)."""
    pair = {
        "H17": _base_rules(dealer_hit_soft_17=True),
        "S17": _base_rules(dealer_hit_soft_17=False),
    }
    result_single = compare_rules(pair, num_rounds=2000, seed=42, num_players=1)
    result_multi = compare_rules(pair, num_rounds=2000, seed=42, num_players=3)

    # Both should produce non-zero variance in the H17-S17 diff
    assert result_single.paired_diffs[("H17", "S17")].M2 > 0
    assert result_multi.paired_diffs[("H17", "S17")].M2 > 0
    # Both should have the same number of rounds recorded
    assert result_single.per_rule_stats["H17"].n_rounds == 2000
    assert result_multi.per_rule_stats["H17"].n_rounds == 2000
    # Multi-player rounds aggregate 3 players' bets into the round-level
    # initial bet; bet_sum should be roughly 3x.
    bet_single = result_single.per_rule_stats["H17"].bet_sum
    bet_multi = result_multi.per_rule_stats["H17"].bet_sum
    assert bet_multi > 2.5 * bet_single  # Allow some slack for splits/doubles


def test_compare_rules_multi_player_reproducible():
    pair = {"H17": _base_rules(dealer_hit_soft_17=True),
            "S17": _base_rules(dealer_hit_soft_17=False)}
    r1 = compare_rules(pair, num_rounds=200, seed=2026, num_players=4)
    r2 = compare_rules(pair, num_rounds=200, seed=2026, num_players=4)
    for label in ("H17", "S17"):
        assert r1.per_rule_stats[label].report() == r2.per_rule_stats[label].report()


def test_crn_variance_lower_than_independent_estimate():
    """The CRN paired-diff variance should be much lower than the sum
    of per-rule variances (sanity check that CRN actually helps)."""
    rules_h17 = _base_rules(dealer_hit_soft_17=True)
    rules_s17 = _base_rules(dealer_hit_soft_17=False)

    result = compare_rules(
        {"H17": rules_h17, "S17": rules_s17}, num_rounds=3000, seed=7
    )
    n = 3000
    var_diff = result.paired_diffs[("H17", "S17")].M2 / (n - 1)

    # Per-rule per-round HE variance
    s_h17 = result.per_rule_stats["H17"]
    s_s17 = result.per_rule_stats["S17"]
    # Convert net-variance to per-bet-unit HE variance via /bet_mean^2
    var_he_h17 = (s_h17.net_M2 / (n - 1)) / (s_h17.bet_mean ** 2)
    var_he_s17 = (s_s17.net_M2 / (n - 1)) / (s_s17.bet_mean ** 2)

    # If H17 and S17 were independent, Var(diff) = Var(H17) + Var(S17).
    # Under CRN, Var(diff) should be a small fraction of that sum.
    independent_sum = var_he_h17 + var_he_s17
    assert var_diff < 0.5 * independent_sum, (
        f"CRN variance {var_diff:.6f} should be << "
        f"independent sum {independent_sum:.6f}"
    )
