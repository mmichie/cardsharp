"""Spanish 21 blackjack variant."""

from typing import List, Optional, Dict
from cardsharp.common.card import Card, Rank, Suit
from cardsharp.blackjack.actor import BlackjackHand
from .base import (
    BlackjackVariant, ActionValidator, WinResolver, 
    PayoutCalculator, SpecialHand
)


class Spanish21ActionValidator(ActionValidator):
    """Spanish 21 action validation with liberal rules."""
    
    def __init__(self, rules):
        self.rules = rules
    
    def can_double_down(self, hand: BlackjackHand, num_cards: int, is_split: bool) -> bool:
        """Spanish 21: Can double on any number of cards."""
        return self.rules.allow_double_down
    
    def can_surrender(self, hand: BlackjackHand, after_double: bool, is_first_action: bool) -> bool:
        """Spanish 21: Can surrender even after doubling (double down rescue)."""
        if hand.is_split:
            return False
        return self.rules.allow_surrender
    
    def can_split_aces_again(self) -> bool:
        """Spanish 21: Can re-split aces."""
        return True
    
    def can_hit_split_aces(self) -> bool:
        """Spanish 21: Can hit split aces."""
        return True
    
    def max_hands_after_split(self) -> int:
        """Spanish 21: Usually allows up to 4 hands."""
        return 4


class Spanish21WinResolver(WinResolver):
    """Spanish 21 win resolution with player-favorable rules."""
    
    def resolve(self, player_hand: BlackjackHand, dealer_hand: BlackjackHand,
                player_blackjack: bool, dealer_blackjack: bool) -> str:
        """Spanish 21 win resolution - player 21 and blackjack always win."""
        player_value = player_hand.value()
        dealer_value = dealer_hand.value()
        
        # Spanish 21: Player blackjack ALWAYS wins (even vs dealer blackjack)
        if player_blackjack:
            return "player"
        
        # Spanish 21: Player 21 ALWAYS wins (even vs dealer 21)
        if player_value == 21:
            return "player"
        
        # Dealer blackjack wins (unless player has 21/blackjack)
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


class Spanish21PayoutCalculator(PayoutCalculator):
    """Spanish 21 payout calculation with bonus hands."""
    
    def __init__(self):
        self.blackjack_payout = 1.5
        self.insurance_payout = 2.0
    
    def calculate_payout(self, bet: float, hand: BlackjackHand, 
                        special_hand: Optional[SpecialHand],
                        is_blackjack: bool, is_insurance_win: bool) -> float:
        """Calculate Spanish 21 payouts including bonuses."""
        if is_insurance_win:
            return bet * self.insurance_payout
        
        # Special hand bonuses take precedence
        if special_hand:
            return bet * (1 + special_hand.multiplier)
        
        if is_blackjack:
            return bet * (1 + self.blackjack_payout)
        
        # Regular win pays 1:1
        return bet * 2


class Spanish21Variant(BlackjackVariant):
    """Spanish 21 rules."""
    
    def __init__(self, rules=None):
        self.rules = rules
    
    def get_name(self) -> str:
        return "Spanish 21"
    
    def create_deck(self) -> List[Card]:
        """Create a 48-card Spanish deck (no 10s)."""
        cards = []
        for suit in Suit:
            for rank in Rank:
                if rank == Rank.JOKER:
                    continue
                # Spanish 21 removes all 10s (but keeps face cards)
                if rank != Rank.TEN:
                    cards.append(Card(suit, rank))
        return cards
    
    def evaluate_special_hands(self, hand: BlackjackHand) -> Optional[SpecialHand]:
        """Evaluate Spanish 21 bonus hands."""
        cards = hand.cards
        value = hand.value()
        
        # Must be exactly 21 for most bonuses
        if value != 21:
            return None
        
        # 5-card 21
        if len(cards) == 5:
            return SpecialHand("5-card-21", 0.5, "Five Card 21")
        
        # 6-card 21
        if len(cards) == 6:
            return SpecialHand("6-card-21", 1.0, "Six Card 21")
        
        # 7+ card 21
        if len(cards) >= 7:
            return SpecialHand("7-card-21", 2.0, "Seven or More Card 21")
        
        # Check for 6-7-8 or 7-7-7
        if len(cards) == 3:
            ranks = sorted([self._get_rank_value(c.rank) for c in cards])
            
            # 6-7-8
            if ranks == [6, 7, 8]:
                suits = [c.suit for c in cards]
                if len(set(suits)) == 1:  # All same suit
                    if suits[0] == Suit.SPADES:
                        return SpecialHand("6-7-8-spades", 2.0, "6-7-8 Suited Spades")
                    else:
                        return SpecialHand("6-7-8-suited", 1.0, "6-7-8 Suited")
                else:
                    return SpecialHand("6-7-8-mixed", 0.5, "6-7-8 Mixed Suits")
            
            # 7-7-7
            if all(self._get_rank_value(c.rank) == 7 for c in cards):
                suits = [c.suit for c in cards]
                if len(set(suits)) == 1:  # All same suit
                    return SpecialHand("7-7-7-suited", 1.0, "7-7-7 Suited")
                else:
                    return SpecialHand("7-7-7-mixed", 0.5, "7-7-7 Mixed Suits")
        
        return None
    
    def _get_rank_value(self, rank: Rank) -> int:
        """Get numeric value for rank."""
        if rank == Rank.ACE:
            return 1
        elif rank in [Rank.JACK, Rank.QUEEN, Rank.KING]:
            return 10
        else:
            return rank.value
    
    def get_action_validator(self) -> ActionValidator:
        return Spanish21ActionValidator(self.rules)
    
    def get_win_resolver(self) -> WinResolver:
        return Spanish21WinResolver()
    
    def get_payout_calculator(self) -> PayoutCalculator:
        return Spanish21PayoutCalculator()
    
    def get_default_rules(self) -> Dict:
        """Return default Spanish 21 rules."""
        return {
            "blackjack_payout": 1.5,
            "dealer_hit_soft_17": True,
            "allow_split": True,
            "allow_double_down": True,
            "allow_insurance": True,
            "allow_surrender": True,
            "allow_late_surrender": True,
            "allow_double_after_split": True,
            "allow_resplitting": True,
            "dealer_peek": True,
            "max_splits": 3,
            "insurance_payout": 2.0,
            "five_card_charlie": False,  # Spanish 21 uses 5-card 21 bonus instead
        }