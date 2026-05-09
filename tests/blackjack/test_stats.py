import math
import random
from unittest.mock import Mock

import pytest

from cardsharp.blackjack.stats import SimulationStats


# Test initializing SimulationStats
def test_simulation_stats_init():
    stats = SimulationStats()

    assert stats.games_played == 0
    assert stats.player_wins == 0
    assert stats.dealer_wins == 0
    assert stats.draws == 0
    assert stats.n_rounds == 0
    assert stats.net_mean == 0.0
    assert stats.net_M2 == 0.0
    assert stats.bet_mean == 0.0
    assert stats.bet_M2 == 0.0
    assert stats.net_bet_C == 0.0


# Test updating SimulationStats
def test_simulation_stats_update():
    stats = SimulationStats()

    # Mock a game object
    mock_game = Mock()
    mock_game.players = [
        Mock(winner=[]),
        Mock(winner=[]),
    ]  # Set winner to an empty list
    mock_game.io_interface = Mock()
    mock_game.io_interface.output = Mock()  # Mock the output method if needed

    # Run update once and check values
    stats.update(mock_game)
    assert stats.games_played == 1
    assert stats.player_wins == 0
    assert stats.dealer_wins == 0
    assert stats.draws == 0

    # Set player 1 to win, run update, and check values
    mock_game.players[0].winner = ["player"]  # Set winner to a list containing "player"
    stats.update(mock_game)
    assert stats.games_played == 2
    assert stats.player_wins == 1
    assert stats.dealer_wins == 0
    assert stats.draws == 0

    # Set dealer to win, run update, and check values
    mock_game.players[0].winner = ["dealer"]
    stats.update(mock_game)
    assert stats.games_played == 3
    assert stats.player_wins == 1
    assert stats.dealer_wins == 1
    assert stats.draws == 0

    # Set draw, run update, and check values
    mock_game.players[0].winner = ["draw"]
    stats.update(mock_game)
    assert stats.games_played == 4
    assert stats.player_wins == 1
    assert stats.dealer_wins == 1
    assert stats.draws == 1


# Test report method
def test_simulation_stats_report():
    stats = SimulationStats()
    stats.games_played = 5
    stats.player_wins = 2
    stats.dealer_wins = 1
    stats.draws = 2

    report = stats.report()
    assert report["games_played"] == 5
    assert report["player_wins"] == 2
    assert report["dealer_wins"] == 1
    assert report["draws"] == 2
    # New keys for variance accumulation
    assert report["n_rounds"] == 0
    assert report["net_mean"] == 0.0
    assert report["net_M2"] == 0.0


# ---------------------------------------------------------------------------
# Welford accumulator correctness
# ---------------------------------------------------------------------------


def _direct_moments(values):
    """Compute mean and sum-of-squared-deviations directly (two-pass)."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    M2 = sum((v - mean) ** 2 for v in values)
    return mean, M2


def _direct_co_moment(xs, ys):
    """Sum (x_i - mean_x)(y_i - mean_y) directly."""
    assert len(xs) == len(ys)
    n = len(xs)
    if n == 0:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys))


def test_record_round_matches_direct_computation():
    """Welford-accumulated mean/M2 must match a direct two-pass calc."""
    rng = random.Random(0xC0FFEE)
    nets = [rng.gauss(-0.5, 1.0) for _ in range(500)]
    bets = [10.0 + rng.choice([0.0, 5.0, 10.0]) for _ in range(500)]

    stats = SimulationStats()
    for n, b in zip(nets, bets):
        # total_bet just stresses the third aggregate; fold doubles in
        stats.record_round(n, b, b * rng.choice([1.0, 2.0]))

    expected_net_mean, expected_net_M2 = _direct_moments(nets)
    expected_bet_mean, expected_bet_M2 = _direct_moments(bets)
    expected_C = _direct_co_moment(nets, bets)

    assert stats.n_rounds == 500
    assert stats.net_mean == pytest.approx(expected_net_mean, rel=1e-12, abs=1e-12)
    assert stats.bet_mean == pytest.approx(expected_bet_mean, rel=1e-12, abs=1e-12)
    assert stats.net_M2 == pytest.approx(expected_net_M2, rel=1e-10, abs=1e-10)
    assert stats.bet_M2 == pytest.approx(expected_bet_M2, rel=1e-10, abs=1e-10)
    assert stats.net_bet_C == pytest.approx(expected_C, rel=1e-10, abs=1e-10)


def test_merge_matches_single_pass():
    """Splitting a sample, accumulating each half, then merging must equal
    the single-pass accumulation."""
    rng = random.Random(2025)
    nets = [rng.gauss(-0.5, 1.0) for _ in range(1000)]
    bets = [10.0 + rng.choice([0.0, 5.0]) for _ in range(1000)]

    full = SimulationStats()
    for n, b in zip(nets, bets):
        full.record_round(n, b, b)

    # Asymmetric split (300 / 700) to stress the n_a != n_b path.
    a = SimulationStats()
    for n, b in zip(nets[:300], bets[:300]):
        a.record_round(n, b, b)
    b_ = SimulationStats()
    for n, b in zip(nets[300:], bets[300:]):
        b_.record_round(n, b, b)
    a.merge(b_)

    assert a.n_rounds == full.n_rounds
    assert a.net_mean == pytest.approx(full.net_mean, rel=1e-12, abs=1e-12)
    assert a.bet_mean == pytest.approx(full.bet_mean, rel=1e-12, abs=1e-12)
    # Sample-variance error growth requires looser tolerance than means
    assert a.net_M2 == pytest.approx(full.net_M2, rel=1e-9, abs=1e-9)
    assert a.bet_M2 == pytest.approx(full.bet_M2, rel=1e-9, abs=1e-9)
    assert a.net_bet_C == pytest.approx(full.net_bet_C, rel=1e-9, abs=1e-9)


def test_merge_into_empty_and_from_empty():
    """Merging with an empty accumulator preserves state on either side."""
    rng = random.Random(7)
    populated = SimulationStats()
    for _ in range(50):
        populated.record_round(rng.gauss(0, 1), 10.0, 10.0)

    snapshot = populated.report()

    # Merge empty into populated -> unchanged
    populated.merge(SimulationStats())
    assert populated.report() == snapshot

    # Merge populated into empty -> equals populated
    empty = SimulationStats()
    empty.merge(SimulationStats.from_dict(snapshot))
    for k, v in snapshot.items():
        assert empty.report()[k] == pytest.approx(v, rel=1e-12, abs=1e-12)


def test_from_dict_round_trip():
    """report() / from_dict() must round-trip exactly."""
    s = SimulationStats()
    rng = random.Random(99)
    for _ in range(20):
        s.record_round(rng.gauss(0, 1), 10.0, 15.0)
    s.player_wins = 7
    s.dealer_wins = 11
    s.draws = 2
    s.games_played = 20

    rebuilt = SimulationStats.from_dict(s.report())
    assert rebuilt.report() == s.report()


# ---------------------------------------------------------------------------
# Confidence intervals
# ---------------------------------------------------------------------------


def test_house_edge_ci_centered_on_estimate():
    """The CI must be symmetric around the point estimate."""
    rng = random.Random(123)
    s = SimulationStats()
    for _ in range(200):
        s.record_round(rng.gauss(-0.05, 1.0), 10.0, 10.0)

    he, lo, hi, half = s.house_edge_with_ci(0.95)
    assert math.isclose(he - lo, half, rel_tol=1e-12)
    assert math.isclose(hi - he, half, rel_tol=1e-12)


def test_house_edge_ci_shrinks_with_n():
    """Increasing N by 4x should roughly halve the CI half-width."""
    rng = random.Random(456)

    def run(n):
        s = SimulationStats()
        for _ in range(n):
            s.record_round(rng.gauss(-0.05, 1.0), 10.0, 10.0)
        return s.house_edge_with_ci(0.95)[3]

    half_small = run(2_000)
    half_large = run(8_000)
    # Expected ratio is ~2 (sqrt(4)); allow generous tolerance for noise
    ratio = half_small / half_large
    assert 1.5 < ratio < 2.7, f"CI width should ~halve with 4x N, got ratio {ratio}"


def test_house_edge_ci_returns_none_with_insufficient_data():
    s = SimulationStats()
    assert s.house_edge_with_ci() is None
    s.record_round(-1.0, 10.0, 10.0)
    # n=1: cannot estimate variance
    assert s.house_edge_with_ci() is None


def test_house_edge_ci_with_constant_bets_matches_simple_formula():
    """When bets are constant, delta-method CI must equal the simple
    Var(net)/n / bet^2 form (no covariance/bet-variance contribution)."""
    rng = random.Random(789)
    s = SimulationStats()
    bet = 10.0
    nets = [rng.gauss(-0.05, 1.2) for _ in range(500)]
    for n in nets:
        s.record_round(n, bet, bet)

    he, lo, hi, half = s.house_edge_with_ci(0.95)

    # Direct: var(net)/n /bet^2; z=1.96 -> ~1.95996...
    var_net = sum((x - sum(nets) / len(nets)) ** 2 for x in nets) / (len(nets) - 1)
    expected_se = math.sqrt(var_net / len(nets)) / bet
    expected_half = 1.959963984540054 * expected_se
    assert half == pytest.approx(expected_half, rel=1e-6)


def test_win_rate_ci_wilson_basic_properties():
    s = SimulationStats()
    s.player_wins = 45
    s.dealer_wins = 55
    p, lo, hi, half = s.win_rate_with_ci(0.95)
    assert p == 0.45
    assert lo < p < hi
    # Wilson interval shouldn't extend below 0 or above 1
    assert 0.0 <= lo
    assert hi <= 1.0
