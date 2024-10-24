"""
Blackjack-specific extensions of the cardsharp library.

This module extends the cardsharp library to provide classes and methods
specifically designed to facilitate the game of Blackjack. It provides a class
`BlackjackHand` that extends the `Hand` class from cardsharp and adds additional
features pertinent to Blackjack.
"""

from cardsharp.common.card import Rank
from cardsharp.common.hand import Hand


class BlackjackHand(Hand):
    """A hand in the game of Blackjack."""

    __slots__ = ("_cards", "_cached_value", "_is_split")

    def __init__(self, *args, is_split: bool = False, **kwargs):
        """Initialize a BlackjackHand."""
        super().__init__(*args, **kwargs)
        self._cached_value = None
        self._is_split = is_split

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
        considering Aces as 1 or 11 as necessary.
        """
        if self._cached_value is not None:
            return self._cached_value

        num_aces = self._num_aces
        non_ace_value = self._non_ace_value

        # Start with all aces counting as 1
        value = non_ace_value + num_aces

        # Try to use aces as 11 when beneficial
        for _ in range(num_aces):
            if value <= 11:
                value += 10  # Convert one ace from 1 to 11

        self._cached_value = value
        return value

    @property
    def is_soft(self) -> bool:
        """
        Check if the hand is soft (contains an Ace counted as 11).
        """
        if not self._num_aces:
            return False

        # Calculate value without any aces as 11
        min_value = self._non_ace_value + self._num_aces
        # Calculate actual value
        actual_value = self.value()
        # If actual value is higher than min_value, at least one ace is being used as 11
        return actual_value > min_value and actual_value <= 21

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
