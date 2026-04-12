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
