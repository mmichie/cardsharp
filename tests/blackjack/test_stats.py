import pytest
from unittest.mock import AsyncMock, Mock

from cardsharp.blackjack.stats import SimulationStats


# Test initializing SimulationStats
def test_simulation_stats_init():
    stats = SimulationStats()

    assert stats.games_played == 0
    assert stats.player_wins == 0
    assert stats.dealer_wins == 0
    assert stats.draws == 0


# Test updating SimulationStats
@pytest.mark.asyncio
async def test_simulation_stats_update():
    stats = SimulationStats()

    # Mock a game object
    mock_game = AsyncMock()
    mock_game.players = [Mock(winner=None), Mock(winner=None)]
    mock_game.io_interface = AsyncMock()

    # Run update once and check values
    await stats.update(mock_game)
    assert stats.games_played == 1
    assert stats.player_wins == 0
    assert stats.dealer_wins == 0
    assert stats.draws == 0

    # Set player 1 to win, run update, and check values
    mock_game.players[0].winner = "player"
    await stats.update(mock_game)
    assert stats.games_played == 2
    assert stats.player_wins == 1
    assert stats.dealer_wins == 0
    assert stats.draws == 0

    # Set dealer to win, run update, and check values
    mock_game.players[0].winner = "dealer"
    await stats.update(mock_game)
    assert stats.games_played == 3
    assert stats.player_wins == 1
    assert stats.dealer_wins == 1
    assert stats.draws == 0

    # Set draw, run update, and check values
    mock_game.players[0].winner = "draw"
    await stats.update(mock_game)
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
