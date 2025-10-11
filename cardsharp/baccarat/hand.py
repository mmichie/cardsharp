"""
Baccarat hand implementation.

In Baccarat, hand values are calculated differently than blackjack:
- Cards 2-9 are worth face value
- 10, J, Q, K are worth 0
- Aces are worth 1
- Only the rightmost digit of the sum counts (17 = 7, 23 = 3)
"""

from typing import List
from cardsharp.common.card import Card, Rank


class BaccaratHand:
    """Represents a hand in Baccarat."""

    def __init__(self):
        """Initialize an empty Baccarat hand."""
        self.cards: List[Card] = []

    def add_card(self, card: Card) -> None:
        """
        Add a card to the hand.

        Args:
            card: Card to add
        """
        self.cards.append(card)

    def value(self) -> int:
        """
        Calculate the value of the hand.

        In Baccarat, only the rightmost digit counts.
        For example: 15 = 5, 20 = 0, 17 = 7

        Returns:
            Hand value (0-9)
        """
        total = 0
        for card in self.cards:
            if card.rank in [Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX,
                            Rank.SEVEN, Rank.EIGHT, Rank.NINE]:
                # Face value for 2-9
                rank_values = {
                    Rank.TWO: 2, Rank.THREE: 3, Rank.FOUR: 4, Rank.FIVE: 5,
                    Rank.SIX: 6, Rank.SEVEN: 7, Rank.EIGHT: 8, Rank.NINE: 9
                }
                total += rank_values[card.rank]
            elif card.rank == Rank.ACE:
                total += 1
            # 10, J, Q, K are worth 0, so we don't add anything

        # Return only the rightmost digit (modulo 10)
        return total % 10

    def is_natural(self) -> bool:
        """
        Check if this is a natural hand (8 or 9 on first two cards).

        Returns:
            True if natural, False otherwise
        """
        return len(self.cards) == 2 and self.value() in [8, 9]

    def card_count(self) -> int:
        """
        Get the number of cards in the hand.

        Returns:
            Number of cards
        """
        return len(self.cards)

    def third_card_value(self) -> int:
        """
        Get the value of the third card (used for Banker drawing rules).

        Returns:
            Value of third card, or -1 if no third card
        """
        if len(self.cards) >= 3:
            card = self.cards[2]
            if card.rank in [Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX,
                            Rank.SEVEN, Rank.EIGHT, Rank.NINE]:
                rank_values = {
                    Rank.TWO: 2, Rank.THREE: 3, Rank.FOUR: 4, Rank.FIVE: 5,
                    Rank.SIX: 6, Rank.SEVEN: 7, Rank.EIGHT: 8, Rank.NINE: 9
                }
                return rank_values[card.rank]
            elif card.rank == Rank.ACE:
                return 1
            else:
                return 0
        return -1

    def __str__(self) -> str:
        """String representation of the hand."""
        cards_str = ", ".join(str(card) for card in self.cards)
        return f"[{cards_str}] = {self.value()}"

    def __repr__(self) -> str:
        """Detailed representation of the hand."""
        return f"BaccaratHand(cards={self.cards}, value={self.value()})"
