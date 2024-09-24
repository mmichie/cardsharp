from typing import List, Union
from cardsharp.common.card import Card
from cardsharp.common.deck import Deck

class Shoe:
    def __init__(self, num_decks: int = 6, penetration: float = 0.75):
        """
        Initialize a Shoe instance.

        :param num_decks: Number of decks to use in the shoe (default is 6)
        :param penetration: Percentage of cards to deal before reshuffling (default is 75%)
        """
        if num_decks < 1:
            raise ValueError("Number of decks must be at least 1")
        if not 0 < penetration <= 1:
            raise ValueError("Penetration must be between 0 and 1")

        self.num_decks = num_decks
        self.penetration = penetration
        self.cards: List[Card] = []
        self.dealt_cards: List[Card] = []
        self.reshuffle_point: int = 0
        self.initialize_shoe()

    def initialize_shoe(self):
        """Initialize the shoe with the specified number of decks and shuffle."""
        self.cards = []
        for _ in range(self.num_decks):
            deck = Deck()
            self.cards.extend(deck.cards)
        self.shuffle()

    def shuffle(self):
        """Shuffle all cards in the shoe and reset the reshuffle point."""
        self.cards.extend(self.dealt_cards)
        self.dealt_cards = []
        Deck.shuffle(self)  # Use the shuffle method from the Deck class
        self.reshuffle_point = int(len(self.cards) * (1 - self.penetration))

    def deal(self, num_cards: int = 1) -> Union[Card, List[Card]]:
        """
        Deal cards from the shoe. Reshuffle if the reshuffle point is reached.

        :param num_cards: Number of cards to deal (default is 1)
        :return: A single Card or a list of Cards
        """
        if num_cards > len(self.cards):
            raise ValueError("Not enough cards in the shoe to deal")

        if len(self.cards) <= self.reshuffle_point:
            self.shuffle()

        dealt = []
        for _ in range(num_cards):
            card = self.cards.pop()
            self.dealt_cards.append(card)
            dealt.append(card)

        return dealt[0] if num_cards == 1 else dealt

    @property
    def cards_remaining(self) -> int:
        """Return the number of cards remaining in the shoe."""
        return len(self.cards)

    def __str__(self) -> str:
        return f"Shoe with {self.cards_remaining} cards remaining"

    def __repr__(self) -> str:
        return f"Shoe(num_decks={self.num_decks}, penetration={self.penetration})"
