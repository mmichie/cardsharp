"""
Baccarat game engine.

Implements the complete Baccarat game logic including dealing, drawing rules,
and outcome determination.
"""

from enum import Enum
from typing import Optional
from dataclasses import dataclass

from cardsharp.common.shoe import Shoe
from cardsharp.baccarat.hand import BaccaratHand
from cardsharp.baccarat.rules import BaccaratRules, player_draws_third_card, banker_draws_third_card


class BetType(Enum):
    """Types of bets in Baccarat."""
    PLAYER = "player"
    BANKER = "banker"
    TIE = "tie"


class Outcome(Enum):
    """Possible outcomes of a Baccarat round."""
    PLAYER_WIN = "player_win"
    BANKER_WIN = "banker_win"
    TIE = "tie"


@dataclass
class BaccaratResult:
    """Result of a Baccarat round."""
    outcome: Outcome
    player_value: int
    banker_value: int
    player_cards: int  # Number of cards in Player hand
    banker_cards: int  # Number of cards in Banker hand
    player_natural: bool
    banker_natural: bool


class BaccaratGame:
    """
    Main Baccarat game engine.

    Handles dealing, drawing rules, and outcome determination.
    """

    def __init__(self, rules: Optional[BaccaratRules] = None, shoe: Optional[Shoe] = None):
        """
        Initialize a Baccarat game.

        Args:
            rules: Game rules configuration
            shoe: Card shoe (will create default if not provided)
        """
        self.rules = rules if rules else BaccaratRules()

        if shoe:
            self.shoe = shoe
        else:
            self.shoe = Shoe(
                num_decks=self.rules.num_decks,
                penetration=self.rules.penetration
            )

        self.player_hand = BaccaratHand()
        self.banker_hand = BaccaratHand()

        # Statistics
        self.rounds_played = 0
        self.player_wins = 0
        self.banker_wins = 0
        self.ties = 0
        self.naturals = 0

    def reset_hands(self):
        """Reset hands for a new round."""
        self.player_hand = BaccaratHand()
        self.banker_hand = BaccaratHand()

    def deal_initial_cards(self):
        """
        Deal initial four cards (2 to Player, 2 to Banker).

        Order: Player, Banker, Player, Banker
        """
        self.player_hand.add_card(self.shoe.deal())
        self.banker_hand.add_card(self.shoe.deal())
        self.player_hand.add_card(self.shoe.deal())
        self.banker_hand.add_card(self.shoe.deal())

    def apply_drawing_rules(self):
        """
        Apply Baccarat drawing rules to determine if third cards are needed.

        This follows the standard Baccarat drawing rules:
        1. Check for naturals (8 or 9) - no more cards dealt
        2. Determine if Player draws third card
        3. Determine if Banker draws third card (depends on Player's action)
        """
        # Check for naturals (8 or 9 on first two cards)
        if self.player_hand.is_natural() or self.banker_hand.is_natural():
            if self.player_hand.is_natural() or self.banker_hand.is_natural():
                self.naturals += 1
            return

        # Determine if Player draws
        player_value = self.player_hand.value()
        player_drew = False
        player_third_value = -1

        if player_draws_third_card(player_value):
            card = self.shoe.deal()
            self.player_hand.add_card(card)
            player_drew = True
            player_third_value = self.player_hand.third_card_value()

        # Determine if Banker draws (depends on Player's third card)
        banker_value = self.banker_hand.value()
        if banker_draws_third_card(banker_value, player_drew, player_third_value):
            self.banker_hand.add_card(self.shoe.deal())

    def determine_outcome(self) -> Outcome:
        """
        Determine the outcome of the round.

        Returns:
            Outcome enum value
        """
        player_value = self.player_hand.value()
        banker_value = self.banker_hand.value()

        if player_value > banker_value:
            return Outcome.PLAYER_WIN
        elif banker_value > player_value:
            return Outcome.BANKER_WIN
        else:
            return Outcome.TIE

    def calculate_payout(self, bet_type: BetType, bet_amount: float, outcome: Outcome) -> float:
        """
        Calculate the payout for a bet.

        Payouts:
        - Player bet: 1:1
        - Banker bet: 1:1 minus 5% commission
        - Tie bet: 8:1 (or configured ratio)

        Args:
            bet_type: Type of bet placed
            bet_amount: Amount bet
            outcome: Outcome of the round

        Returns:
            Net win/loss (positive = win, negative = loss)
        """
        if bet_type == BetType.PLAYER:
            if outcome == Outcome.PLAYER_WIN:
                return bet_amount  # Win 1:1
            elif outcome == Outcome.TIE:
                return 0  # Push
            else:
                return -bet_amount  # Lose bet

        elif bet_type == BetType.BANKER:
            if outcome == Outcome.BANKER_WIN:
                # Win 1:1 minus commission
                winnings = bet_amount * (1 - self.rules.banker_commission)
                return winnings
            elif outcome == Outcome.TIE:
                return 0  # Push
            else:
                return -bet_amount  # Lose bet

        elif bet_type == BetType.TIE:
            if outcome == Outcome.TIE:
                return bet_amount * self.rules.tie_payout  # Win 8:1
            else:
                return -bet_amount  # Lose bet

        return 0

    def play_round(self, bet_type: BetType = BetType.BANKER, bet_amount: float = 10) -> tuple[BaccaratResult, float]:
        """
        Play a complete round of Baccarat.

        Args:
            bet_type: Type of bet (Player, Banker, or Tie)
            bet_amount: Amount to bet

        Returns:
            Tuple of (BaccaratResult, payout)
        """
        # Reset for new round
        self.reset_hands()

        # Deal initial cards
        self.deal_initial_cards()

        # Apply drawing rules
        self.apply_drawing_rules()

        # Determine outcome
        outcome = self.determine_outcome()

        # Update statistics
        self.rounds_played += 1
        if outcome == Outcome.PLAYER_WIN:
            self.player_wins += 1
        elif outcome == Outcome.BANKER_WIN:
            self.banker_wins += 1
        else:
            self.ties += 1

        # Calculate payout
        payout = self.calculate_payout(bet_type, bet_amount, outcome)

        # Create result
        result = BaccaratResult(
            outcome=outcome,
            player_value=self.player_hand.value(),
            banker_value=self.banker_hand.value(),
            player_cards=self.player_hand.card_count(),
            banker_cards=self.banker_hand.card_count(),
            player_natural=self.player_hand.is_natural(),
            banker_natural=self.banker_hand.is_natural()
        )

        return result, payout

    def get_statistics(self) -> dict:
        """
        Get game statistics.

        Returns:
            Dictionary with statistics
        """
        total_decisive = self.player_wins + self.banker_wins

        return {
            "rounds_played": self.rounds_played,
            "player_wins": self.player_wins,
            "banker_wins": self.banker_wins,
            "ties": self.ties,
            "naturals": self.naturals,
            "player_win_rate": self.player_wins / total_decisive if total_decisive > 0 else 0,
            "banker_win_rate": self.banker_wins / total_decisive if total_decisive > 0 else 0,
            "tie_rate": self.ties / self.rounds_played if self.rounds_played > 0 else 0,
        }

    def __str__(self) -> str:
        """String representation showing current game state."""
        return f"Baccarat Game: {self.rounds_played} rounds played"

    def __repr__(self) -> str:
        """Detailed representation of game state."""
        return f"BaccaratGame(rounds={self.rounds_played}, P:{self.player_wins}, B:{self.banker_wins}, T:{self.ties})"
