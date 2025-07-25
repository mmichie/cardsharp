"""Classic blackjack variant."""

from typing import List, Optional, Dict
from cardsharp.common.card import Card, Rank, Suit
from cardsharp.common.deck import Deck
from cardsharp.blackjack.actor import BlackjackHand
from .base import (
    BlackjackVariant, ActionValidator, WinResolver, 
    PayoutCalculator, SpecialHand
)


class ClassicActionValidator(ActionValidator):
    """Classic blackjack action validation."""
    
    def __init__(self, rules):
        self.rules = rules
    
    def can_double_down(self, hand: BlackjackHand, num_cards: int, is_split: bool) -> bool:
        """Classic: Can only double on 2 cards."""
        if num_cards != 2:
            return False
        if is_split and not self.rules.allow_double_after_split:
            return False
        return self.rules.allow_double_down
    
    def can_surrender(self, hand: BlackjackHand, after_double: bool, is_first_action: bool) -> bool:
        """Classic: Can only surrender as first action, not after double."""
        if after_double:
            return False
        if not is_first_action:
            return False
        if hand.is_split:
            return False
        return self.rules.allow_surrender
    
    def can_split_aces_again(self) -> bool:
        """Classic: Cannot re-split aces."""
        return False
    
    def can_hit_split_aces(self) -> bool:
        """Classic: Cannot hit split aces."""
        return False
    
    def max_hands_after_split(self) -> int:
        """Classic: Use rules max_splits."""
        return self.rules.max_splits + 1


class ClassicWinResolver(WinResolver):
    """Classic blackjack win resolution."""
    
    def resolve(self, player_hand: BlackjackHand, dealer_hand: BlackjackHand,
                player_blackjack: bool, dealer_blackjack: bool) -> str:
        """Standard blackjack win resolution."""
        player_value = player_hand.value()
        dealer_value = dealer_hand.value()
        
        # Both blackjack = push
        if player_blackjack and dealer_blackjack:
            return "draw"
        
        # Player blackjack wins
        if player_blackjack:
            return "player"
        
        # Dealer blackjack wins
        if dealer_blackjack:
            return "dealer"
        
        # Player bust
        if player_value > 21:
            return "dealer"
        
        # Dealer bust
        if dealer_value > 21:
            return "player"
        
        # Compare values
        if player_value > dealer_value:
            return "player"
        elif dealer_value > player_value:
            return "dealer"
        else:
            return "draw"


class ClassicPayoutCalculator(PayoutCalculator):
    """Classic blackjack payout calculation."""
    
    def __init__(self, blackjack_payout: float = 1.5, insurance_payout: float = 2.0):
        self.blackjack_payout = blackjack_payout
        self.insurance_payout = insurance_payout
    
    def calculate_payout(self, bet: float, hand: BlackjackHand, 
                        special_hand: Optional[SpecialHand],
                        is_blackjack: bool, is_insurance_win: bool) -> float:
        """Calculate classic blackjack payouts."""
        if is_insurance_win:
            return bet * self.insurance_payout
        
        if is_blackjack:
            return bet * (1 + self.blackjack_payout)
        
        # Regular win pays 1:1
        return bet * 2


class ClassicBlackjackVariant(BlackjackVariant):
    """Classic blackjack rules."""
    
    def __init__(self, rules=None):
        self.rules = rules
    
    def get_name(self) -> str:
        return "Classic Blackjack"
    
    def create_deck(self) -> List[Card]:
        """Create a standard 52-card deck."""
        deck = Deck()
        return deck.cards
    
    def evaluate_special_hands(self, hand: BlackjackHand) -> Optional[SpecialHand]:
        """Classic blackjack has no special hands beyond blackjack."""
        return None
    
    def get_action_validator(self) -> ActionValidator:
        return ClassicActionValidator(self.rules)
    
    def get_win_resolver(self) -> WinResolver:
        return ClassicWinResolver()
    
    def get_payout_calculator(self) -> PayoutCalculator:
        return ClassicPayoutCalculator(
            self.rules.blackjack_payout if self.rules else 1.5,
            self.rules.insurance_payout if self.rules else 2.0
        )
    
    def get_default_rules(self) -> Dict:
        """Return default classic blackjack rules."""
        return {
            "blackjack_payout": 1.5,
            "dealer_hit_soft_17": True,
            "allow_split": True,
            "allow_double_down": True,
            "allow_insurance": True,
            "allow_surrender": True,
            "allow_late_surrender": False,
            "allow_double_after_split": True,
            "allow_resplitting": True,
            "dealer_peek": True,
            "max_splits": 3,
            "insurance_payout": 2.0,
        }