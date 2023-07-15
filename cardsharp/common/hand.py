"""
This module contains classes to represent a hand of cards in a card game.

It includes an abstract base class `AbstractHand`, and a concrete implementation `Hand`.
Each hand can have multiple cards, and provides methods for adding and removing cards.

Classes:

AbstractHand: An abstract base class for a hand of cards.
Hand: A concrete implementation of a hand of cards.
"""
from abc import ABC
from typing import List

from cardsharp.common.card import Card


class AbstractHand(ABC):
    """
    An abstract base class for a hand of cards.

    This class provides a basic structure for a hand of cards, including methods to add and remove cards.
    Subclasses should override the __repr__ and __str__ methods to provide a string representation of the hand.
    """

    def __init__(self):
        self._cards = []

    @property
    def cards(self) -> List[Card]:
        """Returns the cards in the hand."""
        return self._cards

    def add_card(self, card: Card) -> None:
        """
        Adds a card to the hand.

        Args:
            card: The card to add.
        """
        self._cards.append(card)

    def remove_card(self, card: Card) -> None:
        """
        Removes a card from the hand.

        Args:
            card: The card to remove.

        Raises:
            ValueError: If the card is not found in the hand.
        """
        try:
            self._cards.remove(card)
        except ValueError as exc:
            raise ValueError(f"Card {card} not found in hand.") from exc


class Hand(AbstractHand):
    """
    A concrete implementation of a hand of cards.

    This class provides a string representation of a hand of cards for both debugging and display purposes.
    """

    def __repr__(self) -> str:
        """
        Returns a string representation of the hand for debugging.

        Returns:
            A string in the form "Hand([Card(...), ...])".
        """
        return f"Hand({self.cards!r})"

    def __str__(self) -> str:
        """
        Returns a string representation of the hand for display.

        Returns:
            A string in the form "Card(...), ...".
        """
        return ", ".join(str(card) for card in self.cards)
