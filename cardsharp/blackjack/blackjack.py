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
import logging
import multiprocessing
import time
import cProfile
import pstats
import io
import matplotlib.pyplot as plt
import threading
import os

import random

from cardsharp.blackjack.actor import Dealer, Player
from cardsharp.blackjack.state import (
    STATE_END_ROUND,
    STATE_WAITING,
    _state_waiting,
    _state_placing_bets,
)
from cardsharp.blackjack.stats import SimulationStats
from cardsharp.blackjack.strategy import (
    AggressiveStrategy,
    BasicStrategy,
    CountingStrategy,
    MartingaleStrategy,
)
from cardsharp.common.shoe import Shoe
from cardsharp.common.io_interface import (
    ConsoleIOInterface,
    IOInterface,
    DummyIOInterface,
    LoggingIOInterface,
)
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.decision_logger import decision_logger
from cardsharp.fastsim import resolve_engine, run_fast_batch
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
        self.current_state = _state_waiting
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

        # Cache frequently accessed rules attributes for performance
        self._min_bet = rules.min_bet
        self._max_bet = rules.max_bet
        self._blackjack_payout = rules.blackjack_payout
        self._allow_insurance = rules.allow_insurance
        self._allow_surrender = rules.allow_surrender

        # Cache IO check for performance (avoid repeated isinstance checks)
        self._is_dummy_io = isinstance(io_interface, DummyIOInterface)

        # Track whether any player needs visible card tracking (counting strategies)
        self._track_visible_cards = True  # Updated in add_player

    def _update_visible_card_tracking(self):
        """Check if any player strategy needs visible card tracking."""
        self._track_visible_cards = any(
            hasattr(p, "strategy") and hasattr(p.strategy, "update_count")
            for p in self.players
        )

    def add_visible_card(self, card):
        """Add a card to the list of visible cards (skipped if no counter)."""
        if self._track_visible_cards:
            self.visible_cards.append(card)

    def output(self, message):
        """
        Output a message through the IO interface.

        Optimized to check cached _is_dummy_io flag instead of
        calling isinstance() repeatedly.
        """
        if not self._is_dummy_io:
            self.io_interface.output(message)

    def set_state(self, state):
        """Change the current state of the game."""
        # During simulation with DummyIOInterface, no need to output
        if not self._is_dummy_io:
            self.io_interface.output(f"Changing state to {state}.")
        self.current_state = state

    def add_player(self, player):
        """Add a player to the game."""
        if player is None:
            self.output("Invalid player.")
            return

        if self.current_state.STATE_ID != STATE_WAITING:
            self.output("Game has already started.")
            return

        player.game = self
        if self.current_state is not None:
            self.current_state.add_player(self, player)
        self._update_visible_card_tracking()

    def play_round(self):
        """Play a round of the game until it reaches the end state."""
        while self.current_state.STATE_ID != STATE_END_ROUND:
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

    def get_min_bet(self):
        """Get the minimum bet allowed in the game."""
        return self._min_bet

    def get_max_bet(self):
        """Get the maximum bet allowed in the game."""
        return self._max_bet

    def get_blackjack_payout(self):
        """Get the payout multiplier for a blackjack."""
        return self._blackjack_payout

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

                # Inject a miscounted value into the hand's cache
                hand = self.dealer.current_hand
                original_value = hand.value()
                hand._cache["value"] = original_value + (error_direction * error_amount)

                # Schedule cache invalidation so subsequent calls recalculate
                import threading

                threading.Timer(
                    0.1, lambda: hand._cache.update({"value": None})
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


def generate_player_names(num_players: int) -> list[str]:
    """
    Generate player names for simulation.

    Args:
        num_players: Number of players to generate names for

    Returns:
        List of player names (e.g., ["Player1", "Player2", ...])
    """
    if num_players == 1:
        return ["Player"]
    return [f"Player{i+1}" for i in range(num_players)]


def create_io_interface(args, rules=None):
    """Create the IO interface and the player strategy.

    rules is optional but required for strategies whose construction
    depends on the rule set (currently: solver). All other built-in
    strategies (basic/count/aggro/martin) ignore it.
    """
    from cardsharp.blackjack.strategy import create_strategy

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
        strategy = create_strategy(
            args.strat or "basic",
            rules=rules,
            num_decks=args.num_decks,
        )
    else:
        io_interface = ConsoleIOInterface()
        strategy = create_strategy("basic", rules=rules)
    return io_interface, strategy


def _solver_card_value(card):
    """Convert a Card to the solver's CARD_VALUES integer (Ace=1, T/J/Q/K=10)."""
    from cardsharp.common.card import Rank

    if card.rank == Rank.ACE:
        return 1
    return min(card.bj_value, 10)


def build_deal_ev_table(ev_table, rules):
    """Build (c1,c2,up) -> E[X | deal], including dealer-BJ branch.

    The simulator's actual outcome X conditional on the deal includes the
    case where the dealer has a natural BJ (player loses, or pushes if also
    BJ). The raw ev_table[deal].best_ev assumes no dealer BJ, so using it
    directly as the control-variate Y would mismatch X. This builder
    replicates the solver's per-deal aggregation formula so the resulting
    table satisfies E[Y] = sol.house_edge (sign-flipped), making the
    control-variate estimator unbiased in the simulator's frame.
    """
    from cardsharp.blackjack.solver.types import (
        Deck,
        hand_state_from_cards,
    )
    from cardsharp.blackjack.solver.dealer import dealer_blackjack_prob

    deck = Deck.finite(rules.num_decks) if rules.num_decks <= 8 else Deck.infinite()
    bj_payout = rules.blackjack_payout

    deal_ev = {}
    for c1 in range(1, 11):
        for c2 in range(c1, 11):
            for up in range(1, 11):
                key = (c1, c2, up)
                sev = ev_table.get(key)
                if sev is None:
                    continue
                _, _, disp, _ = hand_state_from_cards(c1, c2)
                is_player_bj = disp == 21 and (c1 == 1 or c2 == 1) and c1 != c2

                deck1 = deck.remove_card(c1)
                deck2 = deck1.remove_card(c2)
                deck3 = deck2.remove_card(up)
                p_dbj = dealer_blackjack_prob(up, deck3)

                if is_player_bj:
                    deal_ev[key] = (1.0 - p_dbj) * bj_payout
                else:
                    deal_ev[key] = p_dbj * (-1.0) + (1.0 - p_dbj) * sev.best_ev
    return deal_ev


def _compute_deal_y(game, deal_ev_table):
    """Look up the solver's bet-weighted predicted profit for this round's deal.

    Returns Y in the same units as X = net/initial_bet (player's view, profit
    per dollar bet). Aggregates across players when there are multiple, weighted
    by each player's initial bet.
    """
    upcard = _solver_card_value(game.dealer.current_hand.cards[0])
    weighted_ev = 0.0
    bet_total = 0.0
    for player in game.players:
        if not player.hands or len(player.hands[0].cards) < 2:
            continue
        c1 = _solver_card_value(player.hands[0].cards[0])
        c2 = _solver_card_value(player.hands[0].cards[1])
        if c1 > c2:
            c1, c2 = c2, c1
        bet = player.bets[0] if player.bets else 0
        if bet == 0:
            continue
        ev = deal_ev_table.get((c1, c2, upcard))
        if ev is None:
            continue
        weighted_ev += ev * bet
        bet_total += bet
    return weighted_ev / bet_total if bet_total > 0 else 0.0


def play_game(
    rules,
    io_interface,
    player_names,
    strategy,
    shoe: Optional[Shoe] = None,
    initial_bankroll: int = 1000,
    ev_table=None,
):
    """
    Function to play a single game of Blackjack, to be executed in a separate process.
    Now accepts an optional shoe parameter and initial bankroll.

    If ev_table is provided, the round's deal state is captured between the
    DEALING and PLAYERS_TURN states and looked up in ev_table to provide a
    control-variate Y to record_round.
    """
    cards_before = shoe.cards_remaining if shoe else None

    players = [
        Player(name, io_interface, strategy, initial_money=initial_bankroll)
        for name in player_names
    ]
    game = BlackjackGame(rules, io_interface, shoe)

    for player in players:
        game.add_player(player)

    game.set_state(_state_placing_bets)

    deal_y = None
    if ev_table is None:
        game.play_round()
    else:
        # Step the state machine manually so we can capture the deal state
        # AFTER DealingState.handle() runs but before player play mutates it.
        from cardsharp.blackjack.state import STATE_DEALING

        while game.current_state.STATE_ID != STATE_END_ROUND:
            prev_state_id = game.current_state.STATE_ID
            game.current_state.handle(game)
            if prev_state_id == STATE_DEALING and deal_y is None:
                deal_y = _compute_deal_y(game, ev_table)
        game.current_state.handle(game)  # END_ROUND

    net_earnings = sum(player.money - initial_bankroll for player in game.players)
    total_bets = sum(player.total_bets for player in game.players)
    initial_bets = sum(player.initial_bets for player in game.players)

    # Record this round's financial outcome for variance/CI estimation.
    # Skip rounds with zero initial bet (broke player) so the ratio
    # estimator's denominator stays positive.
    if initial_bets > 0:
        game.stats.record_round(net_earnings, initial_bets, total_bets, cv_y=deal_y)

    if isinstance(strategy, CountingStrategy) and game.shoe:
        # Detect reshuffle: cards_remaining goes UP when shoe reshuffles.
        # cards_before is None when no shoe was passed (first game).
        reshuffled = (
            cards_before is not None and game.shoe.cards_remaining > cards_before
        )

        if reshuffled:
            strategy.reset_count()

        # Always count visible cards from this round (including dealer
        # hits that happen after decide_action). After a reshuffle,
        # these are the first cards from the fresh deck.
        for card in game.visible_cards:
            card_id = id(card)
            if card_id not in strategy.counted_cards:
                strategy.update_count(card)
                strategy.counted_cards.add(card_id)

        strategy.decks_remaining = max(0.5, game.shoe.cards_remaining / 52)

    game.reset()

    return net_earnings, total_bets, initial_bets, game.stats.report(), game.shoe


def play_game_batch(
    rules,
    io_interface,
    player_names,
    num_games,
    strategy,
    initial_bankroll: int = 1000,
    shuffle_type: str = "perfect",
    shuffle_count: Optional[int] = None,
    seed: Optional[int] = None,
    ev_table=None,
):
    """Function to play a batch of games of Blackjack, to be executed in a separate process.

    If seed is provided, the worker's global random state is seeded for
    reproducibility. Returns the batch-aggregated stats (as a dict),
    a per-round earnings list (for graphing), and the batch's total
    bet sum.
    """
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

    if seed is not None:
        random.seed(seed)

    shoe = Shoe(
        num_decks=rules.num_decks,
        penetration=rules.penetration,
        use_csm=rules.is_using_csm(),
        burn_cards=rules.burn_cards,
        deck_factory=rules.variant.create_deck if rules.variant else None,
        shuffle_type=shuffle_type,
        shuffle_count=shuffle_count,
    )
    agg_stats = SimulationStats()
    earnings = []
    total_bets = 0

    for _ in range(num_games):
        game_earnings, game_bets, game_initial, result, current_shoe = play_game(
            rules,
            io_interface,
            player_names,
            strategy,
            shoe,
            initial_bankroll,
            ev_table=ev_table,
        )
        shoe = current_shoe
        agg_stats.merge(SimulationStats.from_dict(result))
        earnings.append(game_earnings)
        total_bets += game_bets
        # Shuffle detection and count updates are handled inside play_game.

    return agg_stats.report(), earnings, total_bets


def run_solver(args, rules):
    """Run the exact probabilistic solver and display results."""
    from cardsharp.blackjack.solver import solve

    mode = args.solver_mode
    print(
        f"Solving for: {rules.num_decks}-deck "
        f"{'H17' if rules.dealer_hit_soft_17 else 'S17'}, "
        f"{'DAS' if rules.allow_double_after_split else 'no-DAS'}, "
        f"{'surrender' if rules.allow_surrender else 'no-surrender'}, "
        f"{'peek' if rules.dealer_peek else 'no-peek'}, "
        f"double on {rules.double_on}"
    )
    deck_mode = "infinite" if rules.num_decks > 8 else f"{rules.num_decks}-deck finite"
    print(f"Mode: {mode} ({deck_mode})\n")

    result = solve(rules, mode=mode)
    result.print_strategy()

    if args.diff_strategy:
        csv_path = os.path.join(os.path.dirname(__file__), "basic_strategy.csv")
        diffs = result.diff_strategy(csv_path)
        if diffs:
            print(f"\n{len(diffs)} differences vs basic_strategy.csv:")
            for d in diffs:
                print(f"  {d}")
        else:
            print("\nSolver matches basic_strategy.csv exactly.")

    # Show a few notable EV breakdowns
    print("\nNotable EV breakdowns:")
    notable = [
        ((6, 10, 10), "Hard 16 vs 10"),
        ((1, 7, 3), "Soft 18 vs 3"),
        ((8, 8, 10), "Pair 8 vs 10"),
    ]
    for key, label in notable:
        if key in result.ev_table:
            sev = result.ev_table[key]
            parts = []
            if sev.hit == sev.hit:  # not nan
                parts.append(f"hit={sev.hit:+.4f}")
            if sev.stand == sev.stand:
                parts.append(f"stand={sev.stand:+.4f}")
            if sev.double == sev.double:
                parts.append(f"double={sev.double:+.4f}")
            if sev.split == sev.split:
                parts.append(f"split={sev.split:+.4f}")
            if sev.surrender == sev.surrender:
                parts.append(f"surrender={sev.surrender:+.4f}")
            print(f"  {label}: {', '.join(parts)} -> {sev.best_action.value}")


def run_rule_comparison(args, baseline_rules):
    """Run a CRN comparison of two named rule sets.

    The two rule sets share every parameter from baseline_rules except
    the one knob being toggled by --compare_rules. Reports per-rule
    house edge plus a tightly-bounded paired-difference estimate.
    """
    # Match simulate-path noise suppression
    os.environ["BLACKJACK_DISABLE_LOGGING"] = "1"
    decision_logger.set_level(logging.ERROR)

    from cardsharp.blackjack.comparison import compare_rules
    from copy import copy

    def with_override(**kwargs):
        new = copy(baseline_rules)
        for k, v in kwargs.items():
            setattr(new, k, v)
        return new

    if args.compare_rules == "h17_vs_s17":
        pair = {
            "H17": with_override(dealer_hit_soft_17=True),
            "S17": with_override(dealer_hit_soft_17=False),
        }
    elif args.compare_rules == "bj_3_2_vs_6_5":
        pair = {
            "3:2": with_override(blackjack_payout=1.5),
            "6:5": with_override(blackjack_payout=1.2),
        }
    elif args.compare_rules == "peek_vs_no_peek":
        pair = {
            "peek": with_override(dealer_peek=True),
            "no-peek": with_override(dealer_peek=False),
        }
    elif args.compare_rules == "das_vs_no_das":
        pair = {
            "DAS": with_override(allow_double_after_split=True),
            "no-DAS": with_override(allow_double_after_split=False),
        }
    elif args.compare_rules == "surrender_vs_none":
        pair = {
            "LS": with_override(allow_surrender=True, allow_late_surrender=True),
            "no-surr": with_override(
                allow_surrender=False,
                allow_late_surrender=False,
                allow_early_surrender=False,
            ),
        }
    else:
        raise ValueError(f"Unknown comparison: {args.compare_rules}")

    print(f"Comparing: {args.compare_rules}")
    if args.solver_strategy:
        print("  Using per-rule solver strategy")
    if args.num_players > 1:
        print(f"  Table size: {args.num_players} players")
    result = compare_rules(
        rules_dict=pair,
        num_rounds=args.num_games,
        seed=args.seed,
        use_solver_strategy=args.solver_strategy,
        num_players=args.num_players,
    )
    result.print_report(confidence=args.confidence)


def run_strategy_analysis(args, rules, initial_bankroll: int = 1000):
    # Silence decision logging in analysis mode (same as simulate)
    os.environ["BLACKJACK_DISABLE_LOGGING"] = "1"
    decision_logger.set_level(logging.ERROR)

    # Solve once to provide an optimal-per-rules baseline alongside the
    # heuristic strategies. Solver cost is ~1s in fast mode, negligible
    # vs the simulation runtime.
    from cardsharp.blackjack.solver import solve
    from cardsharp.blackjack.strategy import SolverStrategy

    print("Solving rules for the optimal-strategy baseline...")
    sol = solve(rules, mode="auto")
    print(f"  Solver HE = {sol.house_edge * 100:.4f}%")

    strategies = {
        "Basic": BasicStrategy(),
        "Counting": CountingStrategy(num_decks=rules.num_decks),
        "Aggressive": AggressiveStrategy(),
        "Martingale": MartingaleStrategy(),
        "Solver": SolverStrategy(sol),
    }

    # Per-strategy SimulationStats accumulators give us Welford-tracked
    # variance and delta-method CIs for free.
    stats_per_strategy = {name: SimulationStats() for name in strategies}
    player_names = generate_player_names(args.num_players)

    def make_shoe():
        return Shoe(
            num_decks=rules.num_decks,
            penetration=rules.penetration,
            use_csm=rules.is_using_csm(),
            burn_cards=rules.burn_cards,
            deck_factory=rules.variant.create_deck if rules.variant else None,
            shuffle_type=args.shuffle_type,
            shuffle_count=args.shuffle_count,
        )

    # Each strategy gets its own shoe so stateful strategies (counting)
    # see the correct card history for their count.
    shoes = {name: make_shoe() for name in strategies}

    # Track running net earnings per strategy for the graph (cumulative
    # money change). Computed independently from the SimulationStats
    # bookkeeping so existing visualization stays untouched.
    running_net = {name: 0.0 for name in strategies}

    graph = (
        MultiStrategyBlackjackGraph(args.num_games, strategies.keys())
        if args.vis
        else None
    )

    for game_number in range(args.num_games):
        for strategy_name, strategy in strategies.items():
            earnings, total_bets, init_bets, result, shoes[strategy_name] = play_game(
                rules,
                DummyIOInterface(),
                player_names,
                strategy,
                shoes[strategy_name],
                initial_bankroll,
            )
            stats_per_strategy[strategy_name].merge(SimulationStats.from_dict(result))
            running_net[strategy_name] += earnings

            if graph:
                graph.update(
                    strategy_name,
                    game_number + 1,
                    running_net[strategy_name],
                )

    ci_pct = int(round(args.confidence * 100))
    print("\nStrategy Analysis Results:")
    print("--------------------------")
    for strategy_name, stats in stats_per_strategy.items():
        print(f"\n{strategy_name} Strategy:")
        print(f"Net Earnings: ${stats.net_sum:,.2f}")
        print(f"Total Bets: ${stats.total_bet_sum:,.2f}")
        print(f"Wins: {stats.player_wins:,}")
        print(f"Losses: {stats.dealer_wins:,}")
        print(f"Draws: {stats.draws:,}")

        wr = stats.win_rate_with_ci(args.confidence)
        if wr is not None:
            p, lo, hi, half = wr
            print(
                f"Win Rate: {p * 100:.2f}% +/- {half * 100:.2f}% "
                f"({ci_pct}% Wilson CI: [{lo * 100:.2f}%, {hi * 100:.2f}%])"
            )

        he = stats.house_edge_with_ci(args.confidence)
        if he is not None:
            edge, lo, hi, half = he
            print(
                f"Edge (initial wagers): {edge * 100:+.4f}% +/- "
                f"{half * 100:.4f}% "
                f"({ci_pct}% CI: [{lo * 100:+.4f}%, {hi * 100:+.4f}%])"
            )
        if stats.total_bet_sum > 0:
            edge_total = (-stats.net_sum / stats.total_bet_sum) * 100
            print(f"Edge (total action):   {edge_total:+.4f}%")

    best_strategy = max(stats_per_strategy, key=lambda n: running_net[n])
    worst_strategy = min(stats_per_strategy, key=lambda n: running_net[n])

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
        "--engine",
        type=str,
        choices=["auto", "fast", "python"],
        default="auto",
        help="Simulation engine: 'auto' uses the Rust fast core when it is "
        "installed and supports the requested configuration, 'fast' "
        "requires it (error otherwise), 'python' forces the reference "
        "engine (combine with --single_cpu to avoid multiprocessing).",
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
        choices=["basic", "count", "aggro", "martin", "solver"],
        default="basic",
        help="Pick your strategy. 'basic' = static CSV basic strategy, "
        "'count' = Hi-Lo card counter, 'aggro' = aggressive heuristic, "
        "'martin' = Martingale bet ramp, 'solver' = optimal-per-rules "
        "play computed from the solver at startup (~1s).",
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
    parser.add_argument(
        "--solve",
        action="store_true",
        help="Compute exact house edge and optimal strategy using the probabilistic solver (infinite deck)",
        default=False,
    )
    parser.add_argument(
        "--diff_strategy",
        action="store_true",
        help="With --solve, diff optimal strategy against basic_strategy.csv",
        default=False,
    )
    parser.add_argument(
        "--solver_mode",
        type=str,
        choices=["auto", "fast", "exact", "combinatorial"],
        default="auto",
        help="Solver mode: auto (deck-size-aware default), fast (~1s, small bias), "
        "exact (~1-5min, dynamic dealer probs), combinatorial (~1-10min, matches WoO)",
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
        "--num_players",
        type=int,
        default=1,
        help="Number of players at the table (1-7, default 1). "
        "Multiple players see more cards per round, improving card counting accuracy.",
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
    parser.add_argument(
        "--shuffle_type",
        type=str,
        default="perfect",
        choices=["perfect", "riffle", "strip"],
        help="Type of shuffle: 'perfect' (default, cryptographically random), "
        "'riffle' (realistic GSR model, 4 shuffles), "
        "'strip' (less effective, 6 shuffles)",
    )
    parser.add_argument(
        "--shuffle_count",
        type=int,
        default=None,
        help="Number of shuffles to perform (overrides default for shuffle type). "
        "Research shows 7 riffle shuffles needed for true randomness on 52 cards. "
        "Real dealers typically do 3-5 riffles (insufficient mixing).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed for reproducible simulation. If omitted, a seed "
        "is generated and printed so the run can be replayed.",
    )
    parser.add_argument(
        "--compare_rules",
        type=str,
        default=None,
        choices=[
            "h17_vs_s17",
            "bj_3_2_vs_6_5",
            "peek_vs_no_peek",
            "das_vs_no_das",
            "surrender_vs_none",
        ],
        help="Run a Common Random Numbers (CRN) comparison of two rule "
        "sets. Reports per-rule house edge plus the much tighter paired "
        "difference. Uses --num_games rounds. Comparisons whose effect "
        "is purely on player-decision incentives (DAS, surrender) only "
        "produce a non-zero diff with --solver_strategy, since the "
        "default CSV-based BasicStrategy does not branch on those rules.",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.95,
        help="Confidence level for reported intervals (default 0.95).",
    )
    parser.add_argument(
        "--cv",
        action="store_true",
        help="Use the solver's exact EV table as a control variate to "
        "tighten the simulator's house-edge CI. Solves the rules once at "
        "startup (~1s for fast mode); for each round, looks up the deal "
        "state's expected EV and uses it to absorb the between-deal "
        "variance from the Monte Carlo estimator.",
    )
    parser.add_argument(
        "--solver_strategy",
        action="store_true",
        help="Use the solver's optimal per-rules strategy instead of the "
        "static basic_strategy.csv. The CSV is rule-blind aside from a "
        "3-cell H17->S17 patch; the solver-derived strategy reflects the "
        "actual rule set (DAS, surrender, peek, blackjack payout, deck "
        "count). Required for --compare_rules to show a non-zero diff on "
        "rule changes that only affect player decisions (DAS).",
    )
    parser.add_argument(
        "--cd_strategy",
        action="store_true",
        help="Play the first decision of each hand composition-dependently "
        "from the solver's per-(card1,card2,upcard) EV table instead of "
        "the collapsed total-based table (e.g. 10+6 vs 9+7 against a 10 "
        "may play differently). Implies --solver_strategy. This is the "
        "strategy the solver's reported house edge models; worth a few "
        "basis points at 1-2 decks.",
    )
    args = parser.parse_args()
    if args.cd_strategy:
        args.solver_strategy = True

    # Validate num_players
    if args.num_players < 1 or args.num_players > 7:
        parser.error(
            "--num_players must be between 1 and 7 (typical blackjack table limit)"
        )

    rules = create_rules(args)
    io_interface, strategy = create_io_interface(args, rules)

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
            shuffle_type=args.shuffle_type,
            shuffle_count=args.shuffle_count,
        )
        for _ in range(args.num_games):
            game = BlackjackGame(rules, io_interface, shoe)
            player = Player(
                "Player1", io_interface, strategy, initial_money=args.bankroll
            )
            game.add_player(player)
            game.play_round()
            shoe = game.shoe  # Update shoe state for next game

    elif args.solve:
        run_solver(args, rules)
    elif args.analysis:
        run_strategy_analysis(args, rules, args.bankroll)
    elif args.compare_rules:
        run_rule_comparison(args, rules)
    elif args.simulate:
        # Establish a master seed: if user didn't provide one, generate
        # a fresh one from system entropy and print it so the run is
        # reproducible by re-running with --seed <value>.
        master_seed = args.seed
        if master_seed is None:
            master_seed = random.SystemRandom().randint(0, 2**63 - 1)
        random.seed(master_seed)
        print(f"Seed: {master_seed}")

        # If control variate or solver-strategy requested, solve the rules
        # once and reuse the result for both. build_deal_ev_table folds
        # in the dealer-BJ branch so that E[Y] in the simulator equals
        # -sol.house_edge under fresh-shoe conditions; without that fold,
        # Y is biased by ~0.5% and the CV estimator becomes inconsistent
        # with the baseline.
        deal_ev_table = None
        cv_mu_y = None
        if args.cv or args.solver_strategy:
            from cardsharp.blackjack.solver import solve

            solver_t0 = time.time()
            print("Solving rules...")
            # mode="auto": for ≤4 decks the solver routes to a more accurate
            # path (combinatorial / exact) so cv_mu_y and the solver strategy
            # table aren't biased by the static-dealer-prob shortcut. 5+ deck
            # shoes still take the fast path (bias < 0.005%).
            sol = solve(rules, mode="auto")
            print(
                f"Solver done ({time.time() - solver_t0:.2f}s). "
                f"Solver HE = {sol.house_edge * 100:.4f}%"
            )
            if args.cv:
                deal_ev_table = build_deal_ev_table(sol.ev_table, rules)
                cv_mu_y = -sol.house_edge
                print(f"  CV mu_Y = {cv_mu_y:+.6f}")
            if args.solver_strategy:
                from cardsharp.blackjack.strategy import SolverStrategy

                strategy = SolverStrategy(sol, use_ev_table=args.cd_strategy)
                print(
                    "  Using solver-derived strategy table"
                    + (" (composition-dependent)." if args.cd_strategy else ".")
                )

        start_time = time.time()
        graph = BlackjackGraph(args.num_games) if args.vis else None
        agg_stats = SimulationStats()
        agg_stats.cv_mu_y = cv_mu_y
        running_net_earnings = 0
        total_bets = 0
        player_names = generate_player_names(args.num_players)

        # Engine selection: the Rust fast core handles table-encodable
        # strategies on classic rules; anything it cannot reproduce
        # exactly falls back to the reference engine (loudly under
        # --engine fast, silently informative under auto).
        try:
            engine_choice = resolve_engine(
                rules,
                strategy,
                requested=args.engine,
                needs_per_round=bool(args.vis),
                needs_cv=bool(args.cv),
                shuffle_type=args.shuffle_type,
            )
        except RuntimeError as e:
            print(f"Error: {e}")
            return
        if engine_choice.use_core:
            print("Engine: Rust fast core (cardsharp-core)")
        else:
            print(f"Engine: Python reference ({engine_choice.reason})")

        if engine_choice.use_core:
            fast_stats = run_fast_batch(
                rules,
                strategy,
                args.num_games,
                master_seed,
                n_players=args.num_players,
                initial_bankroll=args.bankroll,
            )
            agg_stats.merge(fast_stats)
            running_net_earnings = fast_stats.net_sum
            total_bets = fast_stats.total_bet_sum
        elif args.single_cpu:
            # Initialize shoe once for single CPU mode
            shoe = Shoe(
                num_decks=rules.num_decks,
                penetration=rules.penetration,
                use_csm=rules.is_using_csm(),
                burn_cards=rules.burn_cards,
                deck_factory=rules.variant.create_deck if rules.variant else None,
                shuffle_type=args.shuffle_type,
                shuffle_count=args.shuffle_count,
            )
            for i in range(args.num_games):
                earnings, bets, _, result, current_shoe = play_game(
                    rules,
                    DummyIOInterface(),
                    player_names,
                    strategy,
                    shoe,
                    args.bankroll,
                    ev_table=deal_ev_table,
                )
                shoe = current_shoe  # Update shoe state for next game
                agg_stats.merge(SimulationStats.from_dict(result))
                running_net_earnings += earnings
                total_bets += bets
                if graph:
                    graph.update(i + 1, running_net_earnings)
        else:
            # For parallel processing, we still need separate shoes per process
            cpu_count = multiprocessing.cpu_count()
            games_per_cpu, remainder = divmod(args.num_games, cpu_count)
            game_batches = [
                games_per_cpu + (1 if i < remainder else 0) for i in range(cpu_count)
            ]
            # Derive deterministic, independent worker seeds from the master.
            worker_seeds = [random.randint(0, 2**63 - 1) for _ in range(cpu_count)]

            with multiprocessing.Pool() as pool:
                batch_args = [
                    (
                        rules,
                        DummyIOInterface(),
                        player_names,
                        game_count,
                        strategy,
                        args.bankroll,
                        args.shuffle_type,
                        args.shuffle_count,
                        worker_seeds[i],
                        deal_ev_table,
                    )
                    for i, game_count in enumerate(game_batches)
                ]
                batch_results = pool.starmap(play_game_batch, batch_args)
                game_number = 0
                for batch_dict, batch_earnings, batch_bets in batch_results:
                    agg_stats.merge(SimulationStats.from_dict(batch_dict))
                    total_bets += batch_bets
                    for earnings in batch_earnings:
                        game_number += 1
                        running_net_earnings += earnings
                        if graph:
                            graph.update(game_number, running_net_earnings)

        end_time = time.time()
        duration = end_time - start_time
        games_per_second = args.num_games / duration if duration > 0 else 0

        games_played_excluding_pushes = agg_stats.games_played - agg_stats.draws
        net_earnings = agg_stats.net_sum

        print("Simulation completed.")
        print(f"Games played (excluding pushes): {games_played_excluding_pushes:,}")
        print(f"Player wins: {agg_stats.player_wins:,}")
        print(f"Dealer wins: {agg_stats.dealer_wins:,}")
        print(f"Draws: {agg_stats.draws:,}")
        print(f"Net Earnings: ${net_earnings:,.2f}")
        print(f"Total Bets: ${total_bets:,.2f}")

        # House edge per initial bet, with delta-method CI. This matches
        # the convention used in published house-edge tables.
        he_result = agg_stats.house_edge_with_ci(confidence=args.confidence)
        ci_pct = int(round(args.confidence * 100))
        if he_result is not None:
            he, lo, hi, half = he_result
            print(
                f"House Edge: {he * 100:.4f}% +/- {half * 100:.4f}% "
                f"({ci_pct}% CI: [{lo * 100:.4f}%, {hi * 100:.4f}%], "
                f"n={agg_stats.n_rounds:,})"
            )

        # If control variate is enabled, report the CV-adjusted estimate.
        if args.cv:
            cv = agg_stats.control_variate_he_with_ci(confidence=args.confidence)
            if cv is not None:
                print(
                    f"House Edge (CV): {cv['he'] * 100:.4f}% +/- "
                    f"{cv['half'] * 100:.4f}% "
                    f"({ci_pct}% CI: [{cv['lo'] * 100:.4f}%, "
                    f"{cv['hi'] * 100:.4f}%], n={cv['n']:,})"
                )
                print(
                    f"  Variance reduction: {cv['reduction_pct']:.1f}% "
                    f"(beta={cv['beta']:.3f}, "
                    f"baseline half-width {cv['baseline_half'] * 100:.4f}%)"
                )
        # Edge over total action (legacy metric: includes doubles/splits
        # in the denominator). Kept for backwards compatibility.
        if total_bets > 0:
            edge_total_action = (-net_earnings / total_bets) * 100
            print(f"Edge vs total action: {edge_total_action:.4f}%")

        wr_result = agg_stats.win_rate_with_ci(confidence=args.confidence)
        if wr_result is not None:
            p, lo, hi, half = wr_result
            print(
                f"Player win rate: {p * 100:.2f}% +/- {half * 100:.2f}% "
                f"({ci_pct}% Wilson CI: [{lo * 100:.2f}%, {hi * 100:.2f}%])"
            )
            dealer_n = agg_stats.player_wins + agg_stats.dealer_wins
            if dealer_n > 0:
                dealer_p = agg_stats.dealer_wins / dealer_n * 100
                print(f"Dealer win rate: {dealer_p:.2f}%")

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
