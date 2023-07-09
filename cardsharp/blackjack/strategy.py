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
            player.current_hand.value() == 17 and player.current_hand.is_soft()
        ):
            return Action.HIT
        else:
            return Action.STAND


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
        if current_hand.is_blackjack():
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
        if current_hand.can_split():
            player_rank = current_hand.cards[0].rank
            dealer_rank = dealer_up_card.rank
            if player_rank in [Rank.ACE, Rank.EIGHT]:
                return Action.SPLIT
            elif (
                player_rank in [Rank.TWO, Rank.THREE, Rank.SEVEN]
                and dealer_rank.rank_value <= 7
            ):
                return Action.SPLIT
            elif player_rank == Rank.SIX and dealer_rank.rank_value <= 6:
                return Action.SPLIT
            elif player_rank in [Rank.FOUR] and dealer_rank.rank_value == 5:
                return Action.SPLIT
            elif player_rank in [Rank.NINE] and dealer_rank.rank_value not in [
                7,
                10,
                11,
            ]:
                return Action.SPLIT
        return None

    def _decide_on_double(self, current_hand, dealer_up_card: Card) -> Optional[Action]:
        """
        Decides whether to double based on the hand and the dealer's up card.

        Args:
            current_hand: The current hand of the player.
            dealer_up_card (Card): The dealer's up card.

        Returns:
            Action: Action.DOUBLE if the player decides to double, None otherwise.
        """
        if current_hand.can_double():
            if (
                current_hand.value() in [10, 11] and dealer_up_card.rank.rank_value < 10
            ) or (
                current_hand.is_soft()
                and current_hand.value() in [13, 14, 15, 16, 17]
                and dealer_up_card.rank.rank_value < 7
            ):
                return Action.DOUBLE
        return None

    def _decide_on_stand_or_hit(self, current_hand, dealer_up_card: Card) -> Action:
        """
        Decides whether to stand or hit based on the hand and the dealer's up card.

        Args:
            current_hand: The current hand of the player.
            dealer_up_card (Card): The dealer's up card.

        Returns:
            Action: Action.STAND or Action.HIT based on the player's hand and dealer's up card.
        """
        if current_hand.value() <= 11:
            return Action.HIT
        elif current_hand.value() == 12:
            if dealer_up_card.rank.rank_value < 4 or dealer_up_card.rank.rank_value > 6:
                return Action.HIT
            else:
                return Action.STAND
        elif current_hand.value() in range(13, 17):
            if dealer_up_card.rank.rank_value > 6:
                return Action.HIT
            else:
                return Action.STAND
        else:
            return Action.STAND


class CountingStrategy(Strategy):
    def decide_action(self, player, dealer_up_card):
        # Fill in with Counting Strategy logic
        pass
