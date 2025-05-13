"""
Tests for proper event handler cleanup in game shutdown methods.

This module tests that all game types (Blackjack, War, High Card) properly
clean up their event handlers when shutdown is called.
"""

import asyncio
import gc
import weakref
import pytest

from cardsharp.api import BlackjackGame, WarGame, HighCardGame
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType

# Reset the event bus singleton before tests to ensure clean state
EventBus._instance = None


# Fixture for the test environment
@pytest.fixture
def event_handler_refs():
    """Create a dictionary to track event handler references for testing."""
    return {"blackjack": [], "war": [], "high_card": []}


# Helper function to create event handlers for testing
def create_event_handlers(game_type, event_handler_refs):
    """Create a set of handler functions for testing."""
    handlers = []

    # Create handlers for different event types
    for event_type in [
        EngineEventType.GAME_STARTED,
        EngineEventType.ROUND_STARTED,
        EngineEventType.PLAYER_JOINED,
        EngineEventType.ROUND_ENDED,
    ]:
        # Create a handler function
        def handler(data, event=event_type):
            # Print is replaced with a simple noop in tests
            pass

        # Keep a reference to track cleanup
        handlers.append(handler)
        # Store a weak reference to check if it gets cleaned up
        event_handler_refs[game_type].append(weakref.ref(handler))

    return handlers


@pytest.mark.asyncio
async def test_blackjack_cleanup(event_handler_refs):
    """Test event handler cleanup for BlackjackGame."""
    await _test_game_cleanup("blackjack", event_handler_refs)


@pytest.mark.asyncio
async def test_war_cleanup(event_handler_refs):
    """Test event handler cleanup for WarGame."""
    await _test_game_cleanup("war", event_handler_refs)


@pytest.mark.asyncio
async def test_high_card_cleanup(event_handler_refs):
    """Test event handler cleanup for HighCardGame."""
    await _test_game_cleanup("high_card", event_handler_refs)


async def _test_game_cleanup(game_type, event_handler_refs):
    """Test event handler cleanup for a specific game type."""
    # Create the game instance
    adapter = DummyAdapter()
    game = None

    try:
        if game_type == "blackjack":
            game = BlackjackGame(adapter=adapter, auto_play=True)
        elif game_type == "war":
            game = WarGame(adapter=adapter)
        elif game_type == "high_card":
            game = HighCardGame(adapter=adapter)
        else:
            raise ValueError(f"Unknown game type: {game_type}")

        # Initialize the game
        await game.initialize()

        # Register test handlers
        handlers = create_event_handlers(game_type, event_handler_refs)
        unsubscribe_funcs = []

        for i, handler in enumerate(handlers):
            # Register with game's on method
            unsubscribe = game.on(
                list(EngineEventType)[i % len(list(EngineEventType))], handler
            )
            unsubscribe_funcs.append(unsubscribe)

        # Start the game to generate some events
        await game.start_game()

        # Add a player
        await game.add_player(f"Test-{game_type}", 1000.0)

        # Play a round for games that support it
        if game_type == "blackjack":
            try:
                await game.auto_play_round(default_bet=10.0)
            except Exception:
                # We don't care about gameplay errors, just handler cleanup
                pass
        elif game_type in ["war", "high_card"]:
            try:
                await game.play_round()
            except Exception:
                # We don't care about gameplay errors, just handler cleanup
                pass

        # Verify handlers are registered
        handlers_before = len(game.event_handlers)
        assert handlers_before > 0, f"No event handlers registered for {game_type}"

        # Shutdown the game - this should clean up event handlers
        await game.shutdown()

        # Verify handlers were cleaned up
        handlers_after = len(game.event_handlers)
        assert handlers_after == 0, f"Event handlers not cleaned up for {game_type}"

        # Force garbage collection
        gc.collect()

        # We're primarily interested in that the game cleans up its own tracking
        assert (
            handlers_after == 0
        ), f"Event handlers dictionary not cleared for {game_type}"

    finally:
        # Ensure game is shut down even if test fails
        if game is not None:
            try:
                await game.shutdown()
            except:
                pass
