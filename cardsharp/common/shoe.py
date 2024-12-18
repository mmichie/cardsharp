from typing import List, Union
from cardsharp.common.card import Card
from cardsharp.common.deck import Deck
import random


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
        self.next_card_index = 0
        self.total_cards = 52 * num_decks  # Total number of cards
        self.reshuffle_point: int = int(self.total_cards * (1 - self.penetration))
        self.initialize_shoe()

    def initialize_shoe(self):
        """Initialize the shoe with the specified number of decks and shuffle."""
        self.cards = []
        # Combine all decks into one list
        for _ in range(self.num_decks):
            deck = Deck()
            self.cards.extend(deck.cards)
        self.shuffle()

    def shuffle(self):
        """Shuffle all cards in the shoe and reset the next card index."""
        random.shuffle(self.cards)
        self.next_card_index = 0
        # No need to recompute reshuffle_point as total_cards doesn't change

    def deal(self, num_cards: int = 1) -> Union[Card, List[Card]]:
        """
        Deal cards from the shoe. Reshuffle if the reshuffle point is reached or not enough cards.

        :param num_cards: Number of cards to deal (default is 1)
        :return: A single Card or a list of Cards
        """
        # Check if reshuffle is needed due to penetration
        if self.next_card_index >= self.reshuffle_point:
            self.shuffle()

        # Check if we have enough cards to deal, else reshuffle
        if self.next_card_index + num_cards > self.total_cards:
            self.shuffle()

        # Deal the cards using slicing and increment the index
        dealt_cards = self.cards[
            self.next_card_index : self.next_card_index + num_cards
        ]
        self.next_card_index += num_cards

        return dealt_cards[0] if num_cards == 1 else dealt_cards

    @property
    def cards_remaining(self) -> int:
        """Return the number of cards remaining in the shoe."""
        return self.total_cards - self.next_card_index

    def __str__(self) -> str:
        return f"Shoe with {self.cards_remaining} cards remaining"

    def __repr__(self) -> str:
        return f"Shoe(num_decks={self.num_decks}, penetration={self.penetration})"
