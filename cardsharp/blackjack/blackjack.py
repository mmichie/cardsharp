import argparse
import asyncio

from cardsharp.blackjack.actor import Dealer, Player
from cardsharp.blackjack.state import (
    EndRoundState,
    PlacingBetsState,
    WaitingForPlayersState,
)
from cardsharp.blackjack.stats import SimulationStats
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.common.deck import Deck
from cardsharp.common.io_interface import (
    ConsoleIOInterface,
    DummyIOInterface,
    LoggingIOInterface,
)


class BlackjackGame:
    """
    A class to represent a game of Blackjack.

    Attributes
    ----------
    players : list
        List of Player objects participating in the game.
    io_interface : IOInterface
        Interface for input and output operations.
    dealer : Dealer
        Dealer for the game.
    rules : dict
        Dictionary defining game rules.
    deck : Deck
        Deck of cards for the game.
    current_state : GameState
        Current state of the game.
    stats : SimulationStats
        Statistics for the game.
    """

    def __init__(self, rules, io_interface):
        self.players = []
        self.io_interface = io_interface
        self.dealer = Dealer("Dealer", io_interface)
        self.rules = rules
        self.deck = Deck()
        self.current_state = WaitingForPlayersState()
        self.stats = SimulationStats()

    async def set_state(self, state):
        """Change the current state of the game."""
        await self.io_interface.output(f"Changing state to {state}.")
        self.current_state = state

    async def add_player(self, player):
        """Add a player to the game."""
        if player is None:
            await self.io_interface.output("Invalid player.")
            return

        if len(self.players) >= self.rules["max_players"]:
            await self.io_interface.output("Game is full.")
            return

        if not isinstance(self.current_state, WaitingForPlayersState):
            await self.io_interface.output("Game has already started.")
            return

        if self.current_state is not None:
            await self.current_state.add_player(self, player)

    async def play_round(self):
        """Play a round of the game until it reaches the end state."""
        while not isinstance(self.current_state, EndRoundState):
            await self.io_interface.output("Current state: " + str(self.current_state))
            await self.current_state.handle(self)

        await self.io_interface.output("Calculating winner...")
        await self.current_state.handle(self)

    def reset(self):
        """Reset the game by creating a new deck and resetting all players."""
        self.deck = Deck()
        for player in self.players:
            player.reset()
        self.dealer.reset()


async def main():
    parser = argparse.ArgumentParser(description="Run a Blackjack game.")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run the game in simulation mode with no console output. If --log_file is provided, output will be logged.",
        default=False,
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Run the game in interactive console mode. Overrides other modes if present.",
        default=False,
    )
    parser.add_argument(
        "--num_games", type=int, default=1, help="Number of games to simulate"
    )
    parser.add_argument(
        "--log_file",
        type=str,
        help="Log game output to the specified file. If not provided, output goes to the console.",
    )
    args = parser.parse_args()
    if args.console:
        io_interface = ConsoleIOInterface()
        strategy = None
    elif args.log_file:
        io_interface = LoggingIOInterface(args.log_file)
    elif args.simulate:
        io_interface = DummyIOInterface()
    else:
        io_interface = ConsoleIOInterface()
        strategy = BasicStrategy()

    # Define your rules TODO: make this use rules class
    rules = {
        "blackjack_payout": 1.5,
        "allow_insurance": True,
        "min_players": 1,
        "min_bet": 10,
        "max_players": 6,
    }

    players = [
        Player("Bob", io_interface, strategy),
    ]

    # Create a game
    game = BlackjackGame(rules, io_interface)

    # Add players
    for player in players:
        await game.add_player(player)

    # Change state to PlacingBetsState after all players have been added
    await game.set_state(PlacingBetsState())

    # Play games
    for _ in range(args.num_games):
        await game.play_round()
        game.reset()

    # Get and print the statistics after all games have been played
    stats = game.stats.report()
    games_played = stats["games_played"]
    player_wins = stats["player_wins"]
    dealer_wins = stats["dealer_wins"]
    draws = stats["draws"]

    win_loss_ratio = player_wins / games_played

    print(f"Games played: {games_played}")
    print(f"Player wins: {player_wins}")
    print(f"Dealer wins: {dealer_wins}")
    print(f"Draws: {draws}")
    print(f"Win/Loss ratio: {win_loss_ratio:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
