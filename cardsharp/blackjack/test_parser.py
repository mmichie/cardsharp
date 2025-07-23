"""
Parser for test_cases.txt format.
Converts custom test case format to TestCase objects.
"""

import re
from typing import List, Dict, Any, Optional
from .notation import TestCase, Action, Outcome
from ..common.card import Card, Suit, Rank


class TestCaseParser:
    """Parse test cases from custom text format."""
    
    def __init__(self):
        self.current_case = None
        self.cases = []
    
    def parse_file(self, file_path: str) -> List[TestCase]:
        """Parse test cases from file."""
        self.cases = []
        self.current_case = None
        
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    # Comment or empty line - check if we should finalize current case
                    if self.current_case and self._is_case_complete():
                        self._finalize_case()
                    continue
                
                if line.startswith('@'):
                    self._parse_directive(line)
        
        # Finalize last case if any
        if self.current_case and self._is_case_complete():
            self._finalize_case()
        
        return self.cases
    
    def _parse_directive(self, line: str):
        """Parse a directive line starting with @."""
        if ':' not in line:
            return
        
        key, value = line.split(':', 1)
        key = key.strip('@').strip()
        value = value.strip()
        
        if key == 'deck':
            self._start_new_case()
            self.current_case['deck'] = self._parse_deck(value)
        elif key == 'rules':
            if self.current_case:
                self.current_case['rules'] = self._parse_rules(value)
        elif key == 'expect_actions':
            if self.current_case:
                self.current_case['expected_actions'] = self._parse_actions(value)
        elif key == 'expect_outcome':
            if self.current_case:
                self.current_case['expected_outcome'] = self._parse_outcome(value)
        elif key == 'expect_value':
            if self.current_case:
                self.current_case['expected_value'] = int(value)
    
    def _start_new_case(self):
        """Start a new test case."""
        if self.current_case and self._is_case_complete():
            self._finalize_case()
        self.current_case = {
            'deck': [],
            'rules': {},
            'expected_actions': [],
            'expected_outcome': None,
            'expected_value': None
        }
    
    def _is_case_complete(self) -> bool:
        """Check if current case has minimum required fields."""
        return (self.current_case and 
                'deck' in self.current_case and 
                len(self.current_case['deck']) > 0)
    
    def _finalize_case(self):
        """Convert current case dict to TestCase and add to cases."""
        if not self.current_case:
            return
        
        # Generate name from test contents
        name = self._generate_test_name()
        
        test_case = TestCase(
            name=name,
            deck=self.current_case['deck'],
            rules=self.current_case['rules'],
            expected_actions=self.current_case['expected_actions'],
            expected_outcome=self.current_case['expected_outcome'],
            expected_value=self.current_case.get('expected_value')
        )
        
        self.cases.append(test_case)
        self.current_case = None
    
    def _generate_test_name(self) -> str:
        """Generate descriptive test name from case contents."""
        parts = []
        
        # Add hand description if possible
        if len(self.current_case['deck']) >= 4:
            p1, d1, p2, d2 = self.current_case['deck'][:4]
            parts.append(f"{p1.rank}{p2.rank} vs {d1.rank}")
        
        # Add expected action
        if self.current_case['expected_actions']:
            action_str = ','.join(a.value for a in self.current_case['expected_actions'])
            parts.append(f"expect {action_str}")
        
        # Add outcome
        if self.current_case['expected_outcome']:
            parts.append(f"-> {self.current_case['expected_outcome'].value}")
        
        return " ".join(parts) if parts else f"Test Case {len(self.cases) + 1}"
    
    def _parse_deck(self, deck_str: str) -> List[Card]:
        """Parse deck string like 'Th,Kh,6s,9d,5c'."""
        cards = []
        card_strs = [c.strip() for c in deck_str.split(',')]
        
        for card_str in card_strs:
            if len(card_str) >= 2:
                rank_str = card_str[:-1]
                suit_str = card_str[-1]
                
                # Map notation to Rank enum
                rank_map = {
                    'A': Rank.ACE,
                    '2': Rank.TWO,
                    '3': Rank.THREE,
                    '4': Rank.FOUR,
                    '5': Rank.FIVE,
                    '6': Rank.SIX,
                    '7': Rank.SEVEN,
                    '8': Rank.EIGHT,
                    '9': Rank.NINE,
                    'T': Rank.TEN,
                    '10': Rank.TEN,
                    'J': Rank.JACK,
                    'Q': Rank.QUEEN,
                    'K': Rank.KING
                }
                
                # Map notation to Suit enum
                suit_map = {
                    's': Suit.SPADES,
                    'h': Suit.HEARTS,
                    'd': Suit.DIAMONDS,
                    'c': Suit.CLUBS
                }
                
                if rank_str in rank_map and suit_str in suit_map:
                    card = Card(suit_map[suit_str], rank_map[rank_str])
                    cards.append(card)
        
        return cards
    
    def _parse_rules(self, rules_str: str) -> Dict[str, Any]:
        """Parse rules string like "{'dealer_hit_soft_17': True}"."""
        try:
            # Safe evaluation of dict literal
            import ast
            rules = ast.literal_eval(rules_str)
            
            # Map common abbreviations to proper rule names
            rule_mapping = {
                'allow_double': 'allow_double_down',
                'double': 'allow_double_down',
                'split': 'allow_split',
                'surrender': 'allow_surrender'
            }
            
            # Enable resplitting if max_splits > 1
            if 'max_splits' in rules and rules['max_splits'] > 1:
                rules['allow_resplitting'] = True
            
            # Apply mappings
            for old_key, new_key in rule_mapping.items():
                if old_key in rules:
                    rules[new_key] = rules.pop(old_key)
            
            return rules
        except:
            return {}
    
    def _parse_actions(self, actions_str: str) -> List[Action]:
        """Parse actions string like 'H,S' or 'P,D,S'."""
        actions = []
        
        # Handle comma-separated actions
        action_parts = [a.strip() for a in actions_str.split(',')]
        
        for action_str in action_parts:
            action_map = {
                'H': Action.HIT,
                'S': Action.STAND,
                'D': Action.DOUBLE,
                'P': Action.SPLIT,
                'R': Action.SURRENDER
            }
            
            if action_str in action_map:
                actions.append(action_map[action_str])
        
        return actions
    
    def _parse_outcome(self, outcome_str: str) -> Optional[Outcome]:
        """Parse outcome string like 'W', 'L', 'P', 'BJ-W', 'R-L'."""
        outcome_map = {
            'W': Outcome.WIN,
            'L': Outcome.LOSS,
            'P': Outcome.PUSH,
            'BJ-W': Outcome.BLACKJACK_WIN,
            'R-L': Outcome.SURRENDER_LOSS
        }
        
        return outcome_map.get(outcome_str, None)