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
        # The bottleneck is in random.randint, so we'll minimize its use

        # Common case: deal a single card in non-CSM mode - most frequent case
        if num_cards == 1 and not self.use_csm:
            # Fast path for single card deal
            if (
                self.next_card_index >= self.reshuffle_point
                or self.next_card_index >= self.total_cards
            ):
                self.shuffle()

            card = self.cards[self.next_card_index]
            self.next_card_index += 1
            return card

        # For non-CSM mode with multiple cards
        if not self.use_csm:
            # Check if reshuffle is needed due to penetration or not enough cards
            if (
                self.next_card_index >= self.reshuffle_point
                or self.next_card_index + num_cards > self.total_cards
            ):
                self.shuffle()

            # Deal the cards using direct indexing instead of slicing
            if num_cards == 1:
                card = self.cards[self.next_card_index]
                self.next_card_index += 1
                return card
            else:
                start = self.next_card_index
                end = start + num_cards
                dealt_cards = self.cards[start:end]
                self.next_card_index = end
                return dealt_cards
        else:
            # For CSM mode - highly optimized implementation
            cards_len = len(self.cards)

            # Fast check if we need to shuffle cards back
            if cards_len < num_cards:
                # If we need to shuffle cards back in
                if self.discarded_cards:
                    self.cards.extend(self.discarded_cards)
                    self.discarded_cards = []
                    # Use built-in shuffle which is faster for large lists
                    random.shuffle(self.cards)
                else:
                    # This shouldn't happen, but just in case
                    self.initialize_shoe()
                cards_len = len(self.cards)

            # Optimize for single card case (most common)
            if num_cards == 1:
                # Generate a single random number instead of using randint
                card_index = int(random.random() * cards_len)
                card = self.cards[card_index]

                # Faster removal by swapping with the last element and popping
                self.cards[card_index] = self.cards[cards_len - 1]
                self.cards.pop()

                self.discarded_cards.append(card)

                # Check if we need to shuffle some cards back
                if (
                    cards_len < self.total_cards * 0.2
                    and len(self.discarded_cards) > self.total_cards * 0.4
                ):
                    # Take some discarded cards and put them back
                    num_to_return = len(self.discarded_cards) // 2
                    self.cards.extend(self.discarded_cards[:num_to_return])
                    self.discarded_cards = self.discarded_cards[num_to_return:]
                    random.shuffle(self.cards)

                return card
            else:
                # For multiple cards, pre-generate all random indices at once
                dealt_cards = []
                card_indices = [
                    int(random.random() * (cards_len - i)) for i in range(num_cards)
                ]

                for card_index in card_indices:
                    card = self.cards[card_index]
                    dealt_cards.append(card)
                    self.discarded_cards.append(card)

                    # Swap and remove
                    self.cards[card_index] = self.cards[cards_len - 1]
                    self.cards.pop()
                    cards_len -= 1

                # Check if we need to shuffle some cards back
                if (
                    cards_len < self.total_cards * 0.2
                    and len(self.discarded_cards) > self.total_cards * 0.4
                ):
                    # Take some discarded cards and put them back
                    num_to_return = len(self.discarded_cards) // 2
                    self.cards.extend(self.discarded_cards[:num_to_return])
                    self.discarded_cards = self.discarded_cards[num_to_return:]
                    random.shuffle(self.cards)

                return dealt_cards

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
