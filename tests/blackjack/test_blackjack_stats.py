import pytest
from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.common.io_interface import DummyIOInterface
from cardsharp.common.util import calculate_chi_square


@pytest.fixture
def game():
    rules = {
        "blackjack_payout": 1.5,
        "allow_insurance": True,
        "min_players": 1,
        "min_bet": 10,
        "max_players": 6,
    }
    return BlackjackGame(rules, DummyIOInterface())


@pytest.mark.skip(reason="not running this test")
@pytest.mark.xfail
def test_blackjack_win_rate(game):
    num_rounds = 100
    expected_win_rate = (
        0.428  # The theoretical win rate of blackjack when using basic strategy
    )

    for _ in range(num_rounds):
        game.play_round()
        game.reset()

    stats = game.stats.report()
    observed_win_rate = stats["player_wins"] / num_rounds

    chi_square_stat = calculate_chi_square(
        [observed_win_rate * num_rounds, (1 - observed_win_rate) * num_rounds],
        [expected_win_rate * num_rounds, (1 - expected_win_rate) * num_rounds],
    )

    assert (
        chi_square_stat < 3.841
    ), f"Chi square statistic {chi_square_stat} is greater than critical value (3.841) at 0.05 significance level"
