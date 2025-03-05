from typing import List, Union
from cardsharp.common.card import Card
from cardsharp.common.deck import Deck
import random


class Shoe:
    def __init__(
        self, num_decks: int = 6, penetration: float = 0.75, use_csm: bool = False
    ):
        """
        Initialize a Shoe instance.

        :param num_decks: Number of decks to use in the shoe (default is 6)
        :param penetration: Percentage of cards to deal before reshuffling (default is 75%)
        :param use_csm: Whether to use a Continuous Shuffling Machine (CSM) which
                       returns cards to the shoe immediately after use
        """
        if num_decks < 1:
            raise ValueError("Number of decks must be at least 1")
        if not 0 < penetration <= 1:
            raise ValueError("Penetration must be between 0 and 1")

        self.num_decks = num_decks
        self.penetration = penetration
        self.use_csm = use_csm
        self.cards: List[Card] = []
        self.next_card_index = 0
        self.total_cards = 52 * num_decks  # Total number of cards
        self.reshuffle_point: int = int(self.total_cards * (1 - self.penetration))
        self.discarded_cards: List[Card] = []  # Track discarded cards for CSM
        self.initialize_shoe()

    def initialize_shoe(self):
        """Initialize the shoe with the specified number of decks and shuffle."""
        self.cards = []
        self.discarded_cards = []
        # Combine all decks into one list
        for _ in range(self.num_decks):
            deck = Deck()
            self.cards.extend(deck.cards)
        self.shuffle()

    def shuffle(self):
        """Shuffle all cards in the shoe and reset the next card index."""
        # If using CSM, include discarded cards in the shuffle
        if self.use_csm and self.discarded_cards:
            self.cards.extend(self.discarded_cards)
            self.discarded_cards = []

        random.shuffle(self.cards)
        self.next_card_index = 0
        # No need to recompute reshuffle_point as total_cards doesn't change

    def deal(self, num_cards: int = 1) -> Union[Card, List[Card]]:
        """
        Deal cards from the shoe. Reshuffle if the reshuffle point is reached or not enough cards.
        For CSM mode, immediately reshuffle used cards back into the shoe.

        :param num_cards: Number of cards to deal (default is 1)
        :return: A single Card or a list of Cards
        """
        # For non-CSM mode
        if not self.use_csm:
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
        else:
            # For CSM mode - randomly select cards from the available ones
            dealt_cards = []
            for _ in range(num_cards):
                if not self.cards:
                    # If we've somehow used all cards, shuffle the discarded ones back
                    if self.discarded_cards:
                        self.cards = self.discarded_cards
                        self.discarded_cards = []
                        random.shuffle(self.cards)
                    else:
                        # This shouldn't happen, but just in case
                        self.initialize_shoe()

                # Take a random card from the shoe
                card_index = random.randint(0, len(self.cards) - 1)
                card = self.cards.pop(card_index)
                dealt_cards.append(card)

                # In a real CSM, the card would go back into the machine
                # but we'll add it to discarded_cards for later shuffling
                self.discarded_cards.append(card)

            # If we've used a significant portion of cards, shuffle some back in
            if len(self.cards) < self.total_cards * 0.25 and self.discarded_cards:
                # Take some (not all) discarded cards and put them back
                num_to_return = len(self.discarded_cards) // 2
                cards_to_return = random.sample(self.discarded_cards, num_to_return)
                for card in cards_to_return:
                    self.discarded_cards.remove(card)
                self.cards.extend(cards_to_return)
                random.shuffle(self.cards)

        return dealt_cards[0] if num_cards == 1 else dealt_cards

    @property
    def cards_remaining(self) -> int:
        """Return the number of cards remaining in the shoe."""
        if self.use_csm:
            return len(self.cards)
        else:
            return self.total_cards - self.next_card_index

    def __str__(self) -> str:
        return f"Shoe with {self.cards_remaining} cards remaining"

    def __repr__(self) -> str:
        return f"Shoe(num_decks={self.num_decks}, penetration={self.penetration}, use_csm={self.use_csm})"
