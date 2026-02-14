#!/usr/bin/env python3
"""
Full CLI Blackjack Game

This script provides a complete playable blackjack game using the new architecture components:
- Events system
- Platform adapters
- Immutable state
- Blackjack engine

Run this script to experience the full blackjack game in the command line.
"""

import asyncio
import argparse
import os
import sys
from typing import Optional

try:
    from cardsharp.adapters import CLIAdapter
    from cardsharp.engine import BlackjackEngine
    from cardsharp.events import EventBus, EngineEventType, EventPriority
    from cardsharp.state import GameStage
except ImportError:
    print("ERROR: CardSharp package not found or incompletely installed.")
    print("Please ensure CardSharp is installed properly with: uv sync")
    sys.exit(1)


class BlackjackCLI:
    """CLI interface for playing blackjack with the new architecture."""

    def __init__(self, num_players: int = 1, initial_bankroll: float = 1000.0):
        """
        Initialize the blackjack CLI.

        Args:
            num_players: Number of players (1-7)
            initial_bankroll: Starting bankroll for each player
        """
        self.num_players = min(max(1, num_players), 7)  # Limit to 1-7 players
        self.initial_bankroll = initial_bankroll
        self.adapter = CLIAdapter()

        # Game configuration
        self.config = {
            "dealer_rules": {"stand_on_soft_17": True, "peek_for_blackjack": True},
            "deck_count": 6,
            "rules": {
                "blackjack_pays": 1.5,
                "deck_count": 6,
                "dealer_hit_soft_17": False,
                "offer_insurance": True,
                "allow_surrender": True,
                "allow_double_after_split": True,
                "min_bet": 5.0,
                "max_bet": 1000.0,
            },
        }

        self.engine = BlackjackEngine(self.adapter, self.config)
        self.event_bus = EventBus.get_instance()
        self.players = []
        self.running = False

    async def initialize(self):
        """Initialize the game."""
        # Set up event listeners
        self._setup_event_listeners()

        # Initialize engine
        await self.engine.initialize()

        # Clear the screen and show welcome message
        os.system("cls" if os.name == "nt" else "clear")
        self._print_welcome()

        # Start a new game
        await self.engine.start_game()

        # Add players
        for i in range(1, self.num_players + 1):
            if self.num_players == 1:
                name = input("Enter your name: ")
                if not name:
                    name = "Player 1"
            else:
                name = input(f"Enter name for Player {i}: ")
                if not name:
                    name = f"Player {i}"

            player_id = await self.engine.add_player(name, self.initial_bankroll)
            self.players.append({"id": player_id, "name": name})

    async def run(self, num_rounds: Optional[int] = None):
        """
        Run the blackjack game.

        Args:
            num_rounds: Optional number of rounds to play. None means play until quit.
        """
        self.running = True
        round_num = 1

        while self.running and (num_rounds is None or round_num <= num_rounds):
            print(f"\n{'=' * 20} ROUND {round_num} {'=' * 20}\n")

            # Get bets from all players
            for player in self.players:
                # Check if player has money
                has_money = False
                for p in self.engine.state.players:
                    if p.id == player["id"] and p.balance > 0:
                        has_money = True
                        break

                if not has_money:
                    print(f"{player['name']} has no money left and cannot play!")
                    continue

                player_balance = 0
                # Get current balance
                for p in self.engine.state.players:
                    if p.id == player["id"]:
                        player_balance = p.balance
                        break

                min_bet = self.config["rules"].get("min_bet", 5.0)
                max_bet = min(
                    self.config["rules"].get("max_bet", 1000.0), player_balance
                )

                # Prompt for bet
                while True:
                    try:
                        bet_str = input(
                            f"{player['name']} (${player_balance:.2f}), enter your bet (${min_bet:.2f}-${max_bet:.2f}): "
                        )
                        bet = float(bet_str)
                        if min_bet <= bet <= max_bet:
                            await self.engine.place_bet(player["id"], bet)
                            break
                        else:
                            print(
                                f"Bet must be between ${min_bet:.2f} and ${max_bet:.2f}"
                            )
                    except ValueError:
                        print("Please enter a valid number")

            # Game flow will continue automatically through dealing and player turns
            # Wait for the round to complete
            while self.engine.state.stage != GameStage.PLACING_BETS:
                await asyncio.sleep(0.1)

            # Check if all players are broke
            all_broke = True
            for p in self.engine.state.players:
                if p.balance > 0:
                    all_broke = False
                    break

            if all_broke:
                print("\nAll players are out of money! Game over.")
                self.running = False
                break

            # Check if we should continue
            if num_rounds is None:
                while True:
                    response = input("\nPlay another round? (y/n): ").lower()
                    if response in ("y", "yes"):
                        break
                    elif response in ("n", "no"):
                        self.running = False
                        break
                    else:
                        print("Please enter 'y' for yes or 'n' for no.")

            round_num += 1

    async def shutdown(self):
        """Shut down the game."""
        # Display final stats
        print("\n" + "=" * 40)
        print("FINAL RESULTS")
        print("=" * 40)

        for player in self.engine.state.players:
            net_change = player.balance - self.initial_bankroll
            result = (
                "won" if net_change > 0 else "lost" if net_change < 0 else "broke even"
            )
            print(
                f"{player.name}: ${player.balance:.2f} ({result} ${abs(net_change):.2f})"
            )

        print("\nThank you for playing!")

        # Shutdown the engine
        await self.engine.shutdown()

    def _setup_event_listeners(self):
        """Set up event listeners for the game."""
        # Listen for card dealt events
        self.event_bus.on(
            EngineEventType.CARD_DEALT, self._on_card_dealt, EventPriority.LOW
        )

        # Listen for player and dealer actions
        self.event_bus.on(
            EngineEventType.PLAYER_ACTION, self._on_player_action, EventPriority.LOW
        )
        self.event_bus.on(
            EngineEventType.DEALER_ACTION, self._on_dealer_action, EventPriority.LOW
        )

        # Listen for hand results
        self.event_bus.on(
            EngineEventType.HAND_RESULT, self._on_hand_result, EventPriority.LOW
        )

        # Listen for bankroll updates
        self.event_bus.on(
            EngineEventType.BANKROLL_UPDATED,
            self._on_bankroll_updated,
            EventPriority.LOW,
        )

    def _on_card_dealt(self, data):
        """Handle card dealt events."""
        # We don't need to print here since the CLIAdapter will handle rendering
        pass

    def _on_player_action(self, data):
        """Handle player action events."""
        # Additional logging can be added here if needed
        pass

    def _on_dealer_action(self, data):
        """Handle dealer action events."""
        # Additional logging can be added here if needed
        pass

    def _on_hand_result(self, data):
        """Handle hand result events."""
        if "player_id" in data and data["player_id"] != "dealer":
            result = data.get("result", "unknown")
            payout = data.get("payout", 0)
            if result == "win":
                print(f"✅ {data['player_name']} wins ${payout:.2f}!")
            elif result == "lose":
                print(f"❌ {data['player_name']} loses their bet.")
            elif result == "push":
                print(f"🟰 {data['player_name']} pushes (tie).")
            elif result == "surrender":
                print(
                    f"🏳️ {data['player_name']} surrendered and gets half their bet back."
                )

    def _on_bankroll_updated(self, data):
        """Handle bankroll update events."""
        # Print updated bankroll when available
        print(f"💰 {data['player_name']}'s balance: ${data['balance']:.2f}")

    def _print_welcome(self):
        """Print welcome message and game rules."""
        print("=" * 60)
        print("WELCOME TO BLACKJACK".center(60))
        print("=" * 60)
        print("\nRULES:")
        print(
            f"- Dealer stands on soft 17: {'Yes' if self.config['dealer_rules']['stand_on_soft_17'] else 'No'}"
        )
        print(f"- Blackjack pays: {self.config['rules']['blackjack_pays']}:1")
        print(f"- Decks: {self.config['rules']['deck_count']}")
        print(
            f"- Surrender allowed: {'Yes' if self.config['rules']['allow_surrender'] else 'No'}"
        )
        print(
            f"- Double after split: {'Yes' if self.config['rules']['allow_double_after_split'] else 'No'}"
        )
        print(f"- Minimum bet: ${self.config['rules'].get('min_bet', 5.0):.2f}")
        print(f"- Maximum bet: ${self.config['rules'].get('max_bet', 1000.0):.2f}")
        print("\nCOMMANDS:")
        print("- To hit: type '1' or 'hit'")
        print("- To stand: type '2' or 'stand'")
        print("- To double: type '3' or 'double'")
        print("- To split: type '4' or 'split' (when available)")
        print("- To surrender: type '5' or 'surrender' (when available)")
        print("\nGOOD LUCK!\n")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Play Blackjack with the new architecture"
    )
    parser.add_argument(
        "-p", "--players", type=int, default=1, help="Number of players (1-7)"
    )
    parser.add_argument(
        "-b", "--bankroll", type=float, default=1000.0, help="Starting bankroll"
    )
    parser.add_argument(
        "-r", "--rounds", type=int, help="Number of rounds to play (default: unlimited)"
    )
    parser.add_argument(
        "-t", "--test", action="store_true", help="Run in test mode (non-interactive)"
    )

    args = parser.parse_args()

    # Check if we're running in a test/CI environment
    if args.test or not sys.stdin.isatty():
        print("Running in test mode (non-interactive)")
        # In test mode, we just verify that the game initializes properly
        # Create a game with minimal configuration
        game = BlackjackCLI(num_players=1, initial_bankroll=100.0)

        # Initialize engine and basic event listeners
        event_bus = EventBus.get_instance()
        event_bus.on(
            EngineEventType.GAME_CREATED,
            lambda data: print("Game created successfully"),
        )
        await game.engine.initialize()
        await game.engine.start_game()

        print("Test completed successfully!")
        return

    # Create and run the game
    game = BlackjackCLI(num_players=args.players, initial_bankroll=args.bankroll)
    await game.initialize()

    try:
        await game.run(args.rounds)
    except KeyboardInterrupt:
        print("\nGame interrupted. Exiting...")
    finally:
        await game.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
