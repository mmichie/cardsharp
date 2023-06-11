import random
from typing import List, Union
from cardsharp.common.card import Card, Suit, Rank


class Deck:
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
        suits = [Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS, Suit.SPADES]
        ranks = [
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

        return [Card(suit, rank) for suit in suits for rank in ranks]

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

    def deal(self) -> Card:
        """
        Pop a card from the deck.

        :return: A card instance.
        >>> deck = Deck()
        >>> card = deck.deal()
        >>> isinstance(card, Card)
        True
        """
        return self.cards.pop()

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
