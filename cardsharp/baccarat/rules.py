"""
Baccarat rules and drawing logic.

Baccarat has fixed drawing rules - no player decisions after betting.
The rules determine when Player and Banker draw a third card.
"""

from dataclasses import dataclass


@dataclass
class BaccaratRules:
    """
    Configuration for Baccarat game rules.

    Attributes:
        banker_commission: Commission on Banker wins (typically 0.05 = 5%)
        tie_payout: Payout ratio for Tie bets (typically 8.0 = 8:1)
        num_decks: Number of decks in the shoe
        penetration: Shoe penetration before reshuffling
    """
    banker_commission: float = 0.05  # 5% commission on Banker wins
    tie_payout: float = 8.0  # 8:1 payout for ties
    num_decks: int = 8  # Standard is 8 decks
    penetration: float = 0.80  # Deal 80% before reshuffling


def player_draws_third_card(player_value: int) -> bool:
    """
    Determine if Player draws a third card.

    Player drawing rules:
    - 0-5: Draw
    - 6-7: Stand
    - 8-9: Natural (no draw)

    Args:
        player_value: Player's two-card total

    Returns:
        True if Player should draw, False otherwise
    """
    return player_value <= 5


def banker_draws_third_card(banker_value: int, player_drew: bool, player_third_card: int) -> bool:
    """
    Determine if Banker draws a third card.

    Banker drawing rules are complex and depend on:
    1. Banker's two-card total
    2. Whether Player drew a third card
    3. Value of Player's third card (if drawn)

    Rules:
    - If Player didn't draw: Banker draws on 0-5, stands on 6-7
    - If Player drew:
      - Banker 0-2: Always draw
      - Banker 3: Draw unless Player's 3rd card is 8
      - Banker 4: Draw if Player's 3rd card is 2-7
      - Banker 5: Draw if Player's 3rd card is 4-7
      - Banker 6: Draw if Player's 3rd card is 6-7
      - Banker 7: Stand
      - Banker 8-9: Natural (no draw)

    Args:
        banker_value: Banker's two-card total
        player_drew: Whether Player drew a third card
        player_third_card: Value of Player's third card (0-9, or -1 if no third card)

    Returns:
        True if Banker should draw, False otherwise
    """
    # If Player didn't draw, Banker uses simple rule
    if not player_drew:
        return banker_value <= 5

    # Banker draws based on complex table
    if banker_value <= 2:
        return True
    elif banker_value == 3:
        return player_third_card != 8
    elif banker_value == 4:
        return player_third_card in [2, 3, 4, 5, 6, 7]
    elif banker_value == 5:
        return player_third_card in [4, 5, 6, 7]
    elif banker_value == 6:
        return player_third_card in [6, 7]
    else:
        return False
