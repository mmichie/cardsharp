"""
This module contains classes to represent a hand of cards in a card game.

It includes an abstract base class `AbstractHand`, and a concrete implementation `Hand`.
Each hand can have multiple cards, and provides methods for adding and removing cards.

Classes:

AbstractHand: An abstract base class for a hand of cards.
Hand: A concrete implementation of a hand of cards.
"""

from abc import ABC, abstractmethod
from cardsharp.common.card import Card


class AbstractHand(ABC):
    """
    An abstract base class for a hand of cards.

    This class provides a basic structure for a hand of cards, including methods to add and remove cards.
    Subclasses should override the __repr__ and __str__ methods to provide a string representation of the hand.
    """

    def __init__(self):
        self.cards = []

    def add_card(self, card: Card):
        """
        Adds a card to the hand.

        Args:
            card: The card to add.
        """
        self.cards.append(card)

    def remove_card(self, card: Card):
        """
        Removes a card from the hand.

        Args:
            card: The card to remove.
        """
        self.cards.remove(card)

    @abstractmethod
    def __repr__(self):
        """
        Returns a string representation of the object for debugging.
        """
        pass

    @abstractmethod
    def __str__(self):
        """
        Returns a string representation of the object for display.
        """
        pass


class Hand(AbstractHand):
    """
    A concrete implementation of a hand of cards.

    This class provides a string representation of a hand of cards for both debugging and display purposes.
    """

    def __init__(self):
        super().__init__()

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
