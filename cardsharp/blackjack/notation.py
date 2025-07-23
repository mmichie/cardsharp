"""
Blackjack Notation System for Game Recording and Testing

Format Specification:
--------------------
CARDS: Rank + Suit (As, Kh, Tc, 9d, etc.)
  Ranks: A,2-9,T,J,Q,K
  Suits: s(♠), h(♥), d(♦), c(♣)

ACTIONS: 
  H = Hit
  S = Stand  
  D = Double
  P = Split (creates P1, P2, etc.)
  R = Surrender
  I = Insurance

GAME NOTATION:
  Player|Dealer|Actions|Result

EXAMPLE:
  As,Tc|Kh,9d|S|BJ-W  (Blackjack win)
  8h,8d|Th|P:H(3s)S,H(As)S|20,19-L  (Split, both hands lose)

TEST NOTATION:
  @deck: [ordered list of cards to deal]
  @rules: {rule overrides}
  @expect: {expected outcomes}
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Union
from enum import Enum
import re


class Action(Enum):
    HIT = "H"
    STAND = "S"
    DOUBLE = "D"
    SPLIT = "P"
    SURRENDER = "R"
    INSURANCE = "I"


class Outcome(Enum):
    WIN = "W"
    LOSS = "L"
    PUSH = "P"
    BLACKJACK_WIN = "BJ-W"
    SURRENDER_LOSS = "R-L"


@dataclass
class Card:
    """Card representation."""
    rank: str  # A,2-9,T,J,Q,K
    suit: str  # s,h,d,c
    
    @property
    def value(self) -> int:
        """Blackjack value of card."""
        if self.rank == 'A':
            return 1
        elif self.rank in ['T', 'J', 'Q', 'K']:
            return 10
        else:
            return int(self.rank)
    
    @classmethod
    def from_str(cls, s: str) -> 'Card':
        """Parse 'As' -> Card(A, s)"""
        if len(s) != 2:
            raise ValueError(f"Invalid card notation: {s}")
        return cls(rank=s[0], suit=s[1])
    
    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


@dataclass 
class Hand:
    """Player hand with actions taken."""
    initial_cards: List[Card]
    actions: List[Tuple[Action, Optional[Card]]]  # (action, card_received)
    final_value: Optional[int] = None
    outcome: Optional[Outcome] = None
    bet: int = 10
    is_split: bool = False
    
    def to_notation(self) -> str:
        """Convert hand to notation string."""
        cards = ','.join(str(c) for c in self.initial_cards)
        action_strs = []
        
        for action, card in self.actions:
            if action == Action.HIT and card:
                action_strs.append(f"H({card})")
            else:
                action_strs.append(action.value)
        
        actions = ''.join(action_strs)
        return f"{cards}:{actions}"


@dataclass
class GameRecord:
    """Complete game record."""
    player_hands: List[Hand]
    dealer_cards: List[Card]
    dealer_value: int
    
    def to_notation(self) -> str:
        """Convert game to notation string."""
        # Player hands
        if len(self.player_hands) == 1:
            player_str = self.player_hands[0].to_notation()
        else:
            # Split hands
            hand_strs = [h.to_notation() for h in self.player_hands]
            player_str = "P:" + ",".join(hand_strs)
        
        # Dealer
        dealer_str = ','.join(str(c) for c in self.dealer_cards[:2])
        if len(self.dealer_cards) > 2:
            # Show hits
            hits = [str(c) for c in self.dealer_cards[2:]]
            dealer_str += f":H({''.join(hits)})"
        
        # Outcomes
        outcomes = []
        for hand in self.player_hands:
            if hand.final_value:
                outcomes.append(str(hand.final_value))
            if hand.outcome:
                outcomes.append(hand.outcome.value)
        
        return f"{player_str}|{dealer_str}|{','.join(outcomes)}"


class BlackjackNotation:
    """Parser and formatter for blackjack notation."""
    
    @staticmethod
    def parse_card_list(s: str) -> List[Card]:
        """Parse 'As,Tc,5h' -> [Card(A,s), Card(T,c), Card(5,h)]"""
        return [Card.from_str(c.strip()) for c in s.split(',')]
    
    @staticmethod
    def parse_action_sequence(s: str) -> List[Tuple[Action, Optional[Card]]]:
        """Parse 'H(5c)DH(Ks)S' -> [(HIT, Card(5,c)), (DOUBLE, None), ...]"""
        actions = []
        
        # Pattern to match actions with optional cards
        pattern = r'([HSDPRI])(?:\(([^)]+)\))?'
        
        for match in re.finditer(pattern, s):
            action_char, card_str = match.groups()
            action = Action(action_char)
            card = Card.from_str(card_str) if card_str else None
            actions.append((action, card))
        
        return actions
    
    @staticmethod
    def parse_game(notation: str) -> GameRecord:
        """Parse complete game notation."""
        # Split into player|dealer|outcome sections
        parts = notation.split('|')
        if len(parts) < 2:
            raise ValueError(f"Invalid game notation: {notation}")
        
        player_part = parts[0]
        dealer_part = parts[1]
        
        # Parse player hands (may be split)
        player_hands = []
        if player_part.startswith('P:'):
            # Split hands
            hand_strs = player_part[2:].split(',')
            for hand_str in hand_strs:
                cards_str, actions_str = hand_str.split(':') if ':' in hand_str else (hand_str, '')
                cards = BlackjackNotation.parse_card_list(cards_str)
                actions = BlackjackNotation.parse_action_sequence(actions_str) if actions_str else []
                player_hands.append(Hand(initial_cards=cards, actions=actions, is_split=True))
        else:
            # Single hand
            cards_str, actions_str = player_part.split(':') if ':' in player_part else (player_part, '')
            cards = BlackjackNotation.parse_card_list(cards_str)
            actions = BlackjackNotation.parse_action_sequence(actions_str) if actions_str else []
            player_hands.append(Hand(initial_cards=cards, actions=actions))
        
        # Parse dealer
        dealer_cards_str, dealer_actions = dealer_part.split(':') if ':' in dealer_part else (dealer_part, '')
        dealer_cards = BlackjackNotation.parse_card_list(dealer_cards_str)
        
        # Add dealer hits if any
        if dealer_actions:
            for action, card in BlackjackNotation.parse_action_sequence(dealer_actions):
                if card:
                    dealer_cards.append(card)
        
        return GameRecord(
            player_hands=player_hands,
            dealer_cards=dealer_cards,
            dealer_value=0  # Will be calculated
        )


@dataclass
class TestCase:
    """Test case for validating engine behavior."""
    name: str
    deck: List[Card]  # Predetermined deck order
    rules: Dict[str, any]  # Rule overrides
    expected_actions: List[Action]  # Expected strategy decisions
    expected_outcome: Outcome
    expected_value: Optional[int] = None
    
    def to_notation(self) -> str:
        """Convert test case to notation."""
        lines = [
            f"# Test: {self.name}",
            f"@deck: {','.join(str(c) for c in self.deck)}",
            f"@rules: {self.rules}",
            f"@expect_actions: {','.join(a.value for a in self.expected_actions)}",
            f"@expect_outcome: {self.expected_outcome.value}",
        ]
        if self.expected_value:
            lines.append(f"@expect_value: {self.expected_value}")
        return '\n'.join(lines)
    
    @classmethod
    def from_notation(cls, notation: str) -> 'TestCase':
        """Parse test case from notation."""
        lines = notation.strip().split('\n')
        data = {}
        
        for line in lines:
            if line.startswith('#'):
                data['name'] = line[7:].strip()  # After "# Test: "
            elif line.startswith('@deck:'):
                card_str = line[6:].strip()
                data['deck'] = [Card.from_str(c.strip()) for c in card_str.split(',')]
            elif line.startswith('@rules:'):
                import ast
                data['rules'] = ast.literal_eval(line[7:].strip())
            elif line.startswith('@expect_actions:'):
                action_str = line[16:].strip()
                data['expected_actions'] = [Action(a) for a in action_str.split(',')]
            elif line.startswith('@expect_outcome:'):
                data['expected_outcome'] = Outcome(line[16:].strip())
            elif line.startswith('@expect_value:'):
                data['expected_value'] = int(line[14:].strip())
        
        return cls(**data)


class TestSuite:
    """Collection of test cases for validation."""
    
    def __init__(self):
        self.tests: List[TestCase] = []
    
    def add_test(self, test: TestCase):
        """Add a test case."""
        self.tests.append(test)
    
    def load_from_file(self, filename: str):
        """Load test cases from file."""
        with open(filename, 'r') as f:
            content = f.read()
        
        # Split by double newlines to separate test cases
        test_blocks = content.split('\n\n')
        
        for block in test_blocks:
            if block.strip():
                self.tests.append(TestCase.from_notation(block))
    
    def save_to_file(self, filename: str):
        """Save test cases to file."""
        with open(filename, 'w') as f:
            for i, test in enumerate(self.tests):
                if i > 0:
                    f.write('\n\n')
                f.write(test.to_notation())


# Example test cases
STANDARD_TESTS = [
    TestCase(
        name="Basic Strategy: 16 vs 10 should hit",
        deck=[Card.from_str(c) for c in ['Th', '6s', 'Kh', '9d', '5c']],
        rules={'dealer_hit_soft_17': True},
        expected_actions=[Action.HIT],
        expected_outcome=Outcome.WIN,
        expected_value=21
    ),
    
    TestCase(
        name="Always split 8s",
        deck=[Card.from_str(c) for c in ['8h', '8d', 'Th', '7s', '3c', 'As', '2h', '9d']],
        rules={'allow_split': True},
        expected_actions=[Action.SPLIT],
        expected_outcome=Outcome.WIN,
    ),
    
    TestCase(
        name="Blackjack beats 21",
        deck=[Card.from_str(c) for c in ['As', 'Kh', '7h', '4d', 'Th']],
        rules={},
        expected_actions=[Action.STAND],
        expected_outcome=Outcome.BLACKJACK_WIN,
    ),
]