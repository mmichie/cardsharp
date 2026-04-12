"""Types and constants for the probabilistic solver."""

from typing import NamedTuple

from cardsharp.blackjack.action import Action

# Card values in blackjack: Ace=1, 2-9, 10 (covers T/J/Q/K)
CARD_VALUES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)

# Infinite-deck draw probabilities: 1/13 each for A-9, 4/13 for 10-value
INF_DECK_PROBS = (
    1 / 13,  # Ace
    1 / 13,  # 2
    1 / 13,  # 3
    1 / 13,  # 4
    1 / 13,  # 5
    1 / 13,  # 6
    1 / 13,  # 7
    1 / 13,  # 8
    1 / 13,  # 9
    4 / 13,  # 10/J/Q/K
)

# Card value index: CARD_VALUES[idx] = value, idx used for composition arrays
CARD_IDX = {v: i for i, v in enumerate(CARD_VALUES)}


class Deck:
    """Draw probability source for the solver.

    Two modes: infinite deck (fixed probs) and finite deck (composition-
    dependent, probabilities change as cards are drawn).
    """

    __slots__ = ("_counts", "_total", "_is_infinite", "_key")

    def __init__(self, counts: tuple, is_infinite: bool = False):
        self._counts = counts
        self._total = sum(counts) if not is_infinite else 13  # arbitrary for inf
        self._is_infinite = is_infinite
        self._key = "inf" if is_infinite else counts

    @classmethod
    def infinite(cls):
        """Create an infinite-deck source (constant probabilities)."""
        return cls(counts=(), is_infinite=True)

    @classmethod
    def finite(cls, num_decks: int):
        """Create a finite-deck composition.

        Counts: (n_ace, n_2, n_3, ..., n_9, n_10value)
        Each rank A-9 has 4*num_decks cards. 10-value has 16*num_decks.
        """
        counts = tuple(4 * num_decks for _ in range(9)) + (16 * num_decks,)
        return cls(counts)

    def draw(self, card_idx: int):
        """Return (probability, new_deck_after_removing_card).

        For infinite deck, returns (fixed_prob, self).
        For finite deck, returns (count/total, decremented deck).
        """
        if self._is_infinite:
            return INF_DECK_PROBS[card_idx], self

        if self._total == 0 or self._counts[card_idx] == 0:
            return 0.0, self

        p = self._counts[card_idx] / self._total
        new_counts = list(self._counts)
        new_counts[card_idx] -= 1
        return p, Deck(tuple(new_counts))

    def remove_card(self, card_val: int):
        """Remove a specific card value from the deck. Returns new Deck."""
        if self._is_infinite:
            return self
        idx = CARD_IDX[card_val]
        new_counts = list(self._counts)
        new_counts[idx] -= 1
        return Deck(tuple(new_counts))

    @property
    def key(self):
        """Hashable key for memoization."""
        return self._key


class StateEV(NamedTuple):
    """EV for each action at a given player state vs dealer upcard."""

    hit: float
    stand: float
    double: float  # float('nan') if not allowed
    split: float  # float('nan') if not allowed
    surrender: float  # float('nan') if not allowed
    best_action: Action
    best_ev: float


def display_value(hard_total: int, usable_ace: bool) -> int:
    """Convert internal hand state to display value."""
    return hard_total + 10 if usable_ace else hard_total


def add_card(hard_total: int, usable_ace: bool, card_val: int):
    """Add a card to a hand state, returning (new_hard, new_usable, display).

    hard_total: sum of all cards with Ace=1
    usable_ace: whether one Ace currently counts as 11
    card_val: 1 for Ace, 2-10 for others
    """
    new_hard = hard_total + card_val
    new_usable = usable_ace

    # New ace might be usable
    if card_val == 1 and not new_usable and new_hard + 10 <= 21:
        new_usable = True

    # Check if usable ace must be demoted
    disp = new_hard + 10 if new_usable else new_hard
    if disp > 21 and new_usable:
        new_usable = False
        disp = new_hard

    return new_hard, new_usable, disp


def hand_state_from_cards(c1: int, c2: int):
    """Build initial hand state from two card values.

    Returns (hard_total, usable_ace, display_value, is_pair).
    """
    hard = c1 + c2
    usable = False
    if c1 == 1 and hard + 10 <= 21:
        usable = True
    elif c2 == 1 and not usable and hard + 10 <= 21:
        usable = True
    disp = hard + 10 if usable else hard
    is_pair = c1 == c2
    return hard, usable, disp, is_pair
