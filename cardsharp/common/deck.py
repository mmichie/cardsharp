"""
This module contains the Deck class, which represents a deck of cards.

>>> deck = Deck()
>>> deck.size
52
>>> deck.deal()
Card(Suit.HEARTS, Rank.TWO)
>>> deck.size
51
"""

import random
from typing import List, Union

from cardsharp.common.card import Card, Rank, Suit


class Deck:
    """
    A class representing a deck of cards.
    """

    # Precompute the default deck
    _default_deck = [
        Card(suit, rank)
        for suit in [Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS, Suit.SPADES]
        for rank in [
            Rank.TWO,
            Rank.THREE,
            Rank.FOUR,
            Rank.FIVE,
            Rank.SIX,
            Rank.SEVEN,
            Rank.EIGHT,
            Rank.NINE,
            Rank.TEN,
            Rank.JACK,
            Rank.QUEEN,
            Rank.KING,
            Rank.ACE,
        ]
    ]

    def __init__(self, cards: Union[List[Card], None] = None):
        """
        Initialize a Deck instance.

        :param cards: A list of Card instances to populate the deck (optional).
                      If not provided, a default deck will be constructed.
        >>> deck = Deck()
        >>> deck.size
        52
        """
        if cards is None:
            self.cards: List[Card] = self.initialize_default_deck()
        else:
            self.cards = cards.copy()

    def initialize_default_deck(self) -> List[Card]:
        """
        Construct a default deck with all possible combinations of suits and ranks.

        :return: A list of Card instances representing the default deck.
        >>> deck = Deck()
        >>> len(deck.cards)
        52
        """
        return self._default_deck.copy()

    def shuffle(self):
        """
        Shuffle the cards in the deck.
        >>> deck = Deck()
        >>> original_order = deck.cards.copy()
        >>> deck.shuffle()
        >>> set(deck.cards) != set(original_order)
        True
        """
        random.shuffle(self.cards)
        return self

    def deal(self, num_cards=1) -> Union[Card, List[Card]]:
        """
        Pop n cards from the deck.

        :return: A card instance or a list of card instances.
        >>> deck = Deck()
        >>> cards = deck.deal(5)
        >>> len(cards)
        5
        """
        if num_cards == 1:
            return self.cards.pop()
        return [self.cards.pop() for _ in range(num_cards)]

    @property
    def size(self) -> int:
        """
        Return the number of remaining cards in the deck.

        :return: The size of the deck.
        >>> deck = Deck()
        >>> deck.size
        52
        """
        return len(self.cards)

    def is_empty(self) -> bool:
        """
        Check if the deck is empty.

        :return: True if the deck is empty, False otherwise.
        """
        return len(self.cards) == 0

    def reset(self):
        """
        Reset the deck by recreating
        """
        self.cards = self.initialize_default_deck()

    def __repr__(self) -> str:
        """
        Provide a machine-readable representation of the deck.

        :return: A string representation of the deck.
        >>> deck = Deck()
        >>> repr(deck)
        "Deck([...])"
        """
        return f"Deck({[repr(card) for card in self.cards]})"

    def __str__(self) -> str:
        """
        Provide a human-readable representation of the deck.

        :return: A string representation of the deck.
        >>> deck = Deck()
        >>> str(deck)
        "Deck of 52 cards"
        """
        return f"Deck of {len(self.cards)} cards"
