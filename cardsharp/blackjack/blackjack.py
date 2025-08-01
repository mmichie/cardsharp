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
import os

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
from typing import Optional


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

    def __init__(
        self, rules: Rules, io_interface: IOInterface, shoe: Optional[Shoe] = None
    ):
        self.players = []
        self.io_interface = io_interface
        self.dealer = Dealer("Dealer", io_interface)
        self.rules = rules
        self.shoe = (
            shoe
            if shoe
            else Shoe(
                num_decks=rules.num_decks,
                penetration=rules.penetration,
                use_csm=rules.is_using_csm(),
                burn_cards=rules.burn_cards,
                deck_factory=rules.variant.create_deck if rules.variant else None,
            )
        )
        self.current_state = WaitingForPlayersState()
        self.stats = SimulationStats()
        self.visible_cards = []
        self.minimum_players = 1

        # Cache variant components for performance
        if hasattr(rules, "variant") and rules.variant:
            self.win_resolver = rules.variant.get_win_resolver()
            self.payout_calculator = rules.variant.get_payout_calculator()
            # Store the variant itself, not the bound method
            self.variant = rules.variant
        else:
            self.win_resolver = None  # type: ignore
            self.payout_calculator = None  # type: ignore
            self.variant = None  # type: ignore

    def add_visible_card(self, card):
        """Add a card to the list of visible cards."""
        self.visible_cards.append(card)

    def set_state(self, state):
        """Change the current state of the game."""
        # During simulation with DummyIOInterface, no need to output
        if not isinstance(self.io_interface, DummyIOInterface):
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
        """Reset the game by resetting all players."""
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
        return self.rules.get_insurance_payout()

    def get_bonus_payout(self, card_combination):
        """Get the bonus payout for a specific card combination."""
        return self.rules.get_bonus_payout(card_combination)

    def apply_dealer_error(self, error_type: str, **params):
        """
        Apply a dealer error to the current game state.

        Args:
            error_type: Type of dealer error to apply
            **params: Additional parameters specific to the error type

        Returns:
            Boolean indicating if the error was successfully applied
        """
        if not hasattr(self, "dealer") or not self.dealer:
            return False

        # Apply the error based on type
        if error_type == "card_exposure":
            # Dealer accidentally exposes a card
            # This is primarily handled in the EnvironmentIntegrator class
            # since it requires direct interaction with player strategy
            return True

        elif error_type == "miscount":
            # Dealer miscounts hand value
            # This could affect the dealer's decision to hit/stand
            if hasattr(self.dealer, "current_hand"):
                error_direction = params.get(
                    "error_direction", 1
                )  # 1=too high, -1=too low
                error_amount = params.get("error_amount", 1)

                # Store original value method
                hand = self.dealer.current_hand
                original_value = hand.value()

                # Create a closure to override the value method
                def miscount_value():
                    return original_value + (error_direction * error_amount)

                # Store original method reference
                original_method = hand.value

                # Apply the override
                hand.value = miscount_value

                # Schedule restoration
                import threading

                threading.Timer(
                    0.1, lambda: setattr(hand, "value", original_method)
                ).start()

                return True

        elif error_type == "payout":
            # Dealer makes a payout error
            # This would need to adjust player winnings
            player = params.get("player")
            if player and player in self.players:
                is_overpay = params.get("is_overpay", True)
                error_amount = params.get("error_amount", 0)

                if error_amount > 0:
                    if is_overpay:
                        player.money += error_amount
                    else:
                        player.money -= min(error_amount, player.money)
                    return True

        elif error_type == "procedure":
            # Dealer makes a procedural error
            procedure_type = params.get("procedure_type", "hit_when_should_stand")

            if procedure_type == "hit_when_should_stand" and self.dealer.current_hand:
                # Dealer hits when they should stand
                card = self.shoe.deal()
                self.dealer.add_card(card)
                self.add_visible_card(card)
                self.io_interface.output(f"Dealer accidentally hits and gets {card}.")
                return True

            elif procedure_type == "stand_when_should_hit" and self.dealer.current_hand:
                # Dealer stands when they should hit (harder to simulate)
                # This would need to override dealer's decision logic temporarily
                return True

        # Error type not recognized or couldn't be applied
        return False


def create_io_interface(args):
    """Create the IO interface based on the command line arguments."""
    strategy = None
    if args.console:
        io_interface = ConsoleIOInterface()
    elif args.log_file:
        io_interface = LoggingIOInterface(args.log_file)
    elif args.simulate:
        io_interface = DummyIOInterface()
        # Disable decision logging in simulation mode
        os.environ["BLACKJACK_DISABLE_LOGGING"] = "1"
        from cardsharp.blackjack.decision_logger import decision_logger
        import logging

        decision_logger.set_level(logging.ERROR)
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


def play_game(
    rules,
    io_interface,
    player_names,
    strategy,
    shoe: Optional[Shoe] = None,
    initial_bankroll: int = 1000,
):
    """
    Function to play a single game of Blackjack, to be executed in a separate process.
    Now accepts an optional shoe parameter and initial bankroll.
    """
    # Track initial cut card state
    initial_cut_card_state = shoe.is_cut_card_reached() if shoe else False

    players = [
        Player(name, io_interface, strategy, initial_money=initial_bankroll)
        for name in player_names
    ]
    game = BlackjackGame(rules, io_interface, shoe)

    for player in players:
        game.add_player(player)

    game.set_state(PlacingBetsState())
    game.play_round()

    net_earnings = sum(player.money - initial_bankroll for player in game.players)
    total_bets = sum(player.total_bets for player in game.players)

    if isinstance(strategy, CountingStrategy):
        strategy.update_decks_remaining(len(game.visible_cards))

        # Check if shoe shuffled during this game (cut card was reached then reset)
        final_cut_card_state = game.shoe.is_cut_card_reached() if game.shoe else False
        if initial_cut_card_state and not final_cut_card_state:
            # Shoe was shuffled during the game
            strategy.reset_count()

    game.reset()

    return net_earnings, total_bets, game.stats.report(), game.shoe


def play_game_batch(
    rules, io_interface, player_names, num_games, strategy, initial_bankroll: int = 1000
):
    """Function to play a batch of games of Blackjack, to be executed in a separate process."""
    # Ensure logging is disabled in worker processes
    import os

    os.environ["BLACKJACK_DISABLE_LOGGING"] = "1"

    # Also disable decision logger in worker process
    from cardsharp.blackjack.decision_logger import decision_logger
    import logging

    decision_logger.set_level(logging.ERROR)

    # Clear any accumulated state in the decision logger
    decision_logger.decision_history.clear()
    decision_logger.current_round_decisions.clear()

    shoe = Shoe(
        num_decks=rules.num_decks,
        penetration=rules.penetration,
        use_csm=rules.is_using_csm(),
        burn_cards=rules.burn_cards,
        deck_factory=rules.variant.create_deck if rules.variant else None,
    )
    results = []
    earnings = []
    total_bets = 0

    # Track cards remaining to detect shuffles
    prev_cards_remaining = shoe.cards_remaining

    for _ in range(num_games):
        game_earnings, game_bets, result, current_shoe = play_game(
            rules, io_interface, player_names, strategy, shoe, initial_bankroll
        )
        shoe = current_shoe
        results.append(result)
        earnings.append(game_earnings)
        total_bets += game_bets

        # Check if shoe was shuffled (cards remaining increased)
        if isinstance(strategy, CountingStrategy) and shoe:
            curr_cards_remaining = shoe.cards_remaining
            if curr_cards_remaining > prev_cards_remaining:
                # Shoe was shuffled, reset count
                strategy.reset_count()
            prev_cards_remaining = curr_cards_remaining

    return results, earnings, total_bets


def play_game_and_record(
    rules,
    io_interface,
    player_names,
    strategy,
    shoe: Optional[Shoe] = None,
    initial_bankroll: int = 1000,
):
    """
    Play a single game of Blackjack and record the card sequence.
    Now accepts an optional shoe parameter and initial bankroll.
    """
    players = [
        Player(name, io_interface, strategy, initial_money=initial_bankroll)
        for name in player_names
    ]
    game = BlackjackGame(rules, io_interface, shoe)

    for player in players:
        game.add_player(player)

    game.set_state(PlacingBetsState())

    game.play_round()

    earnings = sum(player.money - initial_bankroll for player in game.players)
    total_bets = sum(sum(player.bets) for player in game.players)

    return earnings, total_bets, game.stats.report(), game.shoe


def replay_game_with_strategy(
    rules, io_interface, player_names, strategy, shoe, initial_bankroll: int = 1000
):
    """
    Replay a game with a specific strategy and shoe state.
    """
    players = [
        Player(name, io_interface, strategy, initial_money=initial_bankroll)
        for name in player_names
    ]
    game = BlackjackGame(rules, io_interface, shoe)

    for player in players:
        game.add_player(player)

    game.set_state(PlacingBetsState())
    game.play_round()

    earnings = sum(player.money - initial_bankroll for player in game.players)
    total_bets = sum(sum(player.bets) for player in game.players)

    return earnings, total_bets, game.stats.report()


def run_strategy_analysis(args, rules, initial_bankroll: int = 1000):
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

    # Initialize shoe once here instead of per game
    initial_shoe = Shoe(
        num_decks=rules.num_decks,
        penetration=rules.penetration,
        use_csm=rules.is_using_csm(),
        burn_cards=rules.burn_cards,
        deck_factory=rules.variant.create_deck if rules.variant else None,
    )

    graph = (
        MultiStrategyBlackjackGraph(args.num_games, strategies.keys())
        if args.vis
        else None
    )

    for game_number in range(args.num_games):
        print(f"\nPlaying game {game_number + 1}")

        # Record game with base strategy using the shared shoe
        _, _, _, current_shoe_state = play_game_and_record(
            rules,
            DummyIOInterface(),
            player_names,
            BasicStrategy(),
            initial_shoe,
            initial_bankroll,
        )

        # Reset shoe to state after recording
        initial_shoe = deepcopy(current_shoe_state)

        for strategy_name, strategy in strategies.items():
            earnings, total_bets, result = replay_game_with_strategy(
                rules,
                DummyIOInterface(),
                player_names,
                strategy,
                deepcopy(current_shoe_state),  # Use the recorded shoe state
                initial_bankroll,
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
    # Define default bonus payouts
    default_bonus_payouts = {}

    # Only use bonus payouts if they are explicitly enabled or not explicitly disabled
    if args.enable_bonus_payouts or (
        not args.disable_bonus_payouts and not hasattr(args, "enable_bonus_payouts")
    ):
        default_bonus_payouts = {
            "suited-6-7-8": 2.0,  # Pays 2:1 for suited 6-7-8
            "7-7-7": 3.0,  # Pays 3:1 for three 7s
            "five-card-21": 1.5,  # Pays 1.5:1 for a 5+ card 21
        }

    return Rules(
        blackjack_payout=1.5,
        dealer_hit_soft_17=args.dealer_hit_soft_17,
        dealer_peek=True,
        allow_split=True,
        allow_double_down=True,
        allow_double_after_split=True,
        allow_insurance=True,
        allow_surrender=True,
        num_decks=args.num_decks,
        min_bet=args.min_bet,
        max_bet=args.max_bet,
        insurance_payout=args.insurance_payout,
        allow_resplitting=args.allow_resplitting,
        allow_late_surrender=args.allow_late_surrender,
        allow_early_surrender=args.allow_early_surrender,
        use_csm=args.use_csm,
        time_limit=args.time_limit,
        max_splits=args.max_splits,
        bonus_payouts=default_bonus_payouts,
        penetration=args.penetration,
        burn_cards=args.burn_cards,
        variant=args.variant,
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
    parser.add_argument(
        "--bankroll", type=int, default=1000, help="Initial player bankroll/money"
    )
    parser.add_argument(
        "--insurance_payout",
        type=float,
        default=2.0,
        help="Insurance payout multiplier",
    )
    parser.add_argument(
        "--dealer_hit_soft_17", action="store_true", help="Dealer hits on soft 17"
    )
    parser.add_argument(
        "--allow_resplitting", action="store_true", help="Allow resplitting"
    )
    parser.add_argument(
        "--allow_late_surrender", action="store_true", help="Allow late surrender"
    )
    parser.add_argument(
        "--allow_early_surrender", action="store_true", help="Allow early surrender"
    )
    parser.add_argument(
        "--use_csm", action="store_true", help="Use continuous shuffling machine"
    )
    parser.add_argument(
        "--time_limit",
        type=int,
        default=0,
        help="Time limit for player decisions (0 for no limit)",
    )
    parser.add_argument(
        "--max_splits", type=int, default=3, help="Maximum number of splits allowed"
    )
    parser.add_argument(
        "--num_decks", type=int, default=6, help="Number of decks in the shoe"
    )
    parser.add_argument(
        "--enable_bonus_payouts",
        action="store_true",
        help="Enable bonus payouts for special combinations",
    )
    parser.add_argument(
        "--disable_bonus_payouts", action="store_true", help="Disable all bonus payouts"
    )
    parser.add_argument(
        "--penetration",
        type=float,
        default=0.75,
        help="Deck penetration before reshuffling (0.0-1.0, default 0.75)",
    )
    parser.add_argument(
        "--burn_cards",
        type=int,
        default=0,
        help="Number of cards to burn after each shuffle (default 0)",
    )
    parser.add_argument(
        "--variant",
        type=str,
        default="classic",
        choices=["classic", "spanish21"],
        help="Blackjack variant to play (default: classic)",
    )
    args = parser.parse_args()

    io_interface, strategy = create_io_interface(args)
    rules = create_rules(args)

    profiler = None
    if args.profile:
        profiler = cProfile.Profile()
        profiler.enable()

    if args.console:
        # Initialize shoe once for console mode
        shoe = Shoe(
            num_decks=rules.num_decks,
            penetration=rules.penetration,
            use_csm=rules.is_using_csm(),
            burn_cards=rules.burn_cards,
            deck_factory=rules.variant.create_deck if rules.variant else None,
        )
        for _ in range(args.num_games):
            game = BlackjackGame(rules, io_interface, shoe)
            player = Player(
                "Player1", io_interface, strategy, initial_money=args.bankroll
            )
            game.add_player(player)
            game.play_round()
            shoe = game.shoe  # Update shoe state for next game

    elif args.analysis:
        run_strategy_analysis(args, rules, args.bankroll)
    elif args.simulate:
        start_time = time.time()
        graph = BlackjackGraph(args.num_games) if args.vis else None
        net_earnings = 0
        total_bets = 0
        results = []

        if args.single_cpu:
            # Initialize shoe once for single CPU mode
            shoe = Shoe(
                num_decks=rules.num_decks,
                penetration=rules.penetration,
                use_csm=rules.is_using_csm(),
                burn_cards=rules.burn_cards,
                deck_factory=rules.variant.create_deck if rules.variant else None,
            )
            for i in range(args.num_games):
                earnings, bets, result, current_shoe = play_game(
                    rules, DummyIOInterface(), ["Bob"], strategy, shoe, args.bankroll
                )
                shoe = current_shoe  # Update shoe state for next game
                net_earnings += earnings
                total_bets += bets
                if graph:
                    graph.update(i + 1, net_earnings)
                results.append(result)
        else:
            # For parallel processing, we still need separate shoes per process
            cpu_count = multiprocessing.cpu_count()
            games_per_cpu, remainder = divmod(args.num_games, cpu_count)
            game_batches = [
                games_per_cpu + (1 if i < remainder else 0) for i in range(cpu_count)
            ]

            with multiprocessing.Pool() as pool:
                batch_args = [
                    (
                        rules,
                        DummyIOInterface(),
                        ["Bob"],
                        game_count,
                        strategy,
                        args.bankroll,
                    )
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

        end_time = time.time()
        duration = end_time - start_time
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

        if games_played_excluding_pushes != 0:
            player_win_rate = total_player_wins / games_played_excluding_pushes * 100
            dealer_win_rate = total_dealer_wins / games_played_excluding_pushes * 100
            print(f"Player win rate: {player_win_rate:.2f}%")
            print(f"Dealer win rate: {dealer_win_rate:.2f}%")

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
