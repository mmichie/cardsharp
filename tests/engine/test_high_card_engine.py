"""
Tests for the HighCardEngine class.

This module contains tests for the HighCardEngine class
to ensure it provides the expected behavior and correctly
implements the CardsharpEngine interface.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch
import time

from cardsharp.engine.high_card import HighCardEngine
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType, EventEmitter
from cardsharp.high_card.state import GameState, GameStage


@pytest.fixture
def high_card_engine():
    """Create a HighCardEngine instance for testing."""
    # Create a dummy adapter
    adapter = DummyAdapter()

    # Create a config for the engine
    config = {
        "shuffle_threshold": 5,
    }

    # Create a high card engine
    engine = HighCardEngine(adapter, config)
    return engine


def test_initialization(high_card_engine):
    """Test that the engine initializes correctly."""
    assert high_card_engine is not None
    assert high_card_engine.adapter is not None
    assert high_card_engine.config is not None
    assert high_card_engine.event_bus is not None
    assert high_card_engine.state is not None
    assert high_card_engine.shuffle_threshold == 5


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_initialize(mock_emit, high_card_engine):
    """Test that initialize sets up the engine correctly."""
    await high_card_engine.initialize()

    # Check that deck was initialized
    assert high_card_engine.deck is not None
    assert high_card_engine.deck.size == 52

    # Check that ENGINE_INIT event was emitted
    mock_emit.assert_called()
    args = mock_emit.call_args[0]
    assert args[0] == EngineEventType.ENGINE_INIT


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_shutdown(mock_emit, high_card_engine):
    """Test that shutdown emits the expected event."""
    await high_card_engine.shutdown()

    # Check that ENGINE_SHUTDOWN event was emitted
    mock_emit.assert_called()
    args = mock_emit.call_args[0]
    assert args[0] == EngineEventType.ENGINE_SHUTDOWN


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_start_game(mock_emit, high_card_engine):
    """Test that start_game sets up a new game correctly."""
    await high_card_engine.start_game()

    # Check that a new state was created
    assert high_card_engine.state is not None

    # Check that GAME_CREATED and GAME_STARTED events were emitted
    calls = [args[0] for args, _ in mock_emit.call_args_list]
    assert EngineEventType.GAME_CREATED in calls
    assert EngineEventType.GAME_STARTED in calls


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_add_player(mock_emit, high_card_engine):
    """Test that add_player adds a player correctly."""
    # Start a game
    await high_card_engine.start_game()

    # Add a player
    player_id = await high_card_engine.add_player("Test Player")

    # Check that the player was added
    assert len(high_card_engine.state.players) == 1
    assert high_card_engine.state.players[0].name == "Test Player"
    assert high_card_engine.state.players[0].id == player_id


@pytest.mark.asyncio
@patch.object(DummyAdapter, "render_game_state")
async def test_render_state(mock_render, high_card_engine):
    """Test that render_state calls the adapter's render_game_state method."""
    # Render the state
    await high_card_engine.render_state()

    # Check that render_game_state was called
    mock_render.assert_called_once()


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_play_round(mock_emit, high_card_engine):
    """Test that play_round plays a round correctly."""
    # Start a game
    await high_card_engine.start_game()

    # Add at least 2 players
    player1_id = await high_card_engine.add_player("Player 1")
    player2_id = await high_card_engine.add_player("Player 2")

    # Create an async mock for render_state
    async def mock_render_state():
        pass

    # Mock the render_state method to avoid UI interactions
    high_card_engine.render_state = mock_render_state

    # Play a round
    result = await high_card_engine.play_round()

    # Check that the result is a dictionary
    assert isinstance(result, dict)

    # Check that the state was updated to either COMPARING_CARDS or ROUND_ENDED
    assert high_card_engine.state.stage in (
        GameStage.COMPARING_CARDS,
        GameStage.ROUND_ENDED,
    )

    # Check that each player has a card
    for player in high_card_engine.state.players:
        assert player.card is not None

    # Check that a winner was determined
    assert high_card_engine.state.winner_id is not None


def test_deal_card(high_card_engine):
    """Test that _deal_card returns a card from the deck."""
    # Initialize the deck
    high_card_engine.deck.reset()
    high_card_engine.deck.shuffle()

    # Get the initial deck size
    initial_size = high_card_engine.deck.size

    # Deal a card
    card = high_card_engine._deal_card()

    # Check that a card was returned
    assert card is not None

    # Check that the deck size was decremented
    assert high_card_engine.deck.size == initial_size - 1


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
