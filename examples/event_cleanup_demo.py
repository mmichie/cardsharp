#!/usr/bin/env python3
"""
Example script demonstrating proper event handler cleanup in game shutdown methods.

This script shows how to test that all game types (Blackjack, War, High Card) properly 
clean up their event handlers when the shutdown method is called. For automated testing,
see tests/api/test_event_cleanup.py.
"""

import asyncio
import gc
import weakref
from typing import List, Dict, Any

# Import the game API classes
try:
    from cardsharp.api import BlackjackGame, WarGame, HighCardGame
    from cardsharp.adapters import DummyAdapter
    from cardsharp.events import EventBus, EngineEventType
except ImportError:
    print("ERROR: CardSharp package not found or incompletely installed.")
    print("Please ensure CardSharp is installed properly with: poetry install")
    import sys

    sys.exit(1)


# Track event handlers to verify cleanup
event_handler_refs = {"blackjack": [], "war": [], "high_card": []}


# Create handler functions for tracking
def create_event_handlers(game_type: str) -> List[callable]:
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
            print(f"{game_type} - {event.name} event received")

        # Keep a reference to track cleanup
        handlers.append(handler)
        # Store a weak reference to check if it gets cleaned up
        event_handler_refs[game_type].append(weakref.ref(handler))

    return handlers


async def test_game_cleanup(game_type: str):
    """Test event handler cleanup for a specific game type."""
    print(f"\n=== Testing {game_type.capitalize()} API Cleanup ===")

    # Create the game instance
    adapter = DummyAdapter()

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

    # Register our test handlers
    handlers = create_event_handlers(game_type)
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
        except Exception as e:
            print(f"Error during auto_play_round: {e}")
    elif game_type in ["war", "high_card"]:
        try:
            await game.play_round()
        except Exception as e:
            print(f"Error during play_round: {e}")

    # Check that we have event handlers registered
    print(f"Event handlers before shutdown: {len(game.event_handlers)}")

    # Shutdown the game - this should clean up event handlers
    await game.shutdown()

    # Check that handlers were cleaned up
    print(f"Event handlers after shutdown: {len(game.event_handlers)}")

    # Force garbage collection
    gc.collect()

    # Check if our weak references still point to live objects
    live_handlers = sum(1 for ref in event_handler_refs[game_type] if ref() is not None)
    print(f"Live handler references: {live_handlers}")

    # Return success or failure
    return len(game.event_handlers) == 0


async def main():
    """Run cleanup tests for all game types."""
    print("=== Event Handler Cleanup Test ===")

    results = {}

    # Test all game types
    for game_type in ["blackjack", "war", "high_card"]:
        try:
            success = await test_game_cleanup(game_type)
            results[game_type] = success
        except Exception as e:
            print(f"Error testing {game_type}: {e}")
            results[game_type] = False

    # Print summary
    print("\n=== Test Results ===")
    all_success = True
    for game_type, success in results.items():
        status = "PASSED" if success else "FAILED"
        print(f"{game_type.capitalize()}: {status}")
        all_success = all_success and success

    # Return exit code
    if all_success:
        print("\nAll tests passed successfully!")
        return 0
    else:
        print("\nSome tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    import sys

    sys.exit(exit_code)
