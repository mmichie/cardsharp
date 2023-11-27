"""
This module defines the `Suit`, `Rank`, and `Card` classes, which are used to represent playing cards.

- `Suit`: An enum representing the four suits of a standard deck of playing
cards: Hearts, Diamonds, Clubs, and Spades.

- `Rank`: An enum representing the thirteen ranks of a standard deck of playing
cards: Two through Ten, Jack, Queen, King, and Ace. It also includes a Joker
rank.

- `Card`: A class representing a playing card. A card has a suit and a
rank. The `Card` class also provides methods for comparing cards and for
converting cards to strings for display.

This module is part of the `cardsharp` package, a framework for creating and playing card games.
"""

from enum import Enum, unique


@unique
class Suit(Enum):
    """
    Enum for suits in a card deck.
    """

    HEARTS = "♥"
    DIAMONDS = "♦"
    CLUBS = "♣"
    SPADES = "♠"

    def __str__(self) -> str:
        return self.value


class Rank(Enum):
    """
    Enum for ranks in a card deck.
    """

    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 10
    QUEEN = 10
    KING = 10
    ACE = 11
    JOKER = 0

    @property
    def rank_value(self):
        """The value of the rank, used for scoring."""
        return self.value

    @property
    def rank_str(self):
        """A string representation of the rank."""
        if self == self.JOKER:
            return "Joker"
        if self in (self.JACK, self.QUEEN, self.KING):
            return self.name[0]
        return str(self.value)

    def __str__(self) -> str:
        return self.rank_str


class Card:
    """
    Class representing a playing card. This class is a member of a card deck.

    >>> card = Card(Suit.HEARTS, Rank.TWO)
    >>> print(card)
    2 of ♥
    >>> joker = Card(None, Rank.JOKER)
    >>> print(joker)
    Joker
    """

    def __init__(self, suit: Suit, rank: Rank):
        """
        Initialize a Card instance.

        :param suit: Suit of the card (one of the Suit enums, or None for Jokers)
        :param rank: Rank of the card (one of the Rank enums)
        """
        match rank:
            case Rank.JOKER:
                self.suit = None
                self.rank = rank
                self.str_rep = f"{self.rank.rank_str}"
            case _:
                if not isinstance(suit, Suit):
                    raise TypeError(f"Invalid suit: {suit}")
                if not isinstance(rank, Rank):
                    raise TypeError(f"Invalid rank: {rank}")
                self.suit = suit
                self.rank = rank
                self.str_rep = f"{self.rank.rank_str} of {str(self.suit)}"

    def __eq__(self, other):
        """
        Checks if this card is equal to another card.

        :param other: The other card to compare to.
        :return: True if the cards have the same rank and suit, False otherwise.
        """
        if isinstance(other, Card):
            return self.rank == other.rank and self.suit == other.suit
        return NotImplemented

    def __hash__(self):
        return hash((self.suit, self.rank))

    def __repr__(self) -> str:
        """
        Provide a machine-readable representation of the card.

        :return: A string representation of the card.
        """
        if self.rank == Rank.JOKER:
            return "Card(None, Rank.JOKER)"

        return f"Card(Suit.{self.suit.name if self.suit else 'None'}, Rank.{self.rank.name})"

    def __str__(self) -> str:
        """
        Provide a human-readable representation of the card.

        :return: A string representation of the card.
        """
        return self.str_rep
