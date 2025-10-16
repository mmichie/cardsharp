"""
Optimized strategy lookups using integer-indexed arrays.

This module provides a fast version of BasicStrategy that uses
pre-built integer-indexed arrays instead of nested dict lookups
with string keys. This eliminates string operations and dict overhead.

Performance improvement: ~2-3x faster strategy lookups.
"""

import csv
import os
from typing import Optional

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.strategy import Strategy
from cardsharp.common.card import Card, Rank
from cardsharp.blackjack.constants import get_blackjack_value
from cardsharp.blackjack.decision_logger import decision_logger


class FastBasicStrategy(Strategy):
    """
    Optimized BasicStrategy using integer-indexed arrays.

    Instead of:
        strategy[hand_type][dealer_card]  # Dict lookups, string keys

    Uses:
        hard_table[hand_value][dealer_index]  # Direct array indexing

    This eliminates:
    - String concatenation for hand types
    - Dict lookups for strategy table
    - Dict lookup for dealer_indexes
    - Dict lookup for action symbol mapping
    """

    # Action enum values stored directly in arrays
    HIT = Action.HIT
    STAND = Action.STAND
    DOUBLE = Action.DOUBLE
    SPLIT = Action.SPLIT
    SURRENDER = Action.SURRENDER

    def __init__(self, strategy_file=None):
        """
        Initialize fast strategy with pre-built lookup arrays.

        Args:
            strategy_file: Path to basic_strategy.csv (optional)
        """
        if strategy_file is None:
            strategy_file = os.path.join(
                os.path.dirname(__file__), "basic_strategy.csv"
            )

        # Build three separate lookup tables
        self._build_strategy_tables(strategy_file)

    def _build_strategy_tables(self, strategy_file):
        """
        Build optimized lookup tables from CSV file.

        Creates three 2D arrays:
        - hard_table[0-17][0-9]: Hard 4-21 vs dealer 2-A
        - soft_table[0-8][0-9]: Soft 13-21 vs dealer 2-A
        - pair_table[0-10][0-9]: Pair 2-A vs dealer 2-A
        """
        # Initialize arrays with default action (HIT)
        self.hard_table = [[self.HIT for _ in range(10)] for _ in range(18)]
        self.soft_table = [[self.HIT for _ in range(10)] for _ in range(9)]
        self.pair_table = [[self.HIT for _ in range(10)] for _ in range(11)]

        # Action symbol to enum mapping
        action_map = {
            "H": self.HIT,
            "S": self.STAND,
            "D": self.DOUBLE,
            "DS": self.DOUBLE,  # Double or Stand
            "P": self.SPLIT,
            "R": self.SURRENDER,
        }

        # Load and parse CSV
        with open(strategy_file, "r") as f:
            reader = csv.reader(f)
            next(reader)  # Skip header

            for row in reader:
                hand_type = row[0]
                actions = [action_map.get(a.strip(), self.HIT) for a in row[1:]]

                # Determine which table and index
                if hand_type.startswith("Hard"):
                    value = int(hand_type[4:])  # Extract number from "Hard16"
                    if 4 <= value <= 21:
                        self.hard_table[value - 4] = actions

                elif hand_type.startswith("Soft"):
                    value = int(hand_type[4:])  # Extract number from "Soft18"
                    if 13 <= value <= 21:
                        self.soft_table[value - 13] = actions

                elif hand_type.startswith("Pair"):
                    pair_card = hand_type[4:]  # Extract "2", "10", "A"
                    if pair_card == "A":
                        pair_index = 10  # Ace pairs at index 10
                    elif pair_card == "10":
                        pair_index = 9  # 10/J/Q/K pairs at index 9
                    else:
                        pair_index = int(pair_card) - 1  # Pair2 at index 1, etc.
                    self.pair_table[pair_index] = actions

    def _get_dealer_index(self, dealer_up_card: Card) -> int:
        """
        Convert dealer up card to array index.

        Returns:
            0-7: Cards 2-9
            8: Cards 10/J/Q/K
            9: Ace
        """
        rank = dealer_up_card.rank
        if rank == Rank.ACE:
            return 9
        value = get_blackjack_value(rank)
        if value >= 10:
            return 8
        return value - 2  # Cards 2-9 map to indices 0-7

    def decide_action(self, player, dealer_up_card: Card, game=None) -> Action:
        """
        Optimized action decision using direct array indexing.

        Args:
            player: Current player
            dealer_up_card: Dealer's up card
            game: Game instance (optional)

        Returns:
            Action enum value
        """
        hand = player.current_hand
        dealer_index = self._get_dealer_index(dealer_up_card)

        # Determine hand type and lookup action
        if hand.can_split:
            # Pairs
            rank = hand.cards[0].rank
            if rank == Rank.ACE:
                pair_index = 10
            elif get_blackjack_value(rank) == 10:
                pair_index = 9
            else:
                pair_index = get_blackjack_value(rank) - 1

            action = self.pair_table[pair_index][dealer_index]

        elif hand.is_soft:
            # Soft hands
            value = hand.value()
            if 13 <= value <= 21:
                action = self.soft_table[value - 13][dealer_index]
            else:
                action = self.HIT  # Fallback

        else:
            # Hard hands
            value = hand.value()
            if 4 <= value <= 21:
                action = self.hard_table[value - 4][dealer_index]
            else:
                action = self.HIT  # Fallback

        # Validate action against available actions
        final_action = self._get_valid_action(player, action, "")

        # Log decision (for debugging/analysis)
        if decision_logger.logger.isEnabledFor(10):  # DEBUG level
            hand_desc = f"{'Pair' if hand.can_split else 'Soft' if hand.is_soft else 'Hard'}{hand.value()}"
            decision_logger.log_strategy_lookup(hand_desc, str(dealer_index), str(final_action))

        return final_action

    def _get_valid_action(self, player, action: Action, action_symbol: str) -> Action:
        """
        Ensure the chosen action is valid for current game state.

        If action is not available (e.g., can't double after 3 cards),
        fall back to appropriate alternative.

        Args:
            player: Current player
            action: Desired action
            action_symbol: Original action symbol (unused in fast version)

        Returns:
            Valid action for current state
        """
        valid_actions = player.valid_actions

        if action in valid_actions:
            return action

        # Fallback logic
        if action == self.DOUBLE:
            return self.HIT if self.HIT in valid_actions else self.STAND
        elif action == self.SURRENDER:
            return self.HIT if self.HIT in valid_actions else self.STAND
        elif action == self.SPLIT:
            return self.HIT if self.HIT in valid_actions else self.STAND
        else:
            # Last resort
            if self.STAND in valid_actions:
                return self.STAND
            return self.HIT

    def decide_insurance(self, player) -> bool:
        """Decide whether to buy insurance. Returns False (basic strategy never takes insurance)."""
        return False

    def get_bet_amount(self, min_bet: float, max_bet: float, player_money: float) -> float:
        """Return minimum bet (flat betting)."""
        return min_bet
