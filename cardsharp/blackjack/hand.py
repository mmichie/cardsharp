"""
Optimized BlackjackHand implementation with improved cache handling.
"""

from typing import Any, Dict
from cardsharp.common.card import Card, Rank
from cardsharp.common.hand import Hand


class BlackjackHand(Hand):
    """A hand in the game of Blackjack with optimized caching."""

    __slots__ = ("_cards", "_cache", "_is_split")

    def __init__(self, *args, is_split: bool = False, **kwargs):
        """Initialize a BlackjackHand with an optimized cache system."""
        super().__init__(*args, **kwargs)
        self._is_split = is_split
        # Cache structure holds multiple computed properties
        self._cache: Dict[str, Any] = {
            "value": None,
            "non_ace_value": None,
            "num_aces": None,
            "is_soft": None,
            "is_blackjack": None,
            "last_card_count": 0,
        }

    def _invalidate_cache(self) -> None:
        """Invalidate only necessary cache entries."""
        self._cache.update(
            {
                "value": None,
                "is_soft": None,
                "is_blackjack": None,
                "last_card_count": len(self._cards),
            }
        )
        # Don't invalidate 'num_aces' and 'non_ace_value' unless necessary

    def add_card(self, card: Card) -> None:
        """Add a card to the hand with selective cache invalidation."""
        super().add_card(card)

        # Update cached values for 'num_aces' and 'non_ace_value'
        if self._cache["num_aces"] is not None:
            if card.rank == Rank.ACE:
                self._cache["num_aces"] += 1
            else:
                if self._cache["non_ace_value"] is not None:
                    self._cache["non_ace_value"] += card.rank.rank_value

        # Invalidate computed values that depend on the entire hand
        self._invalidate_cache()

    def remove_card(self, card: Card) -> None:
        """Remove a card from the hand with full cache invalidation."""
        super().remove_card(card)
        # Full cache invalidation on removal as it's less common
        self._cache = {key: None for key in self._cache}
        self._cache["last_card_count"] = len(self._cards)

    @property
    def _num_aces(self) -> int:
        """Calculate and cache the number of aces in the hand."""
        if self._cache["num_aces"] is None:
            # Faster implementation with direct attribute access and manual loop
            count = 0
            for card in self._cards:
                if card.rank == Rank.ACE:
                    count += 1
            self._cache["num_aces"] = count
        return self._cache["num_aces"]

    @property
    def _non_ace_value(self) -> int:
        """Calculate and cache the sum of non-ace card values."""
        if self._cache["non_ace_value"] is None:
            # Faster implementation with direct calculation and manual loop
            total = 0
            for card in self._cards:
                if card.rank != Rank.ACE:
                    total += card.rank.rank_value
            self._cache["non_ace_value"] = total
        return self._cache["non_ace_value"]

    def value(self) -> int:
        """Calculate the optimal value of the hand with ace handling."""
        if self._cache["value"] is not None:
            return self._cache["value"]

        num_aces = self._num_aces
        non_ace_value = self._non_ace_value

        # Start with minimum value (all aces counted as 1)
        value = non_ace_value + num_aces

        # Try to use aces as 11 when beneficial - use original algorithm
        # to match test expectations
        for _ in range(num_aces):
            if value + 10 <= 21:
                value += 10
            else:
                break

        self._cache["value"] = value
        return value

    @property
    def is_soft(self) -> bool:
        """Determine if the hand is soft (contains an ace counted as 11)."""
        if self._cache["is_soft"] is not None:
            return self._cache["is_soft"]

        if self._num_aces == 0:
            self._cache["is_soft"] = False
            return False

        min_value = self._non_ace_value + self._num_aces
        actual_value = self.value()
        self._cache["is_soft"] = actual_value > min_value and actual_value <= 21
        return self._cache["is_soft"]

    @property
    def is_blackjack(self) -> bool:
        """Determine if the hand is a natural blackjack."""
        if self._cache["is_blackjack"] is not None:
            return self._cache["is_blackjack"]

        if len(self._cards) != 2 or self._is_split:
            self._cache["is_blackjack"] = False
            return False

        ranks = {card.rank for card in self._cards}
        has_ace = Rank.ACE in ranks
        has_ten_value = any(rank.rank_value == 10 for rank in ranks)

        self._cache["is_blackjack"] = has_ace and has_ten_value
        return self._cache["is_blackjack"]

    @property
    def can_split(self) -> bool:
        """Check if the hand can be split."""
        return len(self._cards) == 2 and self._cards[0].rank == self._cards[1].rank

    @property
    def can_double(self) -> bool:
        """Check if the hand can be doubled down."""
        return len(self._cards) == 2

    @property
    def is_split(self) -> bool:
        """Return whether this hand was created from a split."""
        return self._is_split
