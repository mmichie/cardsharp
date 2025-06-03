"""Durak-specific constants and value mappings."""

from cardsharp.common.card import Rank

# Durak-specific card values (traditional Russian deck order)
DURAK_VALUES = {
    Rank.TWO: 2,
    Rank.THREE: 3,
    Rank.FOUR: 4,
    Rank.FIVE: 5,
    Rank.SIX: 6,
    Rank.SEVEN: 7,
    Rank.EIGHT: 8,
    Rank.NINE: 9,
    Rank.TEN: 10,
    Rank.JACK: 11,
    Rank.QUEEN: 12,
    Rank.KING: 13,
    Rank.ACE: 14,  # Ace is highest in Durak
    Rank.JOKER: 0,
}


def get_durak_value(rank: Rank) -> int:
    """Get the durak value for a given rank."""
    return DURAK_VALUES.get(rank, rank.rank_value)
