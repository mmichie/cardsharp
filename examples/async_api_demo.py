#!/usr/bin/env python3
"""
Async API Demo for Cardsharp

This example demonstrates the new asynchronous API features introduced in Phase 3
of the architecture modernization plan. It showcases:

1. The high-level BlackjackGame API
2. Event-driven flow control
3. Both async and sync operation modes
4. Auto-play capabilities
"""

import asyncio
import time
import random
import sys
from typing import Dict, Any, List, Optional

# Check if cardsharp is installed properly
try:
    from cardsharp.api import (
        BlackjackGame,
        EventWaiter,
        EventSequence,
        EventFilter,
        event_driven,
        EventDrivenContext,
    )
    from cardsharp.adapters import CLIAdapter, DummyAdapter
    from cardsharp.events import EngineEventType
    from cardsharp.blackjack.action import Action
except ImportError:
    print("ERROR: CardSharp package not found or incompletely installed.")
    print("Please ensure CardSharp is installed properly with: poetry install")
    sys.exit(1)


class DemoOptions:
    """Demo configuration options"""

    CLI_MODE = True  # Set to False to use a DummyAdapter instead of CLI
    PLAYER_COUNT = 2  # Number of players to add
    AUTO_PLAY = True  # Whether to auto-play or require manual input
    ROUND_COUNT = 3  # Number of rounds to play


async def showcase_basics():
    """Showcase basic API capabilities"""
    print("\n=== BASIC API DEMO ===")

    # Create adapter based on demo mode
    if DemoOptions.CLI_MODE:
        adapter = CLIAdapter()
        print("Using CLI adapter for interactive play")
    else:
        adapter = DummyAdapter(verbose=True)
        print("Using Dummy adapter for simulated play")

    # Create the game with the adapter
    game = BlackjackGame(adapter=adapter, auto_play=DemoOptions.AUTO_PLAY)

    # Initialize the game
    print("Initializing game...")
    await game.initialize()

    # Start a new game
    print("Starting game...")
    await game.start_game()

    # Add players
    players = []
    for i in range(1, DemoOptions.PLAYER_COUNT + 1):
        name = f"Player {i}"
        balance = 1000.0
        player_id = await game.add_player(name, balance)
        players.append({"id": player_id, "name": name})
        print(f"Added {name} with ID {player_id}")

    # Play rounds
    for round_num in range(1, DemoOptions.ROUND_COUNT + 1):
        print(f"\n=== ROUND {round_num} ===")

        # Place bets
        for player in players:
            bet = 10.0 * round_num
            await game.place_bet(player["id"], bet)
            print(f"{player['name']} bets ${bet:.2f}")

        # If auto-play is enabled, let the round play out automatically
        if DemoOptions.AUTO_PLAY:
            print("Auto-playing round...")
            round_results = await game.auto_play_round()

            # Display results
            print("\nRound Results:")
            for player in round_results["players"]:
                player_name = player["name"]
                player_balance = player["balance"]
                hands = player["hands"]

                for i, hand in enumerate(hands):
                    result = hand.get("result", "unknown")
                    payout = hand.get("payout", 0)
                    cards = ", ".join(hand.get("cards", []))

                    print(f"{player_name} Hand {i+1}: {cards} - {result.upper()}")
                    if result == "win":
                        print(f"  Won ${payout:.2f}")
                    elif result == "push":
                        print(f"  Push - got ${payout:.2f} back")

                print(f"{player_name}'s balance: ${player_balance:.2f}")
        else:
            # Let the game play out through user interaction
            # Wait for the round to complete
            state = await game.get_state()
            while state.stage.name != "PLACING_BETS":
                await asyncio.sleep(0.5)
                state = await game.get_state()

    # Shutdown the game
    print("\nShutting down game...")
    await game.shutdown()
    print("Basic demo completed!")


async def showcase_event_driven_flow():
    """Showcase event-driven flow control"""
    print("\n=== EVENT-DRIVEN FLOW CONTROL DEMO ===")

    # Create a dummy adapter for simpler demonstration
    adapter = DummyAdapter(verbose=True)

    # Create the game
    game = BlackjackGame(adapter=adapter, auto_play=False)

    # Initialize and start
    await game.initialize()
    await game.start_game()

    # Add a player
    player_id = await game.add_player("EventPlayer", 1000.0)

    print("\nDemonstrating event waiting:")

    # Place a bet and wait for the bet event
    print("Placing bet and waiting for bet event...")
    bet_task = asyncio.create_task(game.place_bet(player_id, 25.0))

    # Wait for the bet event
    try:
        event, data = await game.wait_for_event(
            EngineEventType.PLAYER_BET,
            lambda evt, data: data.get("player_id") == player_id,
            timeout=5.0,
        )
        print(f"Caught event: {event}")
        print(f"Bet amount: ${data.get('amount', 0):.2f}")
    except asyncio.TimeoutError:
        print("Timeout waiting for bet event")

    # Make sure the bet task is complete
    await bet_task

    print("\nDemonstrating event sequence:")

    # Create an event sequence for a complete player turn
    sequence = game.create_event_sequence()

    # Add steps to the sequence
    sequence.add_step(
        "hit",
        lambda g: g.execute_action(player_id, Action.HIT, wait_for_completion=False),
        EngineEventType.PLAYER_ACTION,
        lambda evt, data: data.get("player_id") == player_id
        and data.get("action") == "HIT",
    )

    sequence.add_step(
        "stand",
        lambda g: g.execute_action(player_id, Action.STAND, wait_for_completion=False),
        EngineEventType.PLAYER_ACTION,
        lambda evt, data: data.get("player_id") == player_id
        and data.get("action") == "STAND",
    )

    # Execute the sequence
    print("Executing pre-planned action sequence: HIT then STAND")
    results = await sequence.execute(game)

    # Show results
    for step_name, (success, result, error) in results.items():
        if success:
            print(f"Step '{step_name}' succeeded")
        else:
            print(f"Step '{step_name}' failed: {error}")

    print("\nDemonstrating event context manager:")

    # Wait for the game to get back to the betting stage
    print("Waiting for next round...")
    await game.wait_for_event(EngineEventType.ROUND_ENDED, timeout=10.0)

    # Place another bet
    await game.place_bet(player_id, 50.0)

    # Use the event context manager to set up temporary handlers
    async with EventDrivenContext(game.event_bus) as ctx:
        # Set up handlers for specific events
        cards_dealt = 0

        def card_deal_handler(data):
            nonlocal cards_dealt
            if data.get("player_id") == player_id:
                cards_dealt += 1
                print(f"Card dealt to player: {data.get('card', '?')}")

        def hand_result_handler(data):
            if data.get("player_id") == player_id:
                result = data.get("result", "unknown")
                print(f"Hand result: {result.upper()}")

        # Register handlers for the duration of the context
        ctx.on(EngineEventType.CARD_DEALT, card_deal_handler)
        ctx.on(EngineEventType.HAND_RESULT, hand_result_handler)

        # Execute actions and wait for events
        print("Playing with event context - will track cards and results")
        await game.execute_action(player_id, Action.HIT)
        await game.execute_action(player_id, Action.STAND)

        # Wait for the hand to be resolved
        try:
            await ctx.wait_for(
                EngineEventType.HAND_RESULT,
                lambda evt, data: data.get("player_id") == player_id,
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            print("Timeout waiting for hand result")

    print(f"Total cards dealt to player: {cards_dealt}")

    # Shutdown the game
    await game.shutdown()
    print("Event-driven flow demo completed!")


async def showcase_decorated_functions():
    """Showcase decorated event-driven functions"""
    print("\n=== DECORATED FUNCTIONS DEMO ===")

    # Create a dummy adapter
    adapter = DummyAdapter(verbose=True)

    # Create the game
    game = BlackjackGame(adapter=adapter, auto_play=False)

    # Initialize and start
    await game.initialize()
    await game.start_game()

    # Add a player
    player_id = await game.add_player("DecoratedPlayer", 1000.0)

    # Example of a decorated function that waits for a specific event
    @event_driven(EngineEventType.PLAYER_BET, lambda data: data.get("amount") == 75.0)
    async def place_special_bet(game_instance, player_id):
        """Place a special bet and wait for the event"""
        return await game_instance.place_bet(player_id, 75.0)

    # Use the decorated function
    print("Using decorated function to place bet and wait for confirmation...")
    result, event_data = await place_special_bet(game, player_id)

    if event_data:
        print(f"Bet confirmed: ${event_data.get('amount', 0):.2f}")
    else:
        print("Bet placed but event not captured")

    # Shutdown the game
    await game.shutdown()
    print("Decorated functions demo completed!")


async def showcase_sync_api():
    """Showcase synchronous API usage"""
    print("\n=== SYNCHRONOUS API DEMO ===")
    print("Creating a game with synchronous API")

    # Create the game with sync mode
    game = BlackjackGame(adapter=DummyAdapter(verbose=True), use_async=False)

    # Use synchronous methods
    print("Initializing game synchronously...")
    game.initialize_sync()

    print("Starting game synchronously...")
    game.start_game_sync()

    print("Adding player synchronously...")
    player_id = game.add_player_sync("SyncPlayer", 1000.0)

    print("Playing a round synchronously...")
    game.place_bet_sync(player_id, 100.0)

    # Auto-play the round
    print("Auto-playing round synchronously...")
    results = game.auto_play_round_sync()

    # Display a simple summary
    for player in results["players"]:
        player_name = player["name"]
        player_balance = player["balance"]
        print(f"{player_name}'s balance: ${player_balance:.2f}")

    # Shutdown
    print("Shutting down synchronously...")
    game.shutdown_sync()
    print("Synchronous API demo completed!")


async def main():
    """Main entry point for the demo"""
    print("=" * 60)
    print("CARDSHARP ASYNC API DEMO".center(60))
    print("=" * 60)
    print("\nThis demo showcases the new Phase 3 asynchronous API features")

    try:
        # Run the basic API demo
        await showcase_basics()

        # Run the event-driven flow control demo
        await showcase_event_driven_flow()

        # Run the decorated functions demo
        await showcase_decorated_functions()

        # Run the synchronous API demo (this runs in a separate thread)
        await asyncio.to_thread(showcase_sync_api)

    except KeyboardInterrupt:
        print("\nDemo interrupted. Exiting...")

    print("\nDemo completed! Phase 3 API features have been showcased.")


if __name__ == "__main__":
    asyncio.run(main())
