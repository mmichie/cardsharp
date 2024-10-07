"""
This module is used to execute a game of Blackjack.

It can be used to play a game in different modes:
- Interactive console mode, where the user interacts with the game via the console.
- Simulation mode, where the game runs automatically.
- Logging mode, where game output is logged to a specified file.
- Visualization mode, where a real-time graph of earnings is displayed.

To run the game in different modes, specific command line arguments are used.
For example, `--console` runs the game in interactive console mode,
`--simulate` runs the game in simulation mode and `--log_file` followed by a filename runs the game in logging mode.
`--vis` enables real-time visualization of the simulation results.
"""

import argparse
import multiprocessing
import time
import cProfile
import pstats
import io
import matplotlib.pyplot as plt
import threading
from copy import deepcopy

from cardsharp.blackjack.actor import Dealer, Player
from cardsharp.blackjack.state import (
    EndRoundState,
    PlacingBetsState,
    WaitingForPlayersState,
)
from cardsharp.blackjack.stats import SimulationStats
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.blackjack.strategy import CountingStrategy
from cardsharp.blackjack.strategy import AggressiveStrategy
from cardsharp.blackjack.strategy import MartingaleStrategy
from cardsharp.common.shoe import Shoe
from cardsharp.common.io_interface import (
    ConsoleIOInterface,
    IOInterface,
    DummyIOInterface,
    LoggingIOInterface,
)
from cardsharp.blackjack.rules import Rules


class BlackjackGraph:
    def __init__(self, max_games):
        self.max_games = max_games
        self.games = []
        self.net_earnings = []

        plt.ion()  # Turn on interactive mode
        self.fig, self.ax = plt.subplots()
        (self.line,) = self.ax.plot([], [], "b-")

        self.ax.set_xlim(0, max_games)
        self.ax.set_ylim(-100, 100)  # Adjust as needed
        self.ax.set_title("Blackjack Performance")
        self.ax.set_xlabel("Games")
        self.ax.set_ylabel("Net Earnings")
        self.ax.grid(True)

    def update(self, game_number, earnings):
        self.games.append(game_number)
        self.net_earnings.append(earnings)

        self.line.set_data(self.games, self.net_earnings)

        if game_number > self.ax.get_xlim()[1]:
            self.ax.set_xlim(0, game_number + 10)

        y_min = min(self.net_earnings) - 10
        y_max = max(self.net_earnings) + 10
        self.ax.set_ylim(y_min, y_max)

        self.fig.canvas.draw()
        self.fig.canvas.flush_events()


class MultiStrategyBlackjackGraph:
    def __init__(self, max_games, strategies):
        self.max_games = max_games
        self.strategies = strategies
        self.data = {strategy: {"games": [], "earnings": []} for strategy in strategies}

        plt.ion()  # Turn on interactive mode
        self.fig, self.ax = plt.subplots(figsize=(12, 6))
        self.lines = {
            strategy: self.ax.plot([], [], label=strategy)[0] for strategy in strategies
        }

        self.ax.set_xlim(0, max_games)
        self.ax.set_ylim(-1000, 1000)  # Adjust as needed
        self.ax.set_title("Blackjack Performance by Strategy")
        self.ax.set_xlabel("Games")
        self.ax.set_ylabel("Net Earnings")
        self.ax.grid(True)
        self.ax.legend()

        self.lock = threading.Lock()

    def update(self, strategy, game_number, earnings):
        with self.lock:
            self.data[strategy]["games"].append(game_number)
            self.data[strategy]["earnings"].append(earnings)

            self.lines[strategy].set_data(
                self.data[strategy]["games"], self.data[strategy]["earnings"]
            )

            all_earnings = [
                earn
                for strat_data in self.data.values()
                for earn in strat_data["earnings"]
            ]
            if all_earnings:
                y_min = min(min(all_earnings) - 10, -1000)
                y_max = max(max(all_earnings) + 10, 1000)
                self.ax.set_ylim(y_min, y_max)

            if game_number > self.ax.get_xlim()[1]:
                self.ax.set_xlim(0, game_number + 10)

            self.fig.canvas.draw()
            self.fig.canvas.flush_events()


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
    rules : Rules
        Object defining game rules.
    shoe : Shoe
        Shoe of cards for the game.
    current_state : GameState
        Current state of the game.
    stats : SimulationStats
        Statistics for the game.
    visible_cards : list
        List of visible cards in the game.
    """

    def __init__(self, rules: Rules, io_interface: IOInterface):
        self.players = []
        self.io_interface = io_interface
        self.dealer = Dealer("Dealer", io_interface)
        self.rules = rules
        self.shoe = Shoe(num_decks=rules.num_decks, penetration=0.75)
        self.current_state = WaitingForPlayersState()
        self.stats = SimulationStats()
        self.visible_cards = []

    def add_visible_card(self, card):
        """Add a card to the list of visible cards."""
        self.visible_cards.append(card)

    def set_state(self, state):
        """Change the current state of the game."""
        self.io_interface.output(f"Changing state to {state}.")
        self.current_state = state

    def add_player(self, player):
        """Add a player to the game."""
        if player is None:
            self.io_interface.output("Invalid player.")
            return

        if not isinstance(self.current_state, WaitingForPlayersState):
            self.io_interface.output("Game has already started.")
            return

        player.game = self
        if self.current_state is not None:
            self.current_state.add_player(self, player)

    def play_round(self):
        """Play a round of the game until it reaches the end state."""
        while not isinstance(self.current_state, EndRoundState):
            self.current_state.handle(self)
        self.current_state.handle(self)

    def reset(self):
        """Reset the game by shuffling the shoe and resetting all players."""
        self.shoe.shuffle()
        for player in self.players:
            player.reset()
        self.dealer.reset()
        self.visible_cards = []

    def is_blackjack(self, hand):
        """Check if a hand is a blackjack."""
        return self.rules.is_blackjack(hand)

    def should_dealer_hit(self):
        """Determine if the dealer should hit based on the game rules."""
        return self.rules.should_dealer_hit(self.dealer.current_hand)

    def can_split(self, hand):
        """Check if the hand can be split."""
        return self.rules.can_split(hand)

    def can_double_down(self, hand):
        """Check if the hand can be doubled down."""
        return self.rules.can_double_down(hand)

    def can_insure(self, player):
        """Check if the player can opt for insurance."""
        return self.rules.can_insure(self.dealer.current_hand, player.current_hand)

    def can_surrender(self, hand):
        """Check if the player can surrender."""
        return self.rules.can_surrender(hand)

    def get_min_bet(self):
        """Get the minimum bet allowed in the game."""
        return self.rules.min_bet

    def get_max_bet(self):
        """Get the maximum bet allowed in the game."""
        return self.rules.max_bet

    def get_blackjack_payout(self):
        """Get the payout multiplier for a blackjack."""
        return self.rules.blackjack_payout

    def get_insurance_payout(self):
        """Get the payout multiplier for insurance."""
        return 2.0  # Standard insurance payout is 2:1

    def get_bonus_payout(self, card_combination):
        """Get the bonus payout for a specific card combination."""
        return self.rules.get_bonus_payout(card_combination)


def create_io_interface(args):
    """Create the IO interface based on the command line arguments."""
    strategy = None
    if args.console:
        io_interface = ConsoleIOInterface()
    elif args.log_file:
        io_interface = LoggingIOInterface(args.log_file)
    elif args.simulate:
        io_interface = DummyIOInterface()
        if args.strat:
            if args.strat == "count":
                strategy = CountingStrategy()
            elif args.strat == "aggro":
                strategy = AggressiveStrategy()
            elif args.strat == "martin":
                strategy = MartingaleStrategy()
            else:
                strategy = BasicStrategy()
        else:
            strategy = BasicStrategy()
    else:
        io_interface = ConsoleIOInterface()
        strategy = BasicStrategy()
    return io_interface, strategy


def play_game(rules, io_interface, player_names, strategy):
    """
    Function to play a single game of Blackjack, to be executed in a separate process.
    """
    players = [Player(name, io_interface, strategy) for name in player_names]
    game = BlackjackGame(rules, io_interface)

    for player in players:
        game.add_player(player)

    game.set_state(PlacingBetsState())
    game.play_round()

    net_earnings = sum(player.money - 1000 for player in game.players)
    total_bets = sum(player.total_bets for player in game.players)

    if isinstance(strategy, CountingStrategy):
        strategy.update_decks_remaining(len(game.visible_cards))

    game.reset()

    return net_earnings, total_bets, game.stats.report()


def play_game_batch(rules, io_interface, player_names, num_games, strategy):
    """Function to play a batch of games of Blackjack, to be executed in a separate process."""
    results = []
    earnings = []
    total_bets = 0
    for _ in range(num_games):
        game_earnings, game_bets, result = play_game(
            rules, io_interface, player_names, strategy
        )
        results.append(result)
        earnings.append(game_earnings)
        total_bets += game_bets
    return results, earnings, total_bets


def play_game_and_record(rules, io_interface, player_names, strategy):
    """
    Play a single game of Blackjack and record the card sequence.
    """
    players = [Player(name, io_interface, strategy) for name in player_names]
    game = BlackjackGame(rules, io_interface)

    for player in players:
        game.add_player(player)

    game.set_state(PlacingBetsState())

    initial_shoe = deepcopy(game.shoe)

    game.play_round()

    earnings = sum(player.money - 1000 for player in game.players)
    total_bets = sum(sum(player.bets) for player in game.players)

    return earnings, total_bets, game.stats.report(), initial_shoe


def replay_game_with_strategy(
    rules, io_interface, player_names, strategy, initial_deck
):
    """
    Replay a game with a specific strategy and initial deck state.
    """
    players = [Player(name, io_interface, strategy) for name in player_names]
    game = BlackjackGame(rules, io_interface)

    for player in players:
        game.add_player(player)

    game.set_state(PlacingBetsState())

    game.shoe = initial_deck

    game.play_round()

    earnings = sum(player.money - 1000 for player in game.players)
    total_bets = sum(sum(player.bets) for player in game.players)

    return earnings, total_bets, game.stats.report()


def run_strategy_analysis(args, rules):
    strategies = {
        "Basic": BasicStrategy(),
        "Counting": CountingStrategy(),
        "Aggressive": AggressiveStrategy(),
        "Martingale": MartingaleStrategy(),
    }

    results = {
        strategy: {
            "net_earnings": 0,
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
        }
        for strategy in strategies
    }
    player_names = ["Bob"]

    graph = (
        MultiStrategyBlackjackGraph(args.num_games, strategies.keys())
        if args.vis
        else None
    )

    for game_number in range(args.num_games):
        print(f"\nPlaying game {game_number + 1}")

        _, _, _, initial_deck = play_game_and_record(
            rules, DummyIOInterface(), player_names, BasicStrategy()
        )

        for strategy_name, strategy in strategies.items():
            earnings, total_bets, result = replay_game_with_strategy(
                rules,
                DummyIOInterface(),
                player_names,
                strategy,
                deepcopy(initial_deck),
            )

            results[strategy_name]["net_earnings"] += earnings
            results[strategy_name]["total_bets"] += total_bets
            results[strategy_name]["wins"] += result["player_wins"]
            results[strategy_name]["losses"] += result["dealer_wins"]
            results[strategy_name]["draws"] += result["draws"]

            if graph:
                graph.update(
                    strategy_name,
                    game_number + 1,
                    results[strategy_name]["net_earnings"],
                )

    print("\nStrategy Analysis Results:")
    print("--------------------------")
    for strategy_name, result in results.items():
        print(f"\n{strategy_name} Strategy:")
        print(f"Net Earnings: ${result['net_earnings']:,.2f}")
        print(f"Total Bets: ${result['total_bets']:,.2f}")
        print(f"Wins: {result['wins']:,}")
        print(f"Losses: {result['losses']:,}")
        print(f"Draws: {result['draws']:,}")

        total_games = result["wins"] + result["losses"] + result["draws"]
        if total_games > 0:
            win_rate = result["wins"] / total_games
            print(f"Win Rate: {win_rate:.2%}")

        if result["total_bets"] > 0:
            house_edge = (
                (result["total_bets"] - result["net_earnings"]) / result["total_bets"]
            ) * 100
            print(f"House Edge: {house_edge:.2f}%")

    best_strategy = max(results, key=lambda x: results[x]["net_earnings"])
    worst_strategy = min(results, key=lambda x: results[x]["net_earnings"])

    print(f"\nBest Performing Strategy: {best_strategy}")
    print(f"Worst Performing Strategy: {worst_strategy}")

    if args.vis:
        plt.ioff()
        plt.show()  # Keep the graph window open after simulation ends


def create_rules(args):
    """Create the Rules object based on the command line arguments."""
    return Rules(
        blackjack_payout=1.5,
        dealer_hit_soft_17=False,
        dealer_peek=True,
        allow_split=True,
        allow_double_down=True,
        allow_double_after_split=True,
        allow_insurance=True,
        allow_surrender=True,
        num_decks=6,
        min_bet=args.min_bet,
        max_bet=args.max_bet,
    )


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
    parser.add_argument(
        "--strat",
        type=str,
        choices=["basic", "count", "aggro", "martin"],
        default="basic",
        help="Pick your strategy. 'basic' for basic strategy, 'count' for counting cards, 'aggro' for aggressive strategy",
    )
    parser.add_argument(
        "--vis",
        action="store_true",
        help="Visualize the simulation results in real-time graph.",
        default=False,
    )
    parser.add_argument(
        "--analysis",
        action="store_true",
        help="Analyze every strategy, compare results",
        default=False,
    )
    parser.add_argument("--min_bet", type=int, default=10, help="Minimum bet amount")
    parser.add_argument("--max_bet", type=int, default=1000, help="Maximum bet amount")
    args = parser.parse_args()

    io_interface, strategy = create_io_interface(args)
    rules = create_rules(args)

    profiler = None
    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()

    if args.console:
        for _ in range(args.num_games):
            game = BlackjackGame(rules, io_interface)
            player = Player("Player1", io_interface, strategy)
            game.add_player(player)
            game.play_round()

    elif args.analysis:
        run_strategy_analysis(args, rules)
    elif args.simulate:
        start_time = time.time()  # Record the start time

        graph = BlackjackGraph(args.num_games) if args.vis else None

        net_earnings = 0
        total_bets = 0
        results = []

        if args.single_cpu:
            # Run simulations sequentially
            for i in range(args.num_games):
                earnings, bets, result = play_game(
                    rules, DummyIOInterface(), ["Bob"], strategy
                )
                net_earnings += earnings
                total_bets += bets
                if graph:
                    graph.update(i + 1, net_earnings)
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
                    (rules, DummyIOInterface(), ["Bob"], game_count, strategy)
                    for game_count in game_batches
                ]
                batch_results = pool.starmap(play_game_batch, batch_args)
                game_number = 0
                for batch_result, batch_earnings, batch_bets in batch_results:
                    total_bets += batch_bets
                    for result, earnings in zip(batch_result, batch_earnings):
                        game_number += 1
                        net_earnings += earnings
                        if graph:
                            graph.update(game_number, net_earnings)
                        results.append(result)

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

        if total_bets > 0:
            house_edge = (
                -net_earnings / total_bets
            ) * 100  # Negative because player's net earnings are negative when the house wins
        else:
            house_edge = 0

        print("Simulation completed.")
        print(f"Games played (excluding pushes): {games_played_excluding_pushes:,}")
        print(f"Player wins: {total_player_wins:,}")
        print(f"Dealer wins: {total_dealer_wins:,}")
        print(f"Draws: {total_draws:,}")
        print(f"Net Earnings: ${net_earnings:,.2f}")
        print(f"Total Bets: ${total_bets:,.2f}")
        print(f"House Edge: {house_edge:.2f}%")

        print(f"\nDuration of simulation: {duration:.2f} seconds")
        print(f"Games simulated per second: {games_per_second:,.2f}")

        if graph:
            plt.ioff()
            plt.show()  # Keep the graph window open after simulation ends

    if args.profile and profiler is not None:
        profiler.disable()
        s = io.StringIO()
        sortby = "tottime"
        ps = pstats.Stats(profiler, stream=s).sort_stats(sortby)
        ps.print_stats()
        print(s.getvalue())


if __name__ == "__main__":
    main()
