"""
Test support classes for blackjack engine validation.

This module provides enhanced game components that record actions and outcomes
for test validation purposes.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

from .actor import Player, Dealer
from .hand import BlackjackHand
from .strategy import BasicStrategy
from ..common.card import Card


class GameOutcome(Enum):
    """Detailed game outcome types."""
    PLAYER_BLACKJACK = "player_blackjack"
    DEALER_BLACKJACK = "dealer_blackjack"
    BOTH_BLACKJACK = "both_blackjack"
    PLAYER_BUST = "player_bust"
    DEALER_BUST = "dealer_bust"
    PLAYER_HIGHER = "player_higher"
    DEALER_HIGHER = "dealer_higher"
    PUSH = "push"
    SURRENDER = "surrender"


@dataclass
class ActionRecord:
    """Record of a single action taken during play."""
    hand_index: int
    hand_value: int
    hand_cards: List[Card]
    is_soft: bool
    is_pair: bool
    dealer_upcard: Card
    action_taken: str  # 'hit', 'stand', 'double', 'split', 'surrender'
    card_received: Optional[Card] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for easy inspection."""
        return {
            'hand_index': self.hand_index,
            'hand_value': self.hand_value,
            'hand_cards': [str(c) for c in self.hand_cards],
            'is_soft': self.is_soft,
            'is_pair': self.is_pair,
            'dealer_upcard': str(self.dealer_upcard),
            'action': self.action_taken,
            'card_received': str(self.card_received) if self.card_received else None
        }


@dataclass
class HandOutcome:
    """Outcome for a single hand."""
    hand_index: int
    final_value: int
    final_cards: List[Card]
    is_blackjack: bool
    is_bust: bool
    outcome: GameOutcome
    bet: int
    payout: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'hand_index': self.hand_index,
            'final_value': self.final_value,
            'final_cards': [str(c) for c in self.final_cards],
            'is_blackjack': self.is_blackjack,
            'is_bust': self.is_bust,
            'outcome': self.outcome.value,
            'bet': self.bet,
            'payout': self.payout
        }


@dataclass
class GameRecord:
    """Complete record of a game for validation."""
    player_actions: List[ActionRecord] = field(default_factory=list)
    hand_outcomes: List[HandOutcome] = field(default_factory=list)
    dealer_cards: List[Card] = field(default_factory=list)
    dealer_value: int = 0
    dealer_blackjack: bool = False
    dealer_bust: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entire game record to dictionary."""
        return {
            'player_actions': [a.to_dict() for a in self.player_actions],
            'hand_outcomes': [h.to_dict() for h in self.hand_outcomes],
            'dealer_cards': [str(c) for c in self.dealer_cards],
            'dealer_value': self.dealer_value,
            'dealer_blackjack': self.dealer_blackjack,
            'dealer_bust': self.dealer_bust
        }


class RecordingStrategy(BasicStrategy):
    """Strategy wrapper that records all decisions."""
    
    def __init__(self):
        super().__init__()
        self.action_records: List[ActionRecord] = []
        self.current_dealer_upcard: Optional[Card] = None
    
    def decide_action(self, player, dealer_up_card: Card, game=None):
        """Record the decision before returning it."""
        # Store dealer upcard for recording
        self.current_dealer_upcard = dealer_up_card
        
        # Get the actual decision from basic strategy
        action = super().decide_action(player, dealer_up_card, game)
        
        # Record the decision
        hand = player.current_hand
        record = ActionRecord(
            hand_index=player.current_hand_index,
            hand_value=hand.value(),
            hand_cards=hand.cards.copy(),
            is_soft=hand.is_soft,
            is_pair=len(hand.cards) == 2 and hand.cards[0].rank == hand.cards[1].rank,
            dealer_upcard=dealer_up_card,
            action_taken=action.value.lower()  # Convert enum to string
        )
        self.action_records.append(record)
        
        return action


class TestPlayer(Player):
    """Enhanced player that records all actions and outcomes."""
    
    def __init__(self, name: str, io_interface, strategy=None):
        # Use recording strategy by default
        if strategy is None:
            strategy = RecordingStrategy()
        elif not isinstance(strategy, RecordingStrategy):
            # Wrap provided strategy
            recording_strategy = RecordingStrategy()
            recording_strategy.__class__ = type(
                'Recording' + strategy.__class__.__name__,
                (RecordingStrategy, strategy.__class__),
                {}
            )
            strategy = recording_strategy
            
        super().__init__(name, io_interface, strategy)
        self.game_record = GameRecord()
        self._last_card_count = {}  # Track cards to detect hits
    
    def add_card(self, card: Card):
        """Override to track cards received."""
        hand_idx = self.current_hand_index
        
        # Track that this hand received a card
        if hand_idx not in self._last_card_count:
            self._last_card_count[hand_idx] = 0
        self._last_card_count[hand_idx] = len(self.hands[hand_idx].cards)
        
        # Call parent
        super().add_card(card)
        
        # Update the last action record with the card received
        if isinstance(self.strategy, RecordingStrategy) and self.strategy.action_records:
            last_record = self.strategy.action_records[-1]
            if last_record.hand_index == hand_idx and last_record.card_received is None:
                last_record.card_received = card
    
    def finalize_outcomes(self, dealer_hand: BlackjackHand, dealer_value: int):
        """Call this after the game to record final outcomes."""
        # Record dealer info
        self.game_record.dealer_cards = dealer_hand.cards.copy()
        self.game_record.dealer_value = dealer_value
        self.game_record.dealer_blackjack = dealer_hand.is_blackjack
        self.game_record.dealer_bust = dealer_value > 21
        
        # Record each hand outcome
        for idx, hand in enumerate(self.hands):
            hand_value = hand.value()
            is_blackjack = hand.is_blackjack
            is_bust = hand_value > 21
            
            # Determine outcome
            # Check if this hand was surrendered
            is_surrender = False
            if isinstance(self.strategy, RecordingStrategy):
                # Check if any action for this hand was surrender
                for action in self.strategy.action_records:
                    if action.hand_index == idx and action.action_taken == 'surrender':
                        is_surrender = True
                        break
            
            if is_surrender:
                outcome = GameOutcome.SURRENDER
            elif is_blackjack and self.game_record.dealer_blackjack:
                outcome = GameOutcome.BOTH_BLACKJACK
            elif is_blackjack and not self.game_record.dealer_blackjack:
                outcome = GameOutcome.PLAYER_BLACKJACK
            elif not is_blackjack and self.game_record.dealer_blackjack:
                outcome = GameOutcome.DEALER_BLACKJACK
            elif is_bust:
                outcome = GameOutcome.PLAYER_BUST
            elif self.game_record.dealer_bust:
                outcome = GameOutcome.DEALER_BUST
            elif hand_value > dealer_value:
                outcome = GameOutcome.PLAYER_HIGHER
            elif dealer_value > hand_value:
                outcome = GameOutcome.DEALER_HIGHER
            else:
                outcome = GameOutcome.PUSH
            
            # Calculate payout (simplified)
            bet = self.bets[idx] if idx < len(self.bets) else 10
            if outcome == GameOutcome.PLAYER_BLACKJACK:
                payout = bet * 1.5
            elif outcome in [GameOutcome.PLAYER_HIGHER, GameOutcome.DEALER_BUST]:
                payout = bet
            elif outcome == GameOutcome.PUSH:
                payout = 0
            else:
                payout = -bet
            
            hand_outcome = HandOutcome(
                hand_index=idx,
                final_value=hand_value,
                final_cards=hand.cards.copy(),
                is_blackjack=is_blackjack,
                is_bust=is_bust,
                outcome=outcome,
                bet=bet,
                payout=payout
            )
            
            self.game_record.hand_outcomes.append(hand_outcome)
        
        # Copy action records from strategy
        if isinstance(self.strategy, RecordingStrategy):
            self.game_record.player_actions = self.strategy.action_records.copy()


class TestDealer(Dealer):
    """Enhanced dealer for testing."""
    
    def __init__(self, name: str, io_interface):
        super().__init__(name, io_interface)
        self.final_value = 0
        self.hit_count = 0
    
    def add_card(self, card: Card):
        """Track cards added."""
        super().add_card(card)
        self.hit_count = len(self.hands[0].cards) - 2  # Initial 2 cards don't count


class TestableBlackjackGame:
    """Wrapper to make BlackjackGame more testable."""
    
    def __init__(self, game):
        self.game = game
        self.test_player = None
        self.test_dealer = None
    
    def add_test_player(self, name: str = "TestPlayer") -> TestPlayer:
        """Add a test player to the game."""
        io = self.game.io_interface
        self.test_player = TestPlayer(name, io)
        self.game.add_player(self.test_player)
        return self.test_player
    
    def replace_dealer(self):
        """Replace dealer with test dealer."""
        self.test_dealer = TestDealer("Dealer", self.game.io_interface)
        self.game.dealer = self.test_dealer
    
    def play_round(self):
        """Play a round and finalize outcomes."""
        self.game.play_round()
        
        # Finalize player outcomes
        if self.test_player and self.game.dealer.hands:
            dealer_hand = self.game.dealer.hands[0]
            dealer_value = dealer_hand.value()
            self.test_player.finalize_outcomes(dealer_hand, dealer_value)
    
    def get_game_record(self) -> Optional[GameRecord]:
        """Get the complete game record."""
        if self.test_player:
            return self.test_player.game_record
        return None