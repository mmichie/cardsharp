"""
Testing utilities for cardsharp games.

Provides RiggedShoe for deterministic card dealing in tests,
plus card-parsing helpers for concise test notation.

Example:
    from cardsharp.common.testing import RiggedShoe, cards

    # Flat card list in deal order
    shoe = RiggedShoe(cards("As", "Th", "Kh", "7d"))

    # Specify hands directly -- deal interleaving computed for you
    shoe = RiggedShoe.from_hands(
        player=["As", "Kh"],
        dealer=["Th", "7d"],
        extra=["5c"],  # for hits, splits, dealer draws
    )
"""

from typing import List, Optional, Union

from cardsharp.common.card import Card, Rank, Suit
from cardsharp.common.shoe import Shoe


_RANK_MAP = {
    "A": Rank.ACE,
    "2": Rank.TWO,
    "3": Rank.THREE,
    "4": Rank.FOUR,
    "5": Rank.FIVE,
    "6": Rank.SIX,
    "7": Rank.SEVEN,
    "8": Rank.EIGHT,
    "9": Rank.NINE,
    "T": Rank.TEN,
    "10": Rank.TEN,
    "J": Rank.JACK,
    "Q": Rank.QUEEN,
    "K": Rank.KING,
}

_SUIT_MAP = {
    "s": Suit.SPADES,
    "h": Suit.HEARTS,
    "d": Suit.DIAMONDS,
    "c": Suit.CLUBS,
}


def parse_card(notation: str) -> Card:
    """Parse card notation like 'As' -> Card(Suit.SPADES, Rank.ACE).

    Rank codes: A 2-9 T J Q K
    Suit codes: s(spades) h(hearts) d(diamonds) c(clubs)
    """
    rank_str = notation[:-1]
    suit_str = notation[-1]
    try:
        return Card(_SUIT_MAP[suit_str], _RANK_MAP[rank_str])
    except KeyError:
        raise ValueError(
            f"Invalid card notation: {notation!r}. "
            f"Expected format like 'As', 'Th', '9d'."
        )


def cards(*notations: str) -> List[Card]:
    """Parse multiple card notations.

    Example: cards("As", "Kh", "Th") -> [Ace of Spades, King of Hearts, 10 of Hearts]
    """
    return [parse_card(n) for n in notations]


class RiggedShoe(Shoe):
    """A shoe that deals cards in a predetermined order for testing.

    Extends Shoe as a drop-in replacement. Shuffling is a no-op,
    and cards are dealt in the exact order provided.

    Use the constructor for a flat card list, or from_hands() to
    specify player/dealer hands with automatic deal-order interleaving.
    """

    def __init__(self, card_list: List[Card]):
        # Skip Shoe.__init__() -- we don't need deck building or shuffling.
        # Set attributes the game engine may inspect.
        self._queue: List[Card] = list(card_list)
        self._position: int = 0
        self.cards: List[Card] = list(card_list)
        self.num_decks = 1
        self.penetration = 1.0
        self.use_csm = False
        self.burn_cards = 0
        self.cut_card_reached = False
        self.discarded_cards: List[Card] = []
        self.burned_cards: List[Card] = []
        self.total_cards = len(card_list)
        self.next_card_index = 0
        self.shuffle_type = "perfect"
        self.shuffle_count = 1
        self.cards_per_deck = len(card_list)
        self.reshuffle_point = len(card_list)

    @classmethod
    def from_hands(
        cls,
        *,
        player: Optional[List[str]] = None,
        dealer: List[str],
        extra: Optional[List[str]] = None,
        players: Optional[List[List[str]]] = None,
    ) -> "RiggedShoe":
        """Build a shoe from specified hands with automatic deal-order interleaving.

        In blackjack, initial cards are dealt in rounds:
          Round 1: P1, P2, ..., Dealer  (one card each)
          Round 2: P1, P2, ..., Dealer  (one card each)

        Args:
            player: Cards for a single player, e.g. ["As", "Kh"].
            dealer: Cards for the dealer, e.g. ["Th", "7d"].
            extra: Additional cards for hits, splits, and dealer draws.
            players: For multiplayer, list of per-player card lists.
                     Cannot be used with ``player``.

        Example -- single player::

            shoe = RiggedShoe.from_hands(
                player=["As", "Kh"],
                dealer=["Th", "7d"],
                extra=["5c"],
            )
            # Deal order: As, Th, Kh, 7d, 5c

        Example -- two players::

            shoe = RiggedShoe.from_hands(
                players=[["As", "Kh"], ["8h", "8d"]],
                dealer=["Th", "7d"],
                extra=["3c", "Td"],
            )
            # Deal order: As, 8h, Th, Kh, 8d, 7d, 3c, Td
        """
        if player is not None and players is not None:
            raise ValueError(
                "Use 'player' for single player or 'players' for multiplayer, not both"
            )
        if player is None and players is None:
            raise ValueError("Must specify 'player' or 'players'")

        if player is not None:
            player_hands = [[parse_card(c) for c in player]]
        elif players is not None:
            player_hands = [[parse_card(c) for c in hand] for hand in players]
        else:
            player_hands = []

        dealer_cards = [parse_card(c) for c in dealer]
        extra_cards = [parse_card(c) for c in (extra or [])]

        # Interleave: 2 rounds of one card to each participant
        interleaved: List[Card] = []
        for round_idx in range(2):
            for hand in player_hands:
                if round_idx < len(hand):
                    interleaved.append(hand[round_idx])
            if round_idx < len(dealer_cards):
                interleaved.append(dealer_cards[round_idx])

        interleaved.extend(extra_cards)
        return cls(interleaved)

    def deal(self, num_cards: int = 1) -> Union[Card, List[Card]]:
        """Deal the next predetermined card(s)."""
        remaining = len(self._queue) - self._position
        if num_cards > remaining:
            raise ValueError(
                f"RiggedShoe exhausted: requested {num_cards} card(s) but only "
                f"{remaining} remain (dealt {self._position}/{len(self._queue)}). "
                f"Add more cards to 'extra' when building the shoe."
            )
        if num_cards == 1:
            card = self._queue[self._position]
            self._position += 1
            return card
        start = self._position
        self._position += num_cards
        return self._queue[start : self._position]

    def shuffle(self):
        """No-op: maintain predetermined card order."""
        pass

    def initialize_shoe(self):
        """No-op: cards are set at construction time."""
        pass

    @property
    def cards_remaining(self) -> int:
        return len(self._queue) - self._position

    def is_cut_card_reached(self) -> bool:
        return False

    def get_penetration_percentage(self) -> float:
        if not self._queue:
            return 0.0
        return self._position / len(self._queue)

    def get_burned_cards(self) -> List[Card]:
        return []

    def __repr__(self) -> str:
        return (
            f"RiggedShoe({len(self._queue)} cards, "
            f"position={self._position})"
        )
