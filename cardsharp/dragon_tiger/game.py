"""
Dragon Tiger game engine.

Dragon Tiger is one of the simplest casino card games:
- One card dealt to Dragon, one to Tiger
- Highest card wins (Ace=1 is lowest, King=13 is highest)
- Ties result in a push or half-loss depending on rules
"""

from enum import Enum
from typing import Optional
from dataclasses import dataclass

from cardsharp.common.shoe import Shoe
from cardsharp.common.card import Card, Rank


class BetType(Enum):
    """Types of bets in Dragon Tiger."""
    DRAGON = "dragon"
    TIGER = "tiger"
    TIE = "tie"


class Outcome(Enum):
    """Possible outcomes of a Dragon Tiger round."""
    DRAGON_WIN = "dragon_win"
    TIGER_WIN = "tiger_win"
    TIE = "tie"


@dataclass
class DragonTigerResult:
    """Result of a Dragon Tiger round."""
    outcome: Outcome
    dragon_card: Card
    tiger_card: Card
    dragon_value: int
    tiger_value: int


class DragonTigerRules:
    """Configuration for Dragon Tiger game rules."""

    def __init__(
        self,
        num_decks: int = 8,
        penetration: float = 0.75,
        tie_payout: float = 8.0,  # 8:1 is standard, some casinos offer 11:1
        tie_push: bool = False,  # If True, Dragon/Tiger bets push on tie; if False, they lose
    ):
        """
        Initialize Dragon Tiger rules.

        Args:
            num_decks: Number of decks in shoe
            penetration: When to reshuffle (0.75 = reshuffle at 75% dealt)
            tie_payout: Payout ratio for Tie bets (8:1 or 11:1 typical)
            tie_push: Whether Dragon/Tiger bets push (return stake) on tie, or lose
        """
        self.num_decks = num_decks
        self.penetration = penetration
        self.tie_payout = tie_payout
        self.tie_push = tie_push


def card_value(card: Card) -> int:
    """
    Get the value of a card for Dragon Tiger.

    Ace = 1 (lowest)
    2-10 = face value
    Jack = 11, Queen = 12, King = 13 (highest)

    Args:
        card: The card to evaluate

    Returns:
        Integer value 1-13
    """
    if card.rank == Rank.ACE:
        return 1
    elif card.rank == Rank.TWO:
        return 2
    elif card.rank == Rank.THREE:
        return 3
    elif card.rank == Rank.FOUR:
        return 4
    elif card.rank == Rank.FIVE:
        return 5
    elif card.rank == Rank.SIX:
        return 6
    elif card.rank == Rank.SEVEN:
        return 7
    elif card.rank == Rank.EIGHT:
        return 8
    elif card.rank == Rank.NINE:
        return 9
    elif card.rank == Rank.TEN:
        return 10
    elif card.rank == Rank.JACK:
        return 11
    elif card.rank == Rank.QUEEN:
        return 12
    elif card.rank == Rank.KING:
        return 13
    return 0  # Should never reach here


class DragonTigerGame:
    """
    Main Dragon Tiger game engine.

    Handles dealing, outcome determination, and payouts.
    """

    def __init__(self, rules: Optional[DragonTigerRules] = None, shoe: Optional[Shoe] = None):
        """
        Initialize a Dragon Tiger game.

        Args:
            rules: Game rules configuration
            shoe: Card shoe (will create default if not provided)
        """
        self.rules = rules if rules else DragonTigerRules()

        if shoe:
            self.shoe = shoe
        else:
            self.shoe = Shoe(
                num_decks=self.rules.num_decks,
                penetration=self.rules.penetration
            )

        # Statistics
        self.rounds_played = 0
        self.dragon_wins = 0
        self.tiger_wins = 0
        self.ties = 0

    def determine_outcome(self, dragon_card: Card, tiger_card: Card) -> Outcome:
        """
        Determine the outcome of the round.

        Args:
            dragon_card: Card dealt to Dragon
            tiger_card: Card dealt to Tiger

        Returns:
            Outcome enum value
        """
        dragon_val = card_value(dragon_card)
        tiger_val = card_value(tiger_card)

        if dragon_val > tiger_val:
            return Outcome.DRAGON_WIN
        elif tiger_val > dragon_val:
            return Outcome.TIGER_WIN
        else:
            return Outcome.TIE

    def calculate_payout(self, bet_type: BetType, bet_amount: float, outcome: Outcome) -> float:
        """
        Calculate the payout for a bet.

        Payouts:
        - Dragon bet on Dragon win: 1:1
        - Tiger bet on Tiger win: 1:1
        - Tie bet on Tie: 8:1 (or configured ratio)
        - Dragon/Tiger bet on Tie: lose all (or push if tie_push=True)

        Args:
            bet_type: Type of bet placed
            bet_amount: Amount bet
            outcome: Outcome of the round

        Returns:
            Net win/loss (positive = win, negative = loss)
        """
        if bet_type == BetType.DRAGON:
            if outcome == Outcome.DRAGON_WIN:
                return bet_amount  # Win 1:1
            elif outcome == Outcome.TIE:
                return 0 if self.rules.tie_push else -bet_amount  # Push or lose
            else:
                return -bet_amount  # Lose

        elif bet_type == BetType.TIGER:
            if outcome == Outcome.TIGER_WIN:
                return bet_amount  # Win 1:1
            elif outcome == Outcome.TIE:
                return 0 if self.rules.tie_push else -bet_amount  # Push or lose
            else:
                return -bet_amount  # Lose

        elif bet_type == BetType.TIE:
            if outcome == Outcome.TIE:
                return bet_amount * self.rules.tie_payout  # Win 8:1 or 11:1
            else:
                return -bet_amount  # Lose

        return 0

    def play_round(self, bet_type: BetType = BetType.DRAGON, bet_amount: float = 10) -> tuple[DragonTigerResult, float]:
        """
        Play a complete round of Dragon Tiger.

        Args:
            bet_type: Type of bet (Dragon, Tiger, or Tie)
            bet_amount: Amount to bet

        Returns:
            Tuple of (DragonTigerResult, payout)
        """
        # Deal cards
        dragon_card = self.shoe.deal()
        tiger_card = self.shoe.deal()

        # Determine outcome
        outcome = self.determine_outcome(dragon_card, tiger_card)

        # Update statistics
        self.rounds_played += 1
        if outcome == Outcome.DRAGON_WIN:
            self.dragon_wins += 1
        elif outcome == Outcome.TIGER_WIN:
            self.tiger_wins += 1
        else:
            self.ties += 1

        # Calculate payout
        payout = self.calculate_payout(bet_type, bet_amount, outcome)

        # Create result
        result = DragonTigerResult(
            outcome=outcome,
            dragon_card=dragon_card,
            tiger_card=tiger_card,
            dragon_value=card_value(dragon_card),
            tiger_value=card_value(tiger_card)
        )

        return result, payout

    def get_statistics(self) -> dict:
        """
        Get game statistics.

        Returns:
            Dictionary with statistics
        """
        total_decisive = self.dragon_wins + self.tiger_wins

        return {
            "rounds_played": self.rounds_played,
            "dragon_wins": self.dragon_wins,
            "tiger_wins": self.tiger_wins,
            "ties": self.ties,
            "dragon_win_rate": self.dragon_wins / total_decisive if total_decisive > 0 else 0,
            "tiger_win_rate": self.tiger_wins / total_decisive if total_decisive > 0 else 0,
            "tie_rate": self.ties / self.rounds_played if self.rounds_played > 0 else 0,
        }

    def __str__(self) -> str:
        """String representation showing current game state."""
        return f"Dragon Tiger Game: {self.rounds_played} rounds played"

    def __repr__(self) -> str:
        """Detailed representation of game state."""
        return f"DragonTigerGame(rounds={self.rounds_played}, D:{self.dragon_wins}, T:{self.tiger_wins}, Tie:{self.ties})"
