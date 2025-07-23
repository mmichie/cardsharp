"""
Blackjack Test Engine - Validates engine accuracy using notation-based test cases.
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import json
from pathlib import Path

from .notation import (
    Card, Action, Outcome, TestCase, TestSuite, 
    BlackjackNotation, GameRecord, Hand
)
from ..common.shoe import Shoe
from ..common.card import Card as EngineCard, Suit, Rank


@dataclass
class TestResult:
    """Result of running a test case."""
    test_name: str
    passed: bool
    expected_actions: List[Action]
    actual_actions: List[Action]
    expected_outcome: Outcome
    actual_outcome: Optional[Outcome]
    expected_value: Optional[int]
    actual_value: Optional[int]
    error_message: Optional[str] = None
    
    def __str__(self) -> str:
        status = "✓ PASS" if self.passed else "✗ FAIL"
        msg = f"{status} {self.test_name}"
        
        if not self.passed and self.error_message:
            msg += f"\n  Error: {self.error_message}"
            if self.expected_actions != self.actual_actions:
                msg += f"\n  Expected actions: {[a.value for a in self.expected_actions]}"
                msg += f"\n  Actual actions: {[a.value for a in self.actual_actions]}"
            if self.expected_outcome != self.actual_outcome:
                msg += f"\n  Expected outcome: {self.expected_outcome.value}"
                msg += f"\n  Actual outcome: {self.actual_outcome.value if self.actual_outcome else 'None'}"
        
        return msg


class DeterministicShoe(Shoe):
    """A shoe that deals cards in a predetermined order for testing."""
    
    def __init__(self, cards: List[Card]):
        """Initialize with specific card order."""
        # Convert notation cards to engine cards
        self.predetermined_cards = []
        for card in cards:
            # Check if card is already an EngineCard or needs conversion
            if isinstance(card, EngineCard):
                self.predetermined_cards.append(card)
            elif hasattr(card, 'rank') and hasattr(card, 'suit'):
                # Check if rank/suit are already enums or strings
                if isinstance(card.rank, Rank):
                    rank = card.rank
                else:
                    rank = self._convert_rank(card.rank)
                
                if isinstance(card.suit, Suit):
                    suit = card.suit
                else:
                    suit = self._convert_suit(card.suit)
                
                self.predetermined_cards.append(EngineCard(suit, rank))
            else:
                raise ValueError(f"Invalid card type: {type(card)}")
        
        self.position = 0
        self.num_cards = len(self.predetermined_cards)
        
        # Initialize parent with dummy values
        super().__init__(num_decks=1, penetration=1.0)
    
    def _convert_rank(self, rank_str: str) -> Rank:
        """Convert notation rank to engine rank."""
        rank_map = {
            'A': Rank.ACE,
            '2': Rank.TWO, '3': Rank.THREE, '4': Rank.FOUR,
            '5': Rank.FIVE, '6': Rank.SIX, '7': Rank.SEVEN,
            '8': Rank.EIGHT, '9': Rank.NINE, 'T': Rank.TEN,
            'J': Rank.JACK, 'Q': Rank.QUEEN, 'K': Rank.KING
        }
        return rank_map[rank_str]
    
    def _convert_suit(self, suit_str: str) -> Suit:
        """Convert notation suit to engine suit."""
        suit_map = {
            's': Suit.SPADES,
            'h': Suit.HEARTS,
            'd': Suit.DIAMONDS,
            'c': Suit.CLUBS
        }
        return suit_map[suit_str]
    
    def deal(self) -> EngineCard:
        """Deal next predetermined card."""
        if self.position >= len(self.predetermined_cards):
            raise ValueError("No more cards in deterministic shoe")
        
        card = self.predetermined_cards[self.position]
        self.position += 1
        return card
    
    def shuffle(self):
        """Don't shuffle - maintain predetermined order."""
        self.position = 0


class TestEngine:
    """Engine for running blackjack test cases."""
    
    def __init__(self):
        self.results: List[TestResult] = []
    
    def run_test(self, test_case: TestCase, implementation='python') -> TestResult:
        """Run a single test case."""
        try:
            if implementation == 'python':
                return self._run_python_test(test_case)
            elif implementation == 'c':
                return self._run_c_test(test_case)
            else:
                raise ValueError(f"Unknown implementation: {implementation}")
        except Exception as e:
            return TestResult(
                test_name=test_case.name,
                passed=False,
                expected_actions=test_case.expected_actions,
                actual_actions=[],
                expected_outcome=test_case.expected_outcome,
                actual_outcome=None,
                expected_value=test_case.expected_value,
                actual_value=None,
                error_message=str(e)
            )
    
    def _run_python_test(self, test_case: TestCase) -> TestResult:
        """Run test using Python implementation."""
        from ..blackjack.blackjack import BlackjackGame, Rules
        from ..blackjack.strategy import BasicStrategy
        from ..blackjack.actor import Player
        from ..adapters.base import DummyIOInterface
        
        # Create deterministic shoe
        shoe = DeterministicShoe(test_case.deck)
        
        # Create rules from test case
        rules = Rules(**test_case.rules)
        
        # Create game
        game = BlackjackGame(rules, DummyIOInterface(), shoe)
        
        # Create player with recording strategy
        recorder = RecordingStrategy()
        player = Player("TestPlayer", DummyIOInterface(), recorder)
        game.add_player(player)
        
        # Play the round
        game.play_round()
        
        # Extract results
        actual_actions = recorder.recorded_actions
        
        # Determine outcome
        actual_outcome = self._determine_outcome(game, player)
        actual_value = player.hands[0].value() if player.hands else None
        
        # Compare with expected
        passed = (
            actual_actions == test_case.expected_actions and
            actual_outcome == test_case.expected_outcome and
            (test_case.expected_value is None or actual_value == test_case.expected_value)
        )
        
        return TestResult(
            test_name=test_case.name,
            passed=passed,
            expected_actions=test_case.expected_actions,
            actual_actions=actual_actions,
            expected_outcome=test_case.expected_outcome,
            actual_outcome=actual_outcome,
            expected_value=test_case.expected_value,
            actual_value=actual_value,
            error_message=None if passed else "Mismatch in actions or outcome"
        )
    
    def _run_c_test(self, test_case: TestCase) -> TestResult:
        """Run test using C implementation."""
        # This would require modifying the C engine to accept predetermined decks
        # For now, return a placeholder
        return TestResult(
            test_name=test_case.name,
            passed=False,
            expected_actions=test_case.expected_actions,
            actual_actions=[],
            expected_outcome=test_case.expected_outcome,
            actual_outcome=None,
            expected_value=test_case.expected_value,
            actual_value=None,
            error_message="C implementation testing not yet implemented"
        )
    
    def _determine_outcome(self, game, player) -> Outcome:
        """Determine game outcome."""
        # This is simplified - would need full implementation
        if player.hands[0].is_blackjack():
            return Outcome.BLACKJACK_WIN
        elif player.hands[0].is_bust():
            return Outcome.LOSS
        # Would need to check dealer hand, etc.
        return Outcome.WIN
    
    def run_suite(self, test_suite: TestSuite, implementation='python') -> Dict[str, any]:
        """Run all tests in a suite."""
        self.results = []
        
        for test in test_suite.tests:
            result = self.run_test(test, implementation)
            self.results.append(result)
        
        # Calculate summary
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        
        return {
            'total': len(self.results),
            'passed': passed,
            'failed': failed,
            'pass_rate': passed / len(self.results) if self.results else 0,
            'results': self.results
        }
    
    def print_summary(self):
        """Print test results summary."""
        if not self.results:
            print("No test results")
            return
        
        print("\nTest Results")
        print("=" * 60)
        
        for result in self.results:
            print(result)
        
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        print("\n" + "=" * 60)
        print(f"Total: {total} | Passed: {passed} | Failed: {total - passed}")
        print(f"Pass Rate: {passed/total*100:.1f}%")


class RecordingStrategy:
    """Strategy that records all decisions for testing."""
    
    def __init__(self):
        self.recorded_actions = []
        self.base_strategy = None  # Would use BasicStrategy
    
    def decide_action(self, player, dealer_up_card, game=None):
        """Record and return the action."""
        # This would use BasicStrategy to get the action
        # Then record it before returning
        action = Action.HIT  # Placeholder
        self.recorded_actions.append(action)
        return action


def create_standard_test_file():
    """Create a file with standard test cases."""
    tests = [
        # Basic strategy tests
        """# Test: Hard 16 vs 10 - Should Hit
@deck: Th,6s,Kh,9d,5c,Qh
@rules: {'dealer_hit_soft_17': True}
@expect_actions: H
@expect_outcome: W
@expect_value: 21""",

        # Split tests
        """# Test: Always Split 8s
@deck: 8h,8d,Th,7s,3c,As,Kh,9d
@rules: {'allow_split': True}
@expect_actions: P
@expect_outcome: W""",

        # Soft hand tests
        """# Test: Soft 18 vs 3 - Should Double
@deck: As,7h,3d,5c,2h,Kh,8d
@rules: {'allow_double': True}
@expect_actions: D
@expect_outcome: W
@expect_value: 21""",

        # Surrender tests
        """# Test: 16 vs 10 - Should Surrender if allowed
@deck: Th,6s,As,9d
@rules: {'allow_surrender': True}
@expect_actions: R
@expect_outcome: R-L""",

        # Blackjack tests
        """# Test: Player Blackjack beats dealer 21
@deck: As,Kh,7h,4d,Th
@rules: {}
@expect_actions: S
@expect_outcome: BJ-W""",
    ]
    
    with open('blackjack_tests.txt', 'w') as f:
        f.write('\n\n'.join(tests))
    
    print("Created blackjack_tests.txt with standard test cases")


def validate_implementation(implementation='python'):
    """Run validation tests on an implementation."""
    # Load standard tests
    suite = TestSuite()
    
    # Add programmatic tests
    for test in STANDARD_TESTS:
        suite.add_test(test)
    
    # Run tests
    engine = TestEngine()
    results = engine.run_suite(suite, implementation)
    
    # Print results
    engine.print_summary()
    
    return results


# Example usage
if __name__ == "__main__":
    # Create test file
    create_standard_test_file()
    
    # Run validation
    results = validate_implementation('python')
    
    # Could also compare implementations
    # python_results = validate_implementation('python')
    # c_results = validate_implementation('c')
    # compare_results(python_results, c_results)