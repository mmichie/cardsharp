"""Blackjack-specific constants and value mappings."""

from cardsharp.common.card import Rank

# Blackjack-specific card values
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


def get_blackjack_value(rank: Rank) -> int:
    """Get the blackjack value for a given rank."""
    return BLACKJACK_VALUES.get(rank, rank.rank_value)
