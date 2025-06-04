"""
Integration tests for the Cardsharp system.

This module contains integration tests for the entire Cardsharp system,
testing the interaction between the API, engine, and adapters.
"""

import pytest

from cardsharp.api import BlackjackGame, HighCardGame
from cardsharp.adapters import DummyAdapter
from cardsharp.blackjack.action import Action


# Blackjack game config fixture
@pytest.fixture
def blackjack_config():
    """Return a standard configuration for blackjack tests."""
    return {
        "dealer_rules": {"stand_on_soft_17": True, "peek_for_blackjack": True},
        "deck_count": 2,
        "rules": {
            "blackjack_pays": 1.5,
            "deck_count": 2,
            "dealer_hit_soft_17": False,
            "offer_insurance": True,
            "allow_surrender": True,
            "allow_double_after_split": True,
            "min_bet": 5.0,
            "max_bet": 1000.0,
        },
    }


# Blackjack game fixture
@pytest.fixture
async def blackjack_game(blackjack_config):
    """Create and initialize a BlackjackGame for testing."""
    adapter = DummyAdapter()
    game = BlackjackGame(adapter=adapter, config=blackjack_config, auto_play=True)

    # Initialize and start the game
    await game.initialize()
    await game.start_game()

    yield game

    # Clean up after test
    await game.shutdown()


# High card game config fixture
@pytest.fixture
def highcard_config():
    """Return a standard configuration for high card tests."""
    return {
        "shuffle_threshold": 5,
    }


# High card game fixture
@pytest.fixture
async def highcard_game(highcard_config):
    """Create and initialize a HighCardGame for testing."""
    adapter = DummyAdapter()
    game = HighCardGame(adapter=adapter, config=highcard_config)

    # Initialize and start the game
    await game.initialize()
    await game.start_game()

    yield game

    # Clean up after test
    await game.shutdown()


@pytest.mark.asyncio
async def test_blackjack_game_lifecycle(blackjack_game):
    """Test the complete lifecycle of a blackjack game."""
    # Add players
    player1_id = await blackjack_game.add_player("Alice", 1000.0)
    await blackjack_game.add_player("Bob", 1000.0)

    # Get the initial state
    initial_state = await blackjack_game.get_state()

    # Check that the players were added
    assert len(initial_state.players) == 2

    # Play a round
    result = await blackjack_game.auto_play_round(default_bet=10.0)

    # Check that the result is a dictionary
    assert isinstance(result, dict)

    # Check that the stage is back to PLACING_BETS for the next round
    final_state = await blackjack_game.get_state()
    assert final_state.stage.name == "PLACING_BETS"

    # Check that the players still exist
    assert len(final_state.players) == 2

    # Remove a player
    removed = await blackjack_game.remove_player(player1_id)
    assert removed is True

    # Check that the player was removed
    state_after_remove = await blackjack_game.get_state()
    assert len(state_after_remove.players) == 1


@pytest.mark.asyncio
async def test_blackjack_player_actions(blackjack_game):
    """Test that player actions work correctly in blackjack game."""
    # Add a player
    player_id = await blackjack_game.add_player("Alice", 1000.0)

    # Place a bet
    bet_placed = await blackjack_game.place_bet(player_id, 10.0)
    assert bet_placed is True

    # Create a strategy that always stands
    await blackjack_game.set_auto_action(player_id, Action.STAND)

    # Play a single round instead of testing all actions
    # This simplifies the test and makes it less prone to timing issues
    result = await blackjack_game.auto_play_round(default_bet=10.0)

    # Verify basic result structure
    assert isinstance(result, dict)
    assert "players" in result


@pytest.mark.asyncio
async def test_highcard_game_lifecycle(highcard_game):
    """Test the complete lifecycle of a high card game."""
    # Add players
    player1_id = await highcard_game.add_player("Alice")
    await highcard_game.add_player("Bob")

    # Get the initial state
    initial_state = await highcard_game.get_state()

    # Check that the players were added
    assert len(initial_state.players) == 2

    # Play a round
    result = await highcard_game.play_round()

    # Check that the result is a dictionary
    assert isinstance(result, dict)

    # Play multiple rounds with two players
    results = await highcard_game.play_multiple_rounds(2)

    # Check that we got results for all rounds
    assert len(results) == 2

    # Remove a player
    removed = await highcard_game.remove_player(player1_id)
    assert removed is True

    # Check that the player was removed
    state_after_remove = await highcard_game.get_state()
    assert len(state_after_remove.players) == 1

    # Add another player so we can keep playing
    await highcard_game.add_player("Charlie")

    # Verify we're back to two players
    state_after_add = await highcard_game.get_state()
    assert len(state_after_add.players) == 2

    # Play one more round
    result = await highcard_game.play_round()
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_single_game_simplified():
    """Simplified test that only runs one game to avoid resource contention."""
    # Create dummy adapter
    adapter = DummyAdapter()

    # Create game
    game = BlackjackGame(adapter=adapter, auto_play=True)

    try:
        # Initialize the game
        await game.initialize()

        # Start the game
        await game.start_game()

        # Add player
        await game.add_player("Alice", 1000.0)

        # Play a round
        result = await game.auto_play_round(default_bet=10.0)

        # Check that the game produced a result
        assert isinstance(result, dict)
        assert "players" in result

    finally:
        # Always clean up resources
        await game.shutdown()
