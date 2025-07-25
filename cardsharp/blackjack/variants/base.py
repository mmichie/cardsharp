"""Base class for blackjack variants."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Tuple
from cardsharp.common.card import Card
from cardsharp.blackjack.actor import BlackjackHand


class SpecialHand:
    """Represents a special hand with bonus payout."""
    def __init__(self, name: str, multiplier: float, description: str):
        self.name = name
        self.multiplier = multiplier
        self.description = description


class ActionValidator(ABC):
    """Validates available actions based on variant rules."""
    
    @abstractmethod
    def can_double_down(self, hand: BlackjackHand, num_cards: int, is_split: bool) -> bool:
        """Check if double down is allowed."""
        pass
    
    @abstractmethod
    def can_surrender(self, hand: BlackjackHand, after_double: bool, is_first_action: bool) -> bool:
        """Check if surrender is allowed."""
        pass
    
    @abstractmethod
    def can_split_aces_again(self) -> bool:
        """Check if aces can be re-split."""
        pass
    
    @abstractmethod
    def can_hit_split_aces(self) -> bool:
        """Check if split aces can be hit."""
        pass
    
    @abstractmethod
    def max_hands_after_split(self) -> int:
        """Maximum number of hands allowed after splitting."""
        pass


class WinResolver(ABC):
    """Resolves winner based on variant rules."""
    
    @abstractmethod
    def resolve(self, player_hand: BlackjackHand, dealer_hand: BlackjackHand, 
                player_blackjack: bool, dealer_blackjack: bool) -> str:
        """Determine the winner. Returns 'player', 'dealer', or 'draw'."""
        pass


class PayoutCalculator(ABC):
    """Calculates payouts based on variant rules."""
    
    @abstractmethod
    def calculate_payout(self, bet: float, hand: BlackjackHand, 
                        special_hand: Optional[SpecialHand],
                        is_blackjack: bool, is_insurance_win: bool) -> float:
        """Calculate the payout for a winning hand."""
        pass


class BlackjackVariant(ABC):
    """Base class for all blackjack variants."""
    
    @abstractmethod
    def get_name(self) -> str:
        """Return the variant name."""
        pass
    
    @abstractmethod
    def create_deck(self) -> List[Card]:
        """Create a deck specific to this variant."""
        pass
    
    @abstractmethod
    def evaluate_special_hands(self, hand: BlackjackHand) -> Optional[SpecialHand]:
        """Check for variant-specific special hands."""
        pass
    
    @abstractmethod
    def get_action_validator(self) -> ActionValidator:
        """Return the action validator for this variant."""
        pass
    
    @abstractmethod
    def get_win_resolver(self) -> WinResolver:
        """Return the win resolver for this variant."""
        pass
    
    @abstractmethod
    def get_payout_calculator(self) -> PayoutCalculator:
        """Return the payout calculator for this variant."""
        pass
    
    @abstractmethod
    def get_default_rules(self) -> Dict:
        """Return default rule settings for this variant."""
        pass