"""
Tests for the UI integration with the engine pattern.

This module contains tests to verify that the UI components
work correctly with the engine pattern.
"""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch

from cardsharp.api import BlackjackGame
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType


@pytest.fixture
def dummy_adapter():
    """Provide a dummy adapter for testing."""
    return DummyAdapter()


@pytest.fixture
def received_events():
    """Track received events during tests."""
    return []


@pytest.mark.asyncio
async def test_game_initialization(dummy_adapter):
    """Test that the game can be initialized."""
    # Create a game instance
    game = BlackjackGame(adapter=dummy_adapter)

    try:
        # Initialize the game
        await game.initialize()

        # Verify that the game was initialized
        assert game.engine is not None
        assert game.adapter == dummy_adapter

        # Start the game
        await game.start_game()

        # Get the initial state
        state = await game.get_state()

        # Verify the initial state
        assert state.stage.name == "WAITING_FOR_PLAYERS"
    finally:
        # Shutdown the game
        await game.shutdown()


@pytest.mark.asyncio
async def test_player_management(dummy_adapter):
    """Test player management with the game."""
    # Create a game instance
    game = BlackjackGame(adapter=dummy_adapter)

    try:
        # Initialize the game
        await game.initialize()
        await game.start_game()

        # Add a player
        player_id = await game.add_player("Alice", 1000.0)

        # Verify the player was added
        state = await game.get_state()
        assert len(state.players) == 1
        assert state.players[0].name == "Alice"
        assert state.players[0].balance == 1000.0

        # Remove the player
        result = await game.remove_player(player_id)

        # Verify the player was removed
        assert result is True
        state = await game.get_state()
        assert len(state.players) == 0
    finally:
        # Shutdown the game
        await game.shutdown()


@pytest.mark.asyncio
async def test_game_flow(dummy_adapter):
    """Test the game flow with the engine pattern."""
    # Listen for events
    unsubscribe_funcs = []
    event_bus = EventBus.get_instance()

    # Create event handlers
    handlers = {
        EngineEventType.GAME_STARTED: MagicMock(),
        EngineEventType.PLAYER_JOINED: MagicMock(),
        EngineEventType.ROUND_STARTED: MagicMock(),
        EngineEventType.ROUND_ENDED: MagicMock(),
    }

    # Register event handlers
    for event_type, handler in handlers.items():
        unsubscribe = event_bus.on(event_type, handler)
        unsubscribe_funcs.append(unsubscribe)

    # Create a game instance with auto play
    game = BlackjackGame(adapter=dummy_adapter, auto_play=True)

    try:
        # Initialize the game
        await game.initialize()
        await game.start_game()

        # Verify GAME_STARTED event was emitted
        handlers[EngineEventType.GAME_STARTED].assert_called()

        # Add players
        player1 = await game.add_player("Alice", 1000.0)
        player2 = await game.add_player("Bob", 1000.0)

        # Verify PLAYER_JOINED events were emitted
        # Note: The event might be emitted multiple times due to internal operations
        assert handlers[EngineEventType.PLAYER_JOINED].call_count >= 2

        # Play a round
        result = await game.auto_play_round(default_bet=10.0)

        # Verify ROUND_STARTED and ROUND_ENDED events were emitted
        handlers[EngineEventType.ROUND_STARTED].assert_called()
        handlers[EngineEventType.ROUND_ENDED].assert_called()

        # Verify the result
        assert result is not None
        assert "players" in result
        assert len(result["players"]) == 2
    finally:
        # Unsubscribe event handlers
        for unsubscribe in unsubscribe_funcs:
            unsubscribe()

        # Shutdown the game
        await game.shutdown()


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
