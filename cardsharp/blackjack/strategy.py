import csv
import os

from abc import ABC, abstractmethod
from typing import Optional

from cardsharp.blackjack.action import Action
from cardsharp.common.card import Card, Rank


class Strategy(ABC):
    @abstractmethod
    def decide_action(self, player, dealer_up_card=None) -> Action:
        pass


class DealerStrategy(Strategy):
    def decide_action(self, player, dealer_up_card=None) -> Action:
        if player.is_busted():
            return Action.STAND
        if player.current_hand.value() < 17 or (
            player.current_hand.value() == 17 and player.current_hand.is_soft
        ):
            return Action.HIT
        else:
            return Action.STAND


class BasicStrategyLoader(Strategy):
    def __init__(self, strategy_file=None):
        if strategy_file is None:
            strategy_file = os.path.join(
                os.path.dirname(__file__), "files/basic_strategy.csv"
            )

        self.strategy = self._load_strategy(strategy_file)
        self.dealer_indexes = {
            "TWO": 0,
            "THREE": 1,
            "FOUR": 2,
            "FIVE": 3,
            "SIX": 4,
            "SEVEN": 5,
            "EIGHT": 6,
            "NINE": 7,
            "TEN": 8,
            "JACK": 9,
            "QUEEN": 10,
            "KING": 11,
            "ACE": 12,
        }

    def _load_strategy(self, strategy_file):
        strategy = []
        with open(strategy_file) as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                strategy.append(row)
        return strategy

    def decide_action(self, player, dealer_up_card: Card) -> Action:
        """
        Decides the action to take based on the player's hand and the dealer's up card.

        Args:
            player: The player instance.
            dealer_up_card (Card): The dealer's up card.

        Returns:
            Action: The action to take.
        """
        current_hand = player.current_hand
        if current_hand.is_blackjack:
            return Action.STAND

        action = self._decide_on_surrender(current_hand, dealer_up_card)
        if action is not None:
            return action

        action = self._decide_on_split(current_hand, dealer_up_card)
        if action is not None:
            return action

        action = self._decide_on_double(current_hand, dealer_up_card)
        if action is not None:
            return action

        return self._decide_on_stand_or_hit(current_hand, dealer_up_card)


class BasicStrategy(Strategy):
    """
    Basic blackjack strategy class that decides actions based on hand state and dealer's up card.
    """

    def decide_action(self, player, dealer_up_card: Card) -> Action:
        """
        Decides the action to take based on the player's hand and the dealer's up card.

        Args:
            player: The player instance.
            dealer_up_card (Card): The dealer's up card.

        Returns:
            Action: The action to take.
        """
        current_hand = player.current_hand
        if current_hand.is_blackjack:
            return Action.STAND

        action = self._decide_on_split(current_hand, dealer_up_card)
        if action is not None:
            return action

        action = self._decide_on_double(current_hand, dealer_up_card)
        if action is not None:
            return action

        return self._decide_on_stand_or_hit(current_hand, dealer_up_card)

    def _decide_on_split(self, current_hand, dealer_up_card: Card) -> Optional[Action]:
        """
        Decides whether to split based on the hand and the dealer's up card.

        Args:
            current_hand: The current hand of the player.
            dealer_up_card (Card): The dealer's up card.

        Returns:
            Action: Action.SPLIT if the player decides to split, None otherwise.
        """
        if not current_hand.can_split:
            return None

        player_rank = current_hand.cards[0].rank
        dealer_rank = dealer_up_card.rank

        split_conditions = {
            Rank.ACE: True,
            Rank.EIGHT: True,
            Rank.TWO: dealer_rank.rank_value <= 7,
            Rank.THREE: dealer_rank.rank_value <= 7,
            Rank.SIX: dealer_rank.rank_value <= 6,
            Rank.SEVEN: dealer_rank.rank_value <= 7,
            Rank.NINE: dealer_rank.rank_value not in [7, 10, 11]
            or current_hand.is_soft,
            Rank.FOUR: dealer_rank.rank_value in [5, 6],
        }

        return Action.SPLIT if split_conditions.get(player_rank, False) else None

    def _decide_on_double(self, current_hand, dealer_up_card: Card) -> Optional[Action]:
        """
        Decides whether to double based on the hand and the dealer's up card.

        Args:
            current_hand: The current hand of the player.
            dealer_up_card (Card): The dealer's up card.

        Returns:
            Action: Action.DOUBLE if the player decides to double, None otherwise.
        """
        if not current_hand.can_double:
            return None

        hand_value = current_hand.value()
        dealer_rank = dealer_up_card.rank.rank_value

        # Enhanced double down conditions based on common blackjack strategies
        double_conditions = [
            hand_value == 11,
            hand_value == 10 and dealer_rank < 10,
            hand_value == 9 and dealer_rank in [3, 4, 5, 6],
            current_hand.is_soft
            and (
                (hand_value in [13, 14] and dealer_rank in [5, 6])
                or (hand_value in [15, 16] and dealer_rank in [4, 5, 6])
                or (hand_value == 17 and dealer_rank in [3, 4, 5, 6])
                or (hand_value == 18 and dealer_rank in [3, 4, 5, 6])
            ),
        ]

        return Action.DOUBLE if any(double_conditions) else None

    def _decide_on_stand_or_hit(self, current_hand, dealer_up_card: Card) -> Action:
        """
        Decides whether to stand or hit based on the hand and the dealer's up card.

        Args:
            current_hand: The current hand of the player.
            dealer_up_card (Card): The dealer's up card.

        Returns:
            Action: Action.STAND or Action.HIT based on the player's hand and dealer's up card.
        """
        hand_value = current_hand.value()
        dealer_rank = dealer_up_card.rank.rank_value

        if current_hand.is_soft:
            if hand_value <= 17:
                return Action.HIT
            elif hand_value == 18 and dealer_rank >= 9:
                return Action.HIT
            else:
                return Action.STAND
        else:
            if hand_value <= 11:
                return Action.HIT
            elif hand_value == 12 and dealer_rank not in [4, 5, 6]:
                return Action.HIT
            elif 13 <= hand_value <= 16 and dealer_rank > 6:
                return Action.HIT
            else:
                return Action.STAND

    def _decide_on_surrender(
        self, current_hand, dealer_up_card: Card
    ) -> Optional[Action]:
        """
        Decides whether to surrender based on the hand and the dealer's up card.

        Args:
            current_hand: The current hand of the player.
            dealer_up_card (Card): The dealer's up card.

        Returns:
            Action: Action.SURRENDER if the player decides to surrender, None otherwise.
        """
        if len(current_hand.cards) != 2:
            return None

        hand_value = current_hand.value()
        dealer_rank = dealer_up_card.rank.rank_value

        surrender_conditions = [
            hand_value == 16 and dealer_rank in [9, 10, 11],
            hand_value == 15 and dealer_rank == 10,
        ]

        return Action.SURRENDER if any(surrender_conditions) else None


class CountingStrategy(BasicStrategy):
    def __init__(self):
        super().__init__()
        self.count = 0

    def update_count(self, card: Card):
        if card.rank in [Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX]:
            self.count += 1
        elif card.rank in [Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING, Rank.ACE]:
            self.count -= 1

    def decide_action(self, player, dealer_up_card: Card) -> Action:
        # Update count based on the visible cards (player's cards and dealer's up card)
        for card in player.current_hand.cards + [dealer_up_card]:
            self.update_count(card)

        if self.count > 2:  # Adjust this threshold as needed
            return self.aggressive_strategy(player, dealer_up_card)
        else:
            return super().decide_action(player, dealer_up_card)

    def aggressive_strategy(self, player, dealer_up_card: Card) -> Action:
        # More aggressive play decisions when the count is high
        if (
            self.count >= 4
        ):  # Strongly positive count indicates more high cards are present
            if player.current_hand.can_double and player.current_hand.value() in [
                9,
                10,
                11,
            ]:
                return Action.DOUBLE
            elif player.current_hand.value() <= 16:
                return Action.HIT
        return super().decide_action(
            player, dealer_up_card
        )  # Default to basic strategy otherwise
