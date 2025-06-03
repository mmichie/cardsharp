"""War-specific constants and value mappings."""

from cardsharp.common.card import Rank

# War-specific card values (Ace is highest)
WAR_VALUES = {
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
    Rank.ACE: 14,  # Ace is highest in War
    Rank.JOKER: 0,
}


def get_war_value(rank: Rank) -> int:
    """Get the war value for a given rank."""
    return WAR_VALUES.get(rank, rank.rank_value)
