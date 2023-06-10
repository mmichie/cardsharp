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


@unique
class Rank(Enum):
    """
    Enum for ranks in a card deck.
    """
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"
    ACE = "A"
    JOKER = "Joker"

    def __str__(self) -> str:
        return self.value


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
        if rank == Rank.JOKER:
            self.suit = None
            self.rank = Rank.JOKER
        else:
            if not isinstance(suit, Suit):
                raise ValueError(f"Invalid suit: {suit}")
            if not isinstance(rank, Rank):
                raise ValueError(f"Invalid rank: {rank}")
            self.suit = suit
            self.rank = rank

    def __repr__(self) -> str:
        """
        Provide a machine-readable representation of the card.

        :return: A string representation of the card.
        """
        if self.rank == Rank.JOKER:
            return f"Card(None, Rank.JOKER)"
        else:
            return f"Card(Suit.{self.suit.name}, Rank.{self.rank.name})"


    def __str__(self) -> str:
        """
        Provide a human-readable representation of the card.

        :return: A string representation of the card.
        """
        if self.rank == Rank.JOKER:
            return f"{self.rank.value}"
        else:
            return f"{self.rank.value} of {str(self.suit)}"

