"""Blackjack-specific constants and value mappings."""

from cardsharp.common.card import Rank

# Blackjack-specific card values (kept for reference/compatibility)
BLACKJACK_VALUES = {
    Rank.TWO: 2,
    Rank.THREE: 3,
    Rank.FOUR: 4,
    Rank.FIVE: 5,
    Rank.SIX: 6,
    Rank.SEVEN: 7,
    Rank.EIGHT: 8,
    Rank.NINE: 9,
    Rank.TEN: 10,
    Rank.JACK: 10,
    Rank.QUEEN: 10,
    Rank.KING: 10,
    Rank.ACE: 11,  # Default ace value in blackjack
    Rank.JOKER: 0,
}

# Optimized array-indexed lookup (indexed by Rank.value)
_BLACKJACK_VALUE_ARRAY = [
    0,   # JOKER (0)
    11,  # ACE (1)
    2,   # TWO (2)
    3,   # THREE (3)
    4,   # FOUR (4)
    5,   # FIVE (5)
    6,   # SIX (6)
    7,   # SEVEN (7)
    8,   # EIGHT (8)
    9,   # NINE (9)
    10,  # TEN (10)
    10,  # JACK (11)
    10,  # QUEEN (12)
    10,  # KING (13)
]


def get_blackjack_value(rank: Rank) -> int:
    """Get the blackjack value for a given rank using optimized array lookup."""
    return _BLACKJACK_VALUE_ARRAY[rank.value]
