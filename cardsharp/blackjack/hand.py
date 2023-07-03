"""
This module provides the BlackjackHand class that extends the Hand class from cardsharp.
The BlackjackHand class contains methods to calculate the value of a hand, determine if it's
soft, check if it's a blackjack, and determine if it can be doubled down or split.
"""

from cardsharp.common.hand import Hand
from cardsharp.common.card import Rank


class BlackjackHand(Hand):
    """
    A class representing a hand in the game of Blackjack. This class extends
    the Hand class from cardsharp and provides additional functionality
    specific to the rules of Blackjack.
    """

    def value(self) -> int:
        """
        Calculates and returns the value of the hand following Blackjack rules,
        i.e., considering the value of Ace as 1 or 11 as necessary.
        """
        total_value = sum(
            card.rank.rank_value for card in self.cards if card.rank != Rank.ACE
        )
        num_aces = sum(card.rank == Rank.ACE for card in self.cards)

        for _ in range(num_aces):
            if total_value + Rank.ACE.rank_value <= 21:
                total_value += Rank.ACE.rank_value
            else:
                total_value += Rank.ACE.rank_value - 10

        return total_value

    def is_soft(self) -> bool:
        """
        Returns True if the hand is soft, which means it contains an Ace
        that can be counted as 11 without causing the hand's total value to exceed 21.
        """
        values_without_ace = [
            10
            if card.rank in [Rank.JACK, Rank.QUEEN, Rank.KING]
            else card.rank.rank_value
            for card in self.cards
            if card.rank != Rank.ACE
        ]
        return (
            Rank.ACE in (card.rank for card in self.cards)
            and sum(values_without_ace) + 11 <= 21
        )

    def is_blackjack(self) -> bool:
        """
        Returns True if the hand is a blackjack, which means it contains only two cards
        and their combined value is exactly 21.
        """
        return len(self.cards) == 2 and self.value() == 21

    def can_double(self) -> bool:
        """
        Returns True if the hand can be doubled down, which means it contains exactly two cards.
        Note that this method does not consider whether the player has enough money to double down.
        """
        return len(self.cards) == 2

    def can_split(self) -> bool:
        """
        Returns True if the hand can be split, which means it contains exactly two cards of the same rank.
        Note that this method does not consider whether the player has enough money to split.
        """
        return len(self.cards) == 2 and self.cards[0].rank == self.cards[1].rank
