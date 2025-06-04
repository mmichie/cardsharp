#!/usr/bin/env python3
"""
Demo script showcasing the BlackjackGame API implementation.

This script demonstrates how to use the BlackjackGame API, showing the interaction
with the BlackjackEngine and event handling system.
"""

import asyncio
from cardsharp.api import BlackjackGame
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType


# Storage for events received during the demo
events_received = []


def event_handler(data):
    """Handle events from the game."""
    # Store event data
    current_event = {"event_type": None, "data": data}
    events_received.append(current_event)

    # Extract data fields
    game_id = data.get("game_id", "unknown")
    timestamp = data.get("timestamp", 0)

    print(f"Event received: {current_event['event_type']}")

    # More detailed logging for specific events
    if "player_id" in data:
        print(
            f"  Player: {data.get('player_name', 'unknown')} ({data.get('player_id', 'unknown')})"
        )
    if "action" in data:
        print(f"  Action: {data.get('action', 'unknown')}")


async def run_demo():
    """Run the BlackjackGame API demo."""
    print("Starting BlackjackGame demo...")

    # Create a game with a DummyAdapter that doesn't require UI
    adapter = DummyAdapter()
    game = BlackjackGame(adapter=adapter, auto_play=True)

    # Get the event bus and register a handler for all events
    event_bus = EventBus.get_instance()

    # Register handlers for specific events
    unsubscribe_funcs = []
    for event_type in [
        EngineEventType.GAME_STARTED,
        EngineEventType.ROUND_STARTED,
        EngineEventType.PLAYER_JOINED,
        EngineEventType.PLAYER_BET,
        EngineEventType.PLAYER_ACTION,
        EngineEventType.ROUND_ENDED,
    ]:
        # Create a closure that captures the event type
        def make_handler(et):
            def handler(data):
                # Since we're capturing the event type in the closure, we can set it in the data
                current_event = {"event_type": et.name, "data": data}
                events_received.append(current_event)
                print(f"Event received: {et.name}")

                # More detailed logging for specific events
                if "player_id" in data:
                    print(
                        f"  Player: {data.get('player_name', 'unknown')} ({data.get('player_id', 'unknown')})"
                    )
                if "action" in data:
                    print(f"  Action: {data.get('action', 'unknown')}")

            return handler

        # Register handler for this specific event type
        handler = make_handler(event_type)
        unsubscribe = event_bus.on(event_type, handler)
        unsubscribe_funcs.append(unsubscribe)

    try:
        # Initialize the game
        print("Initializing game...")
        await game.initialize()

        # Start the game
        print("Starting game...")
        await game.start_game()

        # Add players
        print("Adding players...")
        player1 = await game.add_player("Alice", 1000.0)
        player2 = await game.add_player("Bob", 1000.0)

        # Play a round
        print("Playing a round...")
        result = await game.auto_play_round(default_bet=10.0)

        # Print the result
        print("\nRound result:")
        print(f"Game ID: {result.get('id', 'unknown')}")
        print(f"Round: {result.get('round_number', 0)}")
        print(f"Stage: {result.get('stage', 'unknown')}")

        # Print player information
        for player in result.get("players", []):
            print(f"Player: {player.get('name')} (ID: {player.get('id')})")
            print(f"  Balance: {player.get('balance', 0)}")
            for hand in player.get("hands", []):
                if hand.get("cards"):
                    cards = ", ".join(str(c) for c in hand.get("cards", []))
                    print(f"  Hand: {cards}")
                    print(f"  Value: {hand.get('value', 0)}")
                    print(f"  Bet: {hand.get('bet', 0)}")

        # Print dealer cards
        dealer = result.get("dealer", {})
        if dealer.get("hand") and dealer.get("hand").get("cards"):
            dealer_cards = ", ".join(
                str(c) for c in dealer.get("hand", {}).get("cards", [])
            )
            print(f"Dealer: {dealer_cards}")

        # Print event statistics
        print("\nEvents received:")
        event_types = set(e.get("event_type", "unknown") for e in events_received)
        for et in event_types:
            count = sum(1 for e in events_received if e.get("event_type") == et)
            print(f"  {et}: {count}")

        # Demonstrate event handler cleanup
        print("\nShutting down game...")
        await game.shutdown()

        # Verify that the event_handlers dictionary is empty
        print(f"Event handlers after shutdown: {len(game.event_handlers)}")

        # Test that unsubscribe works by manually unsubscribing the handlers
        for unsubscribe in unsubscribe_funcs:
            unsubscribe()

        print("Demo completed successfully!")

    except Exception as e:
        print(f"Error in demo: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_demo())
