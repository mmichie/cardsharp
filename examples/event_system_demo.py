#!/usr/bin/env python3
"""
Example demonstrating the use of the new event system.

This script shows how to use the EventEmitter, EventBus, and event subscription
to create a simple game event flow.
"""

import time
import asyncio

# Check if cardsharp is installed properly
try:
    from cardsharp.events import EventEmitter, EventBus, EngineEventType, EventPriority
except ImportError:
    print("ERROR: CardSharp package not found or incompletely installed.")
    print("Please ensure CardSharp is installed properly with: uv sync")
    import sys

    sys.exit(1)


async def main():
    # Get the global event bus
    event_bus = EventBus.get_instance()

    # Define event handlers
    def on_game_created(data):
        print(f"\nGame created: {data['game_id']}")

    def on_player_joined(data):
        print(f"Player joined: {data['player_name']} (ID: {data['player_id']})")

    def on_round_started(data):
        print(f"\n--- Round {data['round_number']} started ---")

    def on_card_dealt(data):
        recipient = data.get("player_name", "Dealer")
        print(f"Card dealt: {data['card']} to {recipient}")

    def on_player_action(data):
        print(f"Player action: {data['player_name']} chose {data['action']}")

    def on_hand_result(data):
        result = data.get("result", "unknown")
        player = data.get("player_name", "Unknown player")
        print(f"Hand result: {player} - {result}")

    def on_any_event(event_data):
        event_type, data = event_data
        # Only log certain events to avoid cluttering the output
        if event_type not in ["CARD_DEALT", "PLAYER_ACTION"]:
            print(f"[Event log] {event_type}: {data}")

    # Subscribe to events
    event_bus.on(EngineEventType.GAME_CREATED, on_game_created)
    event_bus.on(EngineEventType.PLAYER_JOINED, on_player_joined)
    event_bus.on(EngineEventType.ROUND_STARTED, on_round_started)
    event_bus.on(EngineEventType.CARD_DEALT, on_card_dealt)
    event_bus.on(EngineEventType.PLAYER_ACTION, on_player_action)
    event_bus.on(EngineEventType.HAND_RESULT, on_hand_result)

    # Subscribe to all events with lower priority
    event_bus.on_any(on_any_event, EventPriority.LOW)

    # Simulate a game
    game_id = f"game_{int(time.time())}"

    # Create a game
    event_bus.emit(
        EngineEventType.GAME_CREATED,
        {
            "game_id": game_id,
            "timestamp": time.time(),
            "rules": {"decks": 6, "blackjack_payout": 1.5},
        },
    )

    # Add players
    for i, name in enumerate(["Alice", "Bob", "Charlie"]):
        player_id = f"player_{i+1}"
        event_bus.emit(
            EngineEventType.PLAYER_JOINED,
            {
                "game_id": game_id,
                "player_id": player_id,
                "player_name": name,
                "balance": 1000.0,
                "timestamp": time.time(),
            },
        )

    # Start a round
    round_id = f"{game_id}_round_1"
    event_bus.emit(
        EngineEventType.ROUND_STARTED,
        {
            "game_id": game_id,
            "round_id": round_id,
            "round_number": 1,
            "timestamp": time.time(),
        },
    )

    # Players place bets
    for i, name in enumerate(["Alice", "Bob", "Charlie"]):
        player_id = f"player_{i+1}"
        bet_amount = (i + 1) * 10  # Different bet amounts
        event_bus.emit(
            EngineEventType.PLAYER_BET,
            {
                "game_id": game_id,
                "round_id": round_id,
                "player_id": player_id,
                "player_name": name,
                "amount": bet_amount,
                "timestamp": time.time(),
            },
        )

    # Deal initial cards
    # First, dealer gets a card
    event_bus.emit(
        EngineEventType.CARD_DEALT,
        {
            "game_id": game_id,
            "round_id": round_id,
            "is_dealer": True,
            "card": "A♠",
            "timestamp": time.time(),
        },
    )

    # Players get their first cards
    for i, name in enumerate(["Alice", "Bob", "Charlie"]):
        player_id = f"player_{i+1}"
        cards = ["J♥", "Q♦", "K♣"][i]
        event_bus.emit(
            EngineEventType.CARD_DEALT,
            {
                "game_id": game_id,
                "round_id": round_id,
                "player_id": player_id,
                "player_name": name,
                "card": cards,
                "is_dealer": False,
                "timestamp": time.time(),
            },
        )

        # Small delay for better visualization
        await asyncio.sleep(0.2)

    # Dealer gets second card (hole card)
    event_bus.emit(
        EngineEventType.CARD_DEALT,
        {
            "game_id": game_id,
            "round_id": round_id,
            "is_dealer": True,
            "card": "10♥",
            "is_hole_card": True,
            "timestamp": time.time(),
        },
    )

    # Players get their second cards
    for i, name in enumerate(["Alice", "Bob", "Charlie"]):
        player_id = f"player_{i+1}"
        cards = ["9♥", "10♦", "A♣"][i]
        event_bus.emit(
            EngineEventType.CARD_DEALT,
            {
                "game_id": game_id,
                "round_id": round_id,
                "player_id": player_id,
                "player_name": name,
                "card": cards,
                "is_dealer": False,
                "timestamp": time.time(),
            },
        )

        # Small delay for better visualization
        await asyncio.sleep(0.2)

    # Player actions
    # Alice has 19, stands
    event_bus.emit(
        EngineEventType.PLAYER_ACTION,
        {
            "game_id": game_id,
            "round_id": round_id,
            "player_id": "player_1",
            "player_name": "Alice",
            "action": "STAND",
            "timestamp": time.time(),
        },
    )

    # Bob has 20, stands
    event_bus.emit(
        EngineEventType.PLAYER_ACTION,
        {
            "game_id": game_id,
            "round_id": round_id,
            "player_id": "player_2",
            "player_name": "Bob",
            "action": "STAND",
            "timestamp": time.time(),
        },
    )

    # Charlie has A+K (blackjack)
    event_bus.emit(
        EngineEventType.PLAYER_ACTION,
        {
            "game_id": game_id,
            "round_id": round_id,
            "player_id": "player_3",
            "player_name": "Charlie",
            "action": "STAND",
            "hand_value": 21,
            "is_blackjack": True,
            "timestamp": time.time(),
        },
    )

    # Dealer reveals hole card and it's a blackjack
    event_bus.emit(
        EngineEventType.CARD_REVEALED,
        {
            "game_id": game_id,
            "round_id": round_id,
            "is_dealer": True,
            "card": "10♥",
            "timestamp": time.time(),
        },
    )

    # Hand results
    # Alice loses to dealer blackjack
    event_bus.emit(
        EngineEventType.HAND_RESULT,
        {
            "game_id": game_id,
            "round_id": round_id,
            "player_id": "player_1",
            "player_name": "Alice",
            "result": "lose",
            "timestamp": time.time(),
        },
    )

    # Bob loses to dealer blackjack
    event_bus.emit(
        EngineEventType.HAND_RESULT,
        {
            "game_id": game_id,
            "round_id": round_id,
            "player_id": "player_2",
            "player_name": "Bob",
            "result": "lose",
            "timestamp": time.time(),
        },
    )

    # Charlie pushes with dealer blackjack
    event_bus.emit(
        EngineEventType.HAND_RESULT,
        {
            "game_id": game_id,
            "round_id": round_id,
            "player_id": "player_3",
            "player_name": "Charlie",
            "result": "push",
            "is_blackjack": True,
            "timestamp": time.time(),
        },
    )

    # End the round
    event_bus.emit(
        EngineEventType.ROUND_ENDED,
        {"game_id": game_id, "round_id": round_id, "timestamp": time.time()},
    )

    # End the game
    event_bus.emit(
        EngineEventType.GAME_ENDED, {"game_id": game_id, "timestamp": time.time()}
    )


if __name__ == "__main__":
    asyncio.run(main())
