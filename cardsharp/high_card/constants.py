"""High Card-specific constants and value mappings."""

from cardsharp.common.card import Rank

# High Card uses the same values as War (Ace is highest)
HIGH_CARD_VALUES = {
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
    Rank.ACE: 14,  # Ace is highest in High Card
    Rank.JOKER: 0,
}


def get_high_card_value(rank: Rank) -> int:
    """Get the high card value for a given rank."""
    return HIGH_CARD_VALUES.get(rank, rank.rank_value)
