#!/usr/bin/env python3
"""
Example demonstrating the use of the WarEngine with the immutable state.

This script shows how to use the WarEngine class with a platform adapter
to create a complete War card game.
"""

import asyncio
import argparse

# Check if cardsharp is installed properly
try:
    from cardsharp.adapters import CLIAdapter, DummyAdapter
    from cardsharp.api import WarGame
    from cardsharp.events import EventBus, EngineEventType, EventPriority
except ImportError:
    print("ERROR: CardSharp package not found or incompletely installed.")
    print("Please ensure CardSharp is installed properly with: uv sync")
    import sys

    sys.exit(1)


async def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Play a simulation of War card game.")
    parser.add_argument(
        "-r",
        "--rounds",
        type=int,
        default=10,
        help="number of rounds to play (default: 10)",
    )
    parser.add_argument(
        "-p", "--players", type=int, default=2, help="number of players (default: 2)"
    )
    parser.add_argument(
        "-n",
        "--names",
        nargs="+",
        default=["Alice", "Bob"],
        help="names of the players (default: Alice Bob)",
    )
    parser.add_argument(
        "-s", "--silent", action="store_true", help="run in silent mode (no output)"
    )
    args = parser.parse_args()

    # Create the adapter
    if args.silent:
        adapter = DummyAdapter()
    else:
        adapter = CLIAdapter()

    # Create the game
    game = WarGame(adapter=adapter)

    # Set up event listeners
    event_bus = EventBus.get_instance()

    def on_round_ended(data):
        winner_name = data.get("winner_name", "Unknown")
        print(f"Round {data.get('round_number', '?')} ended. Winner: {winner_name}")

    def on_war_started(data):
        if data.get("event_name") == "WAR_STARTED":
            players = data.get("players", [])
            print(f"WAR! {' vs '.join(players)} have tied cards!")

    # Subscribe to events
    event_bus.on(EngineEventType.ROUND_ENDED, on_round_ended)
    event_bus.on(EngineEventType.CUSTOM_EVENT, on_war_started)

    # Initialize the game
    await game.initialize()

    # Start a new game
    await game.start_game()

    # Add players
    player_ids = []
    for i in range(min(args.players, len(args.names))):
        name = args.names[i]
        player_id = await game.add_player(name)
        player_ids.append(player_id)
        print(f"Added player: {name} (ID: {player_id})")

    print("\nStarting War card game...")

    # Play the specified number of rounds
    for round_num in range(1, args.rounds + 1):
        print(f"\n=== Round {round_num} ===")

        # Play a round
        round_result = await game.play_round()

        # Display round winners and stats
        if not args.silent:
            winner_id = round_result.get("winner_id")
            winner_name = next(
                (p["name"] for p in round_result["players"] if p["id"] == winner_id),
                "Unknown",
            )

            print(f"\nRound {round_num} summary:")
            print(f"Winner: {winner_name}")
            print("\nPlayer stats:")

            for player in round_result["players"]:
                name = player["name"]
                wins = player["wins"]
                win_percent = (wins / round_num) * 100 if round_num > 0 else 0
                max_streak = player.get("max_streak", 0)

                print(
                    f"{name}: {wins} wins ({win_percent:.1f}%), longest streak: {max_streak}"
                )

        # Short delay between rounds
        await asyncio.sleep(0.5)

    # Display final stats
    final_state = await game.get_state()
    print("\n=== Final Results ===")

    for player in final_state.players:
        name = player.name
        wins = player.wins
        win_percent = (wins / args.rounds) * 100 if args.rounds > 0 else 0
        max_streak = player.max_streak

        print(f"{name}: {wins} wins ({win_percent:.1f}%), longest streak: {max_streak}")

    # Shutdown the game
    await game.shutdown()

    print("\nDemo completed!")


if __name__ == "__main__":
    asyncio.run(main())
