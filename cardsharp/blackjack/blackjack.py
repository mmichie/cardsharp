"""
This module is used to execute a game of Blackjack.

It can be used to play a game in different modes:
- Interactive console mode, where the user interacts with the game via the console.
- Simulation mode, where the game runs automatically.
- Logging mode, where game output is logged to a specified file.

To run the game in different modes, specific command line arguments are used.
For example, `--console` runs the game in interactive console mode,
`--simulate` runs the game in simulation mode and `--log_file` followed by a filename runs the game in logging mode.
"""

import argparse
import multiprocessing
import time
import cProfile
import pstats
import io


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

    def set_state(self, state):
        """Change the current state of the game."""
        self.io_interface.output(f"Changing state to {state}.")
        self.current_state = state

    def add_player(self, player):
        """Add a player to the game."""
        if player is None:
            self.io_interface.output("Invalid player.")
            return

        if len(self.players) >= self.rules["max_players"]:
            self.io_interface.output("Game is full.")
            return

        if not isinstance(self.current_state, WaitingForPlayersState):
            self.io_interface.output("Game has already started.")
            return

        if self.current_state is not None:
            self.current_state.add_player(self, player)

    def play_round(self):
        """Play a round of the game until it reaches the end state."""
        while not isinstance(self.current_state, EndRoundState):
            self.io_interface.output("Current state: " + str(self.current_state))
            self.current_state.handle(self)

        self.io_interface.output("Calculating winner...")
        self.current_state.handle(self)

    def reset(self):
        """Reset the game by creating a new deck and resetting all players."""
        self.deck = Deck()
        for player in self.players:
            player.reset()
        self.dealer.reset()


def create_io_interface(args):
    """Create the IO interface based on the command line arguments."""
    strategy = None
    if args.console:
        io_interface = ConsoleIOInterface()
    elif args.log_file:
        io_interface = LoggingIOInterface(args.log_file)
    elif args.simulate:
        io_interface = DummyIOInterface()
        strategy = BasicStrategy()
    else:
        io_interface = ConsoleIOInterface()
        strategy = BasicStrategy()
    return io_interface, strategy


def play_game(rules, io_interface, player_names):
    """
    Function to play a single game of Blackjack, to be executed in a separate process.
    """
    players = [Player(name, io_interface, BasicStrategy()) for name in player_names]

    # Create a game
    game = BlackjackGame(rules, io_interface)

    # Add players
    for player in players:
        game.add_player(player)

    # Change state to PlacingBetsState and play a round
    game.set_state(PlacingBetsState())
    game.play_round()
    game.reset()

    # Return any relevant statistics or results
    return game.stats.report()


def play_game_batch(rules, io_interface, player_names, num_games):
    """Function to play a batch of games of Blackjack, to be executed in a separate process."""
    results = []
    for _ in range(num_games):
        result = play_game(
            rules, io_interface, player_names
        )  # play_single_game is your existing game logic
        results.append(result)
    return results


def main():
    """
    Main function to start the game.

    It handles command-line arguments to determine the mode of operation of the game,
    creates the game, adds players, and then plays a specified number of games.
    Finally, it prints out the statistics of the games played.
    """
    parser = argparse.ArgumentParser(description="Run a Blackjack game.")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run the game in simulation mode. If --log_file is provided, output will be logged.",
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

    parser.add_argument(
        "--single_cpu",
        action="store_true",
        help="If provided, run the simulations on a single CPU thread instead of multiple.",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Run the game with profiling to analyze performance.",
        default=False,
    )
    args = parser.parse_args()

    io_interface, _ = create_io_interface(args)

    profiler = None
    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()

    if args.console:
        rules = {
            "blackjack_payout": 1.5,
            "allow_insurance": True,
            "min_players": 1,
            "min_bet": 10,
            "max_players": 6,
        }

        player_names = ["Player1"]
        for _ in range(args.num_games):
            play_game(rules, io_interface, player_names)

    if args.simulate:
        # Define your rules
        rules = {
            "blackjack_payout": 1.5,
            "allow_insurance": True,
            "min_players": 1,
            "min_bet": 10,
            "max_players": 6,
        }

        player_names = ["Bob"]  # Add more player names if needed

        start_time = time.time()  # Record the start time

        if args.single_cpu:
            # Run simulations sequentially
            results = []
            for _ in range(args.num_games):
                result = play_game(rules, DummyIOInterface(), player_names)
                results.append(result)
        else:
            # Run simulations in parallel
            cpu_count = multiprocessing.cpu_count()
            games_per_cpu, remainder = divmod(args.num_games, cpu_count)
            game_batches = [
                games_per_cpu + (1 if i < remainder else 0) for i in range(cpu_count)
            ]

            with multiprocessing.Pool() as pool:
                batch_args = [
                    (rules, DummyIOInterface(), player_names, game_count)
                    for game_count in game_batches
                ]
                batch_results = pool.starmap(play_game_batch, batch_args)
                results = [
                    result for batch in batch_results for result in batch
                ]  # Flatten the results

        end_time = time.time()  # Record the end time
        duration = end_time - start_time  # Calculate the duration
        games_per_second = args.num_games / duration if duration > 0 else 0

        # Initialize counters for aggregated statistics
        total_games_played = 0
        total_player_wins = 0
        total_dealer_wins = 0
        total_draws = 0

        # Aggregate results
        for result in results:
            total_games_played += result["games_played"]
            total_player_wins += result["player_wins"]
            total_dealer_wins += result["dealer_wins"]
            total_draws += result["draws"]

        games_played_excluding_pushes = total_games_played - total_draws

        if games_played_excluding_pushes != 0:
            player_wins_ratio = total_player_wins / games_played_excluding_pushes
            dealer_wins_ratio = total_dealer_wins / games_played_excluding_pushes
        else:
            player_wins_ratio = 0
            dealer_wins_ratio = 0

        house_edge = dealer_wins_ratio - player_wins_ratio

        print("Simulation completed.")
        print(f"Games played (excluding pushes): {games_played_excluding_pushes:,}")
        print(f"Player wins: {total_player_wins:,}")
        print(f"Dealer wins: {total_dealer_wins:,}")
        print(f"Draws: {total_draws:,}")
        print(f"House Edge: {house_edge:.2f}")

        print(f"\nDuration of simulation: {duration:.2f} seconds")
        print(f"Games simulated per second: {games_per_second:,.2f}")

    if args.profile and profiler is not None:
        profiler.disable()
        s = io.StringIO()
        sortby = "tottime"
        ps = pstats.Stats(profiler, stream=s).sort_stats(sortby)
        ps.print_stats()
        print(s.getvalue())


if __name__ == "__main__":
    main()
