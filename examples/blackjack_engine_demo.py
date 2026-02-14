#!/usr/bin/env python3
"""
Example demonstrating the use of the BlackjackEngine with the immutable state.

This script shows how to use the BlackjackEngine class with a platform adapter
to create a complete blackjack game.
"""

import asyncio

# Check if cardsharp is installed properly
try:
    from cardsharp.adapters import CLIAdapter
    from cardsharp.engine import BlackjackEngine
    from cardsharp.events import EventBus, EngineEventType, EventPriority
except ImportError:
    print("ERROR: CardSharp package not found or incompletely installed.")
    print("Please ensure CardSharp is installed properly with: uv sync")
    import sys

    sys.exit(1)


async def main():
    # Create the adapter
    adapter = CLIAdapter()

    # Create the engine
    config = {
        "dealer_rules": {"stand_on_soft_17": True, "peek_for_blackjack": True},
        "deck_count": 2,
        "rules": {
            "blackjack_pays": 1.5,
            "offer_insurance": True,
            "allow_surrender": True,
        },
    }
    engine = BlackjackEngine(adapter, config)

    # Set up event listeners
    event_bus = EventBus.get_instance()

    def on_card_dealt(data):
        recipient = data.get("player_name", "Dealer")
        if data.get("is_dealer", False):
            if data.get("is_hole_card", False):
                print("Dealer's hole card is dealt (hidden)")
            else:
                print(f"Dealer is dealt: {data['card']}")
        else:
            print(f"{recipient} is dealt: {data['card']}")

    def on_player_action(data):
        print(f"Player action: {data['player_name']} chose {data['action']}")

    def on_hand_result(data):
        player = data.get("player_name", "Unknown player")
        result = data.get("result", "unknown")
        print(f"Hand result: {player} - {result}")

    # Subscribe to events
    event_bus.on(EngineEventType.CARD_DEALT, on_card_dealt)
    event_bus.on(EngineEventType.PLAYER_ACTION, on_player_action)
    event_bus.on(EngineEventType.HAND_RESULT, on_hand_result)

    # Initialize the engine
    await engine.initialize()

    # Start a new game
    await engine.start_game()

    # Add players
    alice_id = await engine.add_player("Alice", 1000.0)
    bob_id = await engine.add_player("Bob", 500.0)

    print("\nWelcome to Blackjack!")
    print("This example demonstrates the BlackjackEngine with immutable state.")
    print("You'll see how the game flows using events and state transitions.")

    # Play multiple rounds
    for round_num in range(1, 4):
        print(f"\n=== Round {round_num} ===\n")

        # Place bets
        await engine.place_bet(alice_id, 20.0 * round_num)
        await engine.place_bet(bob_id, 10.0 * round_num)

        # Game flow will continue automatically through dealing
        # Player turns will be handled by adapter prompts
        # Dealer turn and hand resolution happen automatically

        # Wait for the round to complete
        while engine.state.stage != GameStage.PLACING_BETS:
            await asyncio.sleep(0.1)

        # Short delay between rounds
        await asyncio.sleep(1)

    # Shutdown the engine
    await engine.shutdown()

    print("\nDemo completed!")


if __name__ == "__main__":
    # Import this here to avoid circular import in the example
    from cardsharp.state import GameStage

    asyncio.run(main())
