"""
Blackjack-specific extensions of the cardsharp library.

This module extends the cardsharp library to provide classes and methods
specifically designed to facilitate the game of Blackjack. It provides a class
`BlackjackHand` that extends the `Hand` class from cardsharp and adds additional
features pertinent to Blackjack.

Classes:
    BlackjackHand: Represents a player's hand in a game of Blackjack.

The BlackjackHand class has the following public methods:
    - value: Calculates and returns the value of the hand, accounting for the
      flexible value of Aces in Blackjack.
    - is_soft: Checks if the hand is soft (contains an Ace that can be valued at 11
      without busting).
    - is_blackjack: Checks if the hand is a Blackjack (two cards adding up to 21).
    - can_double: Checks if the hand can be doubled down (contains exactly two cards).
    - can_split: Checks if the hand can be split (contains two cards of the same rank).

The BlackjackHand class also has the following property accessors:
    - is_soft
    - is_blackjack
    - can_double
    - can_split

Dependencies:
    cardsharp.common.hand: Hand class
    cardsharp.common.card: Card and Rank classes
"""

from cardsharp.common.card import Rank
from cardsharp.common.hand import Hand


class BlackjackHand(Hand):
    """
    A class representing a hand in the game of Blackjack. This class extends
    the Hand class from cardsharp and provides additional functionality
    specific to the rules of Blackjack.
    """

    __slots__ = ("_cards", "_cached_value", "_is_split")

    def __init__(self, *args, is_split: bool = False, **kwargs):
        """
        Initialize a BlackjackHand.

        Args:
            is_split (bool): Whether this hand was created from splitting another hand.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self._cached_value = None  # Cache for hand value
        self._is_split = is_split  # Track if this hand was created from a split

    @property
    def is_split(self) -> bool:
        """Whether this hand was created from a split."""
        return self._is_split

    def _invalidate_cache(self):
        """Invalidate the cache when the hand changes."""
        self._cached_value = None

    def add_card(self, card):
        """Override to invalidate cache when a new card is added."""
        super().add_card(card)
        self._invalidate_cache()

    def remove_card(self, card):
        """Override to invalidate cache when a card is removed."""
        super().remove_card(card)
        self._invalidate_cache()

    @property
    def _num_aces(self) -> int:
        """Number of aces in the hand."""
        return sum(card.rank == Rank.ACE for card in self.cards)

    @property
    def _non_ace_value(self) -> int:
        """Sum of values of non-ace cards in the hand."""
        return sum(card.rank.rank_value for card in self.cards if card.rank != Rank.ACE)

    def value(self) -> int:
        """
        Calculate the value of the hand following Blackjack rules,
        i.e., considering the value of Ace as 1 or 11 as necessary.
        """
        if self._cached_value is not None:
            return self._cached_value

        num_aces = self._num_aces
        non_ace_value = self._non_ace_value

        # Calculate value considering the flexible value of Aces
        value = non_ace_value + num_aces  # Count all aces as 1 initially
        if num_aces > 0 and non_ace_value + 10 <= 21:
            value += 10  # Count one ace as 11 if it doesn't bust the hand

        self._cached_value = value
        return value

    @property
    def is_soft(self) -> bool:
        """
        Check if the hand is soft, meaning it contains an Ace
        that can be counted as 11 without causing the hand's total value to exceed 21.
        """
        return self._num_aces > 0 and self._non_ace_value + 10 < 21

    @property
    def is_blackjack(self) -> bool:
        """
        Check if the hand is a blackjack, meaning it contains only two cards
        and their combined value is exactly 21.
        Note: Split hands can't be blackjack, even if they total 21 with two cards.
        """
        return len(self.cards) == 2 and self.value() == 21 and not self._is_split

    @property
    def can_double(self) -> bool:
        """
        Check if the hand can be doubled down, meaning it contains exactly two cards.
        Note that this method does not consider whether the player has enough money to double down.
        """
        return len(self.cards) == 2

    @property
    def can_split(self) -> bool:
        """
        Check if the hand can be split, meaning it contains exactly two cards of the same rank.
        Note that this method does not consider whether the player has enough money to split.
        """
        return len(self.cards) == 2 and self.cards[0].rank == self.cards[1].rank
