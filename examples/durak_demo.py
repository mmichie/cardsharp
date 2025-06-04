"""
Example demonstrating the Durak card game API.

This script provides a simple command-line demo of the Durak game,
showing how to initialize the game, add players, and play a round with
basic user interaction.
"""

import asyncio
import sys
from typing import Dict, Any, List

from cardsharp.adapters import CLIAdapter
from cardsharp.api.durak import DurakGame
from cardsharp.durak.state import GameState


class DurakDemo:
    """
    Demo class for the Durak card game.

    This class provides a simple command-line interface for playing the
    Durak card game, demonstrating the use of the DurakGame API.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the demo.

        Args:
            config: Configuration options for the game
        """
        # Default configuration
        default_config = {
            "deck_size": 36,
            "allow_passing": True,
            "allow_throwing_in": True,
        }

        # Merge with provided config
        if config:
            default_config.update(config)

        self.config = default_config
        self.adapter = CLIAdapter()
        self.game = DurakGame(adapter=self.adapter, config=self.config)
        self.player_ids = []

    async def setup_game(self) -> None:
        """
        Set up the game by initializing the engine and adding players.
        """
        print("Setting up Durak game...")

        # Initialize the game
        await self.game.initialize()
        await self.game.start_game()

        # Add players
        player_names = ["Player", "Alice", "Bob", "Charlie"]
        num_players = int(input(f"Enter number of players (2-{len(player_names)}): "))
        num_players = max(2, min(num_players, len(player_names)))

        for i in range(num_players):
            name = input(f"Enter name for player {i+1} (default: {player_names[i]}): ")
            if not name:
                name = player_names[i]
            player_id = await self.game.add_player(name)
            self.player_ids.append(player_id)
            print(f"Added player: {name} (ID: {player_id})")

        # Deal initial cards
        await self.game.deal_initial_cards()
        print("Initial cards dealt.")

    async def play_game(self) -> None:
        """
        Play the game until it's over.
        """
        # Keep playing until the game is over
        while not await self.game.is_game_over():
            # Get the current state
            state = await self.game.get_state()

            # Display the current state
            self._display_state(state)

            # Get the active player
            active_player = state.active_player
            if not active_player:
                print("No active player, something went wrong.")
                break

            # Get valid actions for the active player
            valid_actions = await self.game.get_valid_actions(active_player.id)

            # Display valid actions
            print(f"\n{active_player.name}'s turn ({state.stage.name}):")

            # Handle user input
            action = await self._get_user_action(active_player.id, valid_actions)

            # Execute the action
            if action[0] == "PLAY_CARD":
                card_index = action[1]
                success = await self.game.play_card(active_player.id, card_index)
                if not success:
                    print("Failed to play card.")
            elif action[0] == "TAKE_CARDS":
                success = await self.game.take_cards(active_player.id)
                if not success:
                    print("Failed to take cards.")
            elif action[0] == "PASS":
                success = await self.game.pass_turn(active_player.id)
                if not success:
                    print("Failed to pass turn.")
            elif action[0] == "PASS_TO_PLAYER":
                target_id = action[1]
                success = await self.game.pass_to_player(active_player.id, target_id)
                if not success:
                    print("Failed to pass to player.")

            print("\n" + "-" * 40)

        # Game is over, display results
        state = await self.game.get_state()
        loser_id = await self.game.get_loser()

        print("\nGame over!")
        if loser_id:
            loser_name = next(
                (p.name for p in state.players if p.id == loser_id), "Unknown"
            )
            print(f"The loser (durak) is: {loser_name}")
        else:
            print("The game ended in a draw.")

    async def _get_user_action(
        self, player_id: str, valid_actions: Dict[str, List[Any]]
    ) -> List[Any]:
        """
        Get a user action based on valid actions.

        Args:
            player_id: ID of the player
            valid_actions: Dictionary of valid actions

        Returns:
            List containing the action type and any parameters
        """
        # Display valid actions
        print("Valid actions:")

        action_list = []

        if "PLAY_CARD" in valid_actions:
            card_indices = valid_actions["PLAY_CARD"]
            state = await self.game.get_state()

            # Find the player
            player = None
            for p in state.players:
                if p.id == player_id:
                    player = p
                    break

            if player:
                for i, idx in enumerate(card_indices):
                    if idx < len(player.hand):
                        card = player.hand[idx]
                        print(f"{i+1}. Play card: {card}")
                        action_list.append(("PLAY_CARD", idx))

        if "TAKE_CARDS" in valid_actions:
            print(f"{len(action_list)+1}. Take cards")
            action_list.append(("TAKE_CARDS",))

        if "PASS" in valid_actions:
            print(f"{len(action_list)+1}. Pass")
            action_list.append(("PASS",))

        if "PASS_TO_PLAYER" in valid_actions:
            target_ids = valid_actions["PASS_TO_PLAYER"]
            state = await self.game.get_state()

            for i, target_id in enumerate(target_ids):
                target_name = next(
                    (p.name for p in state.players if p.id == target_id), "Unknown"
                )
                print(f"{len(action_list)+i+1}. Pass to {target_name}")
                action_list.append(("PASS_TO_PLAYER", target_id))

        # Get user choice
        choice = -1
        while choice < 1 or choice > len(action_list):
            try:
                choice_str = input(f"Enter your choice (1-{len(action_list)}): ")
                choice = int(choice_str)
            except ValueError:
                choice = -1

        return action_list[choice - 1]

    def _display_state(self, state: GameState) -> None:
        """
        Display the current game state.

        Args:
            state: Current game state
        """
        print("\nGame State:")
        print(f"Round: {state.current_round}")
        print(f"Stage: {state.stage.name}")
        print(f"Trump Suit: {state.trump_suit}")
        print(f"Deck remaining: {len(state.deck)}")

        # Display table
        print("\nTable:")
        pairs = state.table.attack_defense_pairs
        for i, (attack, defense) in enumerate(pairs):
            defense_str = f" ← {defense}" if defense else ""
            print(f"  {i+1}. {attack}{defense_str}")

        # Display players
        print("\nPlayers:")
        for player in state.players:
            role = ""
            if player.is_attacker:
                role = " (Attacker)"
            elif player.is_defender:
                role = " (Defender)"

            out_str = " (Out)" if player.is_out else ""

            print(f"  {player.name}{role}{out_str}: {len(player.hand)} cards")

            # Show cards for all players (in a real game, you'd only show the current player's hand)
            card_str = ", ".join(str(card) for card in player.hand)
            print(f"    Cards: {card_str}")

    async def shutdown(self) -> None:
        """
        Shut down the game.
        """
        await self.game.shutdown()
        print("Game shut down.")


async def main():
    """
    Main function to run the demo.
    """
    # Parse command-line arguments for configuration
    config = {}

    if "--deck-size" in sys.argv:
        idx = sys.argv.index("--deck-size")
        if idx + 1 < len(sys.argv):
            try:
                deck_size = int(sys.argv[idx + 1])
                if deck_size in [20, 36, 52]:
                    config["deck_size"] = deck_size
            except ValueError:
                pass

    if "--no-passing" in sys.argv:
        config["allow_passing"] = False

    if "--no-throwing-in" in sys.argv:
        config["allow_throwing_in"] = False

    # Create and run the demo
    demo = DurakDemo(config)

    try:
        await demo.setup_game()
        await demo.play_game()
    finally:
        await demo.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
