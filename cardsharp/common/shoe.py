from typing import List, Union, Optional, Callable
from cardsharp.common.card import Card
from cardsharp.common.deck import Deck
import random


class Shoe:
    def __init__(
        self,
        num_decks: int = 6,
        penetration: float = 0.75,
        use_csm: bool = False,
        burn_cards: int = 0,
        deck_factory: Optional[Callable[[], List[Card]]] = None,
        shuffle_type: str = "perfect",
        shuffle_count: Optional[int] = None,
    ):
        """
        Initialize a Shoe instance.

        :param num_decks: Number of decks to use in the shoe (default is 6)
        :param penetration: Percentage of cards to deal before reshuffling (default is 75%)
        :param use_csm: Whether to use a Continuous Shuffling Machine (CSM) which
                       returns cards to the shoe immediately after use
        :param burn_cards: Number of cards to burn after each shuffle (default is 0)
        :param deck_factory: Optional callable that returns a list of cards for one deck
        :param shuffle_type: Type of shuffle to use: "perfect", "riffle", or "strip" (default is "perfect")
        :param shuffle_count: Number of times to shuffle. If None, uses realistic defaults based on shuffle_type
        """
        if num_decks < 1:
            raise ValueError("Number of decks must be at least 1")
        if not 0 < penetration <= 1:
            raise ValueError("Penetration must be between 0 and 1")
        if burn_cards < 0:
            raise ValueError("Number of burn cards must be non-negative")
        if shuffle_type not in ("perfect", "riffle", "strip"):
            raise ValueError("shuffle_type must be 'perfect', 'riffle', or 'strip'")

        self.num_decks = num_decks
        self.penetration = penetration
        self.use_csm = use_csm
        self.burn_cards = burn_cards
        self.deck_factory = deck_factory
        self.shuffle_type = shuffle_type
        self.cards: List[Card] = []
        self.next_card_index = 0

        # Calculate total cards based on deck factory or assume standard deck
        if deck_factory:
            sample_deck = deck_factory()
            self.cards_per_deck = len(sample_deck)
        else:
            self.cards_per_deck = 52

        self.total_cards = self.cards_per_deck * num_decks
        self.reshuffle_point: int = int(self.total_cards * self.penetration)
        self.discarded_cards: List[Card] = []  # Track discarded cards for CSM
        self.burned_cards: List[Card] = []  # Track burned cards
        self.cut_card_reached = False  # Track if cut card has been reached

        # Set shuffle count based on type if not specified
        # Research shows: 7 riffle shuffles for 52 cards approaches randomness
        # Scale up for multiple decks (Bayer-Diaconis)
        if shuffle_count is None:
            if shuffle_type == "perfect":
                self.shuffle_count = 1  # One perfect shuffle is enough
            elif shuffle_type == "riffle":
                # Dealers typically do 3-5 riffles (insufficient for true randomness)
                # For realistic casino simulation, use 4 riffles
                # For mathematical randomness: 7 + log2(num_decks) riffles needed
                self.shuffle_count = 4  # Realistic dealer behavior
            elif shuffle_type == "strip":
                # Strip shuffles are less effective, need more
                self.shuffle_count = 6
        else:
            self.shuffle_count = shuffle_count

        self.initialize_shoe()

    def initialize_shoe(self):
        """Initialize the shoe with the specified number of decks and shuffle."""
        self.cards = []
        self.discarded_cards = []
        # Combine all decks into one list
        for _ in range(self.num_decks):
            if self.deck_factory:
                # Use custom deck factory
                self.cards.extend(self.deck_factory())
            else:
                # Use standard deck
                deck = Deck()
                self.cards.extend(deck.cards)
        self.shuffle()

    def _gsr_riffle_shuffle(self, cards: List[Card]) -> List[Card]:
        """
        Perform a single GSR (Gilbert-Shannon-Reeds) riffle shuffle.

        This models real riffle shuffles where the deck is cut into two halves
        and cards are interleaved probabilistically. This is the mathematically
        correct model of how real riffle shuffles work.

        Reference: Bayer, D., & Diaconis, P. (1992). "Trailing the Dovetail Shuffle to its Lair"

        :param cards: List of cards to shuffle
        :return: Shuffled list of cards
        """
        n = len(cards)
        if n <= 1:
            return cards

        # Step 1: Cut the deck - binomial distribution determines cut point
        # This models the natural variation in where dealers split the deck
        # Not always exactly at midpoint
        cut_point = 0
        for i in range(n):
            if random.random() < 0.5:
                cut_point += 1

        # Split into two halves
        left = cards[:cut_point]
        right = cards[cut_point:]

        # Step 2: Riffle - cards drop from each half with probability
        # proportional to the size of that half
        result = []
        left_idx = 0
        right_idx = 0

        while left_idx < len(left) or right_idx < len(right):
            left_remaining = len(left) - left_idx
            right_remaining = len(right) - right_idx

            if left_remaining == 0:
                # Only right cards remain
                result.extend(right[right_idx:])
                break
            elif right_remaining == 0:
                # Only left cards remain
                result.extend(left[left_idx:])
                break
            else:
                # Choose which pile to take from based on remaining cards
                # This is the key probabilistic step
                if random.random() < left_remaining / (left_remaining + right_remaining):
                    result.append(left[left_idx])
                    left_idx += 1
                else:
                    result.append(right[right_idx])
                    right_idx += 1

        return result

    def _strip_shuffle(self, cards: List[Card]) -> List[Card]:
        """
        Perform a strip shuffle (running cut).

        Cards are stripped from the top in small packets and dropped to create
        a new pile. This is less effective at randomizing than riffle shuffles.

        :param cards: List of cards to shuffle
        :return: Shuffled list of cards
        """
        n = len(cards)
        if n <= 1:
            return cards

        result = []
        remaining = cards[:]

        # Strip off packets until deck is exhausted
        while remaining:
            # Packet size varies - typically 3-15 cards
            # Smaller packets = more mixing
            packet_size = min(random.randint(3, 15), len(remaining))

            # Take packet from top
            packet = remaining[:packet_size]
            remaining = remaining[packet_size:]

            # Drop packet on top of result
            result = packet + result

        return result

    def shuffle(self):
        """Shuffle all cards in the shoe and reset the next card index."""
        # If using CSM, include discarded cards in the shuffle
        if self.use_csm and self.discarded_cards:
            self.cards.extend(self.discarded_cards)
            self.discarded_cards = []

        # Perform shuffle based on type
        if self.shuffle_type == "perfect":
            # Perfect shuffle - cryptographically random
            random.shuffle(self.cards)
        elif self.shuffle_type == "riffle":
            # GSR riffle shuffle - realistic model of casino shuffling
            for _ in range(self.shuffle_count):
                self.cards = self._gsr_riffle_shuffle(self.cards)
        elif self.shuffle_type == "strip":
            # Strip shuffle - less effective but used in some casinos
            for _ in range(self.shuffle_count):
                self.cards = self._strip_shuffle(self.cards)

        self.next_card_index = 0
        self.cut_card_reached = False

        # Burn cards after shuffle if specified
        if self.burn_cards > 0 and not self.use_csm:
            # Ensure we don't burn more cards than available
            cards_to_burn = min(self.burn_cards, len(self.cards))
            self.burned_cards = []
            for _ in range(cards_to_burn):
                burned_card = self.cards[self.next_card_index]
                self.burned_cards.append(burned_card)
                self.next_card_index += 1

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
                self.cut_card_reached = True
                self.shuffle()

            card = self.cards[self.next_card_index]
            self.next_card_index += 1

            # Check if we just reached the cut card
            if self.next_card_index >= self.reshuffle_point:
                self.cut_card_reached = True

            return card

        # For non-CSM mode with multiple cards
        if not self.use_csm:
            # Check if reshuffle is needed due to penetration or not enough cards
            if (
                self.next_card_index >= self.reshuffle_point
                or self.next_card_index + num_cards > self.total_cards
            ):
                self.cut_card_reached = True
                self.shuffle()

            # Deal the cards using direct indexing instead of slicing
            if num_cards == 1:
                card = self.cards[self.next_card_index]
                self.next_card_index += 1

                # Check if we just reached the cut card
                if self.next_card_index >= self.reshuffle_point:
                    self.cut_card_reached = True

                return card
            else:
                start = self.next_card_index
                end = start + num_cards
                dealt_cards = self.cards[start:end]
                self.next_card_index = end

                # Check if we just reached the cut card
                if self.next_card_index >= self.reshuffle_point:
                    self.cut_card_reached = True

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

    def is_cut_card_reached(self) -> bool:
        """Return whether the cut card has been reached."""
        return self.cut_card_reached

    def get_burned_cards(self) -> List[Card]:
        """Return the list of burned cards from the last shuffle."""
        return self.burned_cards.copy()

    def get_penetration_percentage(self) -> float:
        """Return the current penetration percentage (how far through the shoe we are)."""
        if self.use_csm:
            return 0.0  # CSM doesn't have meaningful penetration
        return self.next_card_index / self.total_cards

    def __str__(self) -> str:
        return f"Shoe with {self.cards_remaining} cards remaining"

    def __repr__(self) -> str:
        return f"Shoe(num_decks={self.num_decks}, penetration={self.penetration}, use_csm={self.use_csm}, burn_cards={self.burn_cards}, shuffle_type='{self.shuffle_type}', shuffle_count={self.shuffle_count})"
