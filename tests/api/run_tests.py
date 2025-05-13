#!/usr/bin/env python3
"""
Standalone test runner for API tests.

This script runs the API tests directly without using the pytest framework,
which might be causing lockups.
"""

import asyncio
import gc
import weakref
import sys
import time
from typing import Dict, Any, List

from cardsharp.api import BlackjackGame, WarGame, HighCardGame
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType


# --- Event Cleanup Tests ---


async def test_blackjack_cleanup():
    """Test event handler cleanup for BlackjackGame."""
    print("Testing BlackjackGame cleanup...")
    result = await _test_game_cleanup("blackjack")
    print(f"BlackjackGame cleanup test: {'PASSED' if result else 'FAILED'}")
    return result


async def test_war_cleanup():
    """Test event handler cleanup for WarGame."""
    print("Testing WarGame cleanup...")
    result = await _test_game_cleanup("war")
    print(f"WarGame cleanup test: {'PASSED' if result else 'FAILED'}")
    return result


async def test_high_card_cleanup():
    """Test event handler cleanup for HighCardGame."""
    print("Testing HighCardGame cleanup...")
    result = await _test_game_cleanup("high_card")
    print(f"HighCardGame cleanup test: {'PASSED' if result else 'FAILED'}")
    return result


async def _test_game_cleanup(game_type):
    """Test event handler cleanup for a specific game type."""
    # Track event handlers with weak references
    handlers = []
    handler_refs = []

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

    try:
        # Initialize the game
        await game.initialize()

        # Create handlers for different event types
        for event_type in [
            EngineEventType.GAME_STARTED,
            EngineEventType.ROUND_STARTED,
            EngineEventType.PLAYER_JOINED,
            EngineEventType.ROUND_ENDED,
        ]:
            # Create a handler function
            def make_handler(et):
                def handler(data):
                    # Just a no-op in the test
                    pass

                return handler

            handler = make_handler(event_type)
            handlers.append(handler)
            handler_refs.append(weakref.ref(handler))

            # Register with game's on method
            game.on(event_type, handler)

        # Start the game to generate some events
        await game.start_game()

        # Add a player
        await game.add_player(f"Test-{game_type}", 1000.0)

        # Play a round for games that support it
        if game_type == "blackjack":
            try:
                await game.auto_play_round(default_bet=10.0)
            except Exception as e:
                print(f"Warning: Error during auto_play_round: {e}")
        elif game_type in ["war", "high_card"]:
            try:
                await game.play_round()
            except Exception as e:
                print(f"Warning: Error during play_round: {e}")

        # Verify handlers are registered
        handlers_before = len(game.event_handlers)
        if handlers_before == 0:
            print(f"ERROR: No event handlers registered for {game_type}")
            return False

        # Shutdown the game - this should clean up event handlers
        await game.shutdown()

        # Verify handlers were cleaned up
        handlers_after = len(game.event_handlers)
        if handlers_after != 0:
            print(
                f"ERROR: Event handlers not cleaned up for {game_type} (found {handlers_after})"
            )
            return False

        # Force garbage collection
        gc.collect()

        # We're primarily interested in that the game cleans up its own tracking
        return handlers_after == 0

    except Exception as e:
        print(f"ERROR in {game_type} test: {e}")
        return False


# --- BlackjackGame Tests ---


async def test_blackjack_game_lifecycle():
    """Test the full lifecycle of a BlackjackGame."""
    print("Testing BlackjackGame lifecycle...")

    # Storage for received events
    events_received = []

    # Create the game
    adapter = DummyAdapter()
    game = BlackjackGame(adapter=adapter, auto_play=True)

    # Set up event handlers
    event_bus = EventBus.get_instance()
    unsubscribe_funcs = []

    for event_type in [
        EngineEventType.GAME_STARTED,
        EngineEventType.ROUND_STARTED,
        EngineEventType.PLAYER_JOINED,
        EngineEventType.PLAYER_BET,
        EngineEventType.PLAYER_ACTION,
        EngineEventType.ROUND_ENDED,
    ]:

        def make_handler(et):
            def handler(data):
                # Just record the event
                events_received.append((et.name, data))

            return handler

        handler = make_handler(event_type)
        unsubscribe = event_bus.on(event_type, handler)
        unsubscribe_funcs.append(unsubscribe)

    try:
        # Initialize and start
        await game.initialize()
        await game.start_game()

        # Add players
        player1 = await game.add_player("Alice", 1000.0)
        player2 = await game.add_player("Bob", 1000.0)

        # Play a round
        result = await game.auto_play_round(default_bet=10.0)

        # Verify the result
        if "id" not in result:
            print("ERROR: Game result missing id")
            return False

        if "round_number" not in result:
            print("ERROR: Game result missing round_number")
            return False

        if "players" not in result:
            print("ERROR: Game result missing players")
            return False

        if len(result["players"]) < 2:
            print(f"ERROR: Expected at least 2 players, got {len(result['players'])}")
            return False

        # Check events
        event_types = {et for et, _ in events_received}

        if "GAME_STARTED" not in event_types:
            print("ERROR: Missing GAME_STARTED event")
            return False

        if "PLAYER_JOINED" not in event_types:
            print("ERROR: Missing PLAYER_JOINED event")
            return False

        if "ROUND_STARTED" not in event_types:
            print("ERROR: Missing ROUND_STARTED event")
            return False

        # Shutdown
        await game.shutdown()

        # Verify event handlers are cleaned up
        if len(game.event_handlers) != 0:
            print(
                f"ERROR: Event handlers not cleaned up (found {len(game.event_handlers)})"
            )
            return False

        print("BlackjackGame lifecycle test: PASSED")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        return False
    finally:
        # Clean up
        for unsubscribe in unsubscribe_funcs:
            unsubscribe()


async def test_blackjack_player_management():
    """Test player management in BlackjackGame."""
    print("Testing BlackjackGame player management...")

    # Create the game
    adapter = DummyAdapter()
    game = BlackjackGame(adapter=adapter, auto_play=False)

    try:
        # Initialize and start
        await game.initialize()
        await game.start_game()

        # Add a player
        player_id = await game.add_player("TestPlayer", 1000.0)

        # Verify player was added
        state = await game.get_state()
        player_ids = [p.id for p in state.players]

        if player_id not in player_ids:
            print("ERROR: Player was not added correctly")
            return False

        # Test player removal if supported
        try:
            removed = await game.remove_player(player_id)
            if removed:
                state = await game.get_state()
                player_ids = [p.id for p in state.players]
                if player_id in player_ids:
                    print("ERROR: Player was not removed correctly")
                    return False
        except (AttributeError, NotImplementedError):
            # Some implementations might not support player removal
            pass

        print("BlackjackGame player management test: PASSED")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        return False
    finally:
        # Clean up
        await game.shutdown()


async def test_blackjack_betting():
    """Test betting functionality in BlackjackGame."""
    print("Testing BlackjackGame betting...")

    # Create the game
    adapter = DummyAdapter()
    game = BlackjackGame(adapter=adapter, auto_play=False)

    try:
        # Initialize and start
        await game.initialize()
        await game.start_game()

        # Add a player
        player_id = await game.add_player("BettingPlayer", 1000.0)

        # Get initial balance
        state = await game.get_state()
        player = None
        for p in state.players:
            if p.id == player_id:
                player = p
                break

        if player is None:
            print("ERROR: Player not found after adding")
            return False

        initial_balance = player.balance

        # Place a bet
        bet_amount = 50.0
        success = await game.place_bet(player_id, bet_amount)

        if not success:
            print("ERROR: Failed to place bet")
            return False

        # Get updated state
        state = await game.get_state()

        # Find the player again
        player = None
        for p in state.players:
            if p.id == player_id:
                player = p
                break

        if player is None:
            print("ERROR: Player not found after betting")
            return False

        # Verify the player's balance has been reduced
        if player.balance != initial_balance - bet_amount:
            print(
                f"ERROR: Expected balance {initial_balance - bet_amount}, got {player.balance}"
            )
            return False

        print("BlackjackGame betting test: PASSED")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        return False
    finally:
        # Clean up
        await game.shutdown()


async def run_all_tests():
    """Run all tests and report results."""
    print("=== Running Cardsharp API Tests ===\n")
    start_time = time.time()

    tests = [
        ("BlackjackGame Cleanup", test_blackjack_cleanup),
        ("WarGame Cleanup", test_war_cleanup),
        ("HighCardGame Cleanup", test_high_card_cleanup),
        ("BlackjackGame Lifecycle", test_blackjack_game_lifecycle),
        ("BlackjackGame Player Management", test_blackjack_player_management),
        ("BlackjackGame Betting", test_blackjack_betting),
    ]

    results = {}

    for name, test_func in tests:
        print(f"\nRunning test: {name}")
        try:
            result = await test_func()
            results[name] = result
        except Exception as e:
            print(f"ERROR: Test {name} raised exception: {e}")
            results[name] = False

    end_time = time.time()
    duration = end_time - start_time

    # Print summary
    print("\n=== Test Results ===")
    all_passed = True
    for name, result in results.items():
        status = "PASSED" if result else "FAILED"
        print(f"{name}: {status}")
        if not result:
            all_passed = False

    print(f"\nCompleted {len(tests)} tests in {duration:.2f}s")
    print(f"Overall status: {'PASSED' if all_passed else 'FAILED'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
