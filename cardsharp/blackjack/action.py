"""Defines the Action enum for the possible actions a player can take in a game of blackjack."""
from enum import Enum


class Action(Enum):
    """Enum for the possible actions a player can take in a game of blackjack."""

    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    SURRENDER = "surrender"
    INSURANCE = "insurance"
