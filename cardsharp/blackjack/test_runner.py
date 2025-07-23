"""
Complete test runner that integrates the test framework with the game engine.
"""

from typing import Dict, List, Any
from .notation import TestCase, TestSuite, Action, Outcome
from .test_engine import DeterministicShoe
from .test_support import TestPlayer, TestableBlackjackGame, GameOutcome
from .blackjack import BlackjackGame, Rules
from ..common.io_interface import DummyIOInterface
from .test_parser import TestCaseParser
import os


def map_outcome_to_notation(game_outcome: GameOutcome) -> Outcome:
    """Map internal game outcome to test notation outcome."""
    mapping = {
        GameOutcome.PLAYER_BLACKJACK: Outcome.BLACKJACK_WIN,
        GameOutcome.DEALER_BLACKJACK: Outcome.LOSS,
        GameOutcome.BOTH_BLACKJACK: Outcome.PUSH,
        GameOutcome.PLAYER_BUST: Outcome.LOSS,
        GameOutcome.DEALER_BUST: Outcome.WIN,
        GameOutcome.PLAYER_HIGHER: Outcome.WIN,
        GameOutcome.DEALER_HIGHER: Outcome.LOSS,
        GameOutcome.PUSH: Outcome.PUSH,
        GameOutcome.SURRENDER: Outcome.SURRENDER_LOSS,
    }
    return mapping.get(game_outcome, Outcome.LOSS)


def map_action_to_notation(action_str: str) -> Action:
    """Map internal action string to test notation action."""
    mapping = {
        'hit': Action.HIT,
        'stand': Action.STAND,
        'double': Action.DOUBLE,
        'split': Action.SPLIT,
        'surrender': Action.SURRENDER,
    }
    return mapping.get(action_str, Action.HIT)


class BlackjackTestRunner:
    """Runs test cases against the blackjack engine."""
    
    def __init__(self):
        self.results = []
    
    def run_test(self, test_case: TestCase) -> Dict[str, Any]:
        """Run a single test case and return results."""
        try:
            # Create deterministic shoe with test deck
            # IMPORTANT: Deal order is Player1, Dealer, Player2, Dealer...
            shoe = DeterministicShoe(test_case.deck)
            
            # Create game with test rules
            rules = Rules(**test_case.rules)
            io = DummyIOInterface()
            game = BlackjackGame(rules, io, shoe)
            
            # Wrap game for testing
            testable_game = TestableBlackjackGame(game)
            test_player = testable_game.add_test_player()
            
            # Start game in PlacingBetsState to skip waiting
            from cardsharp.blackjack.state import PlacingBetsState
            game.set_state(PlacingBetsState())
            
            # Play the round
            testable_game.play_round()
            
            # Get game record
            record = testable_game.get_game_record()
            
            if not record:
                return {
                    'passed': False,
                    'error': 'No game record available',
                    'test_name': test_case.name
                }
            
            # Extract results - flatten split hand actions into single list
            actual_actions = []
            for action in record.player_actions:
                mapped_action = map_action_to_notation(action.action_taken)
                actual_actions.append(mapped_action)
            
            # Get primary hand outcome (first hand, unless splits)
            primary_outcome = None
            actual_value = None
            
            if record.hand_outcomes:
                # For split hands, determine overall outcome
                if len(record.hand_outcomes) > 1:
                    # Map each hand outcome to notation outcome
                    mapped_outcomes = []
                    for h in record.hand_outcomes:
                        mapped = map_outcome_to_notation(h.outcome)
                        mapped_outcomes.append(mapped)
                    
                    # Count wins, losses, pushes
                    wins = sum(1 for o in mapped_outcomes if o == Outcome.WIN or o == Outcome.BLACKJACK_WIN)
                    losses = sum(1 for o in mapped_outcomes if o == Outcome.LOSS)
                    pushes = sum(1 for o in mapped_outcomes if o == Outcome.PUSH)
                    
                    # Determine overall outcome: Win if any hand wins, Loss if all lose
                    if wins > 0:
                        primary_outcome = Outcome.WIN
                    elif pushes > 0 and losses < len(record.hand_outcomes):
                        primary_outcome = Outcome.PUSH
                    else:
                        primary_outcome = Outcome.LOSS
                else:
                    # Single hand
                    hand_outcome = record.hand_outcomes[0]
                    primary_outcome = map_outcome_to_notation(hand_outcome.outcome)
                    actual_value = hand_outcome.final_value
                    
                    # Special handling for blackjack - add implicit stand if no actions recorded
                    if hand_outcome.is_blackjack and not actual_actions:
                        actual_actions = [Action.STAND]
            
            # Check if test passed
            passed = True
            errors = []
            
            # Check actions if specified
            if test_case.expected_actions:
                if actual_actions != test_case.expected_actions:
                    passed = False
                    errors.append(
                        f"Actions mismatch: expected {[a.value for a in test_case.expected_actions]}, "
                        f"got {[a.value for a in actual_actions]}"
                    )
            
            # Check outcome if specified
            if test_case.expected_outcome and primary_outcome:
                if primary_outcome != test_case.expected_outcome:
                    passed = False
                    errors.append(
                        f"Outcome mismatch: expected {test_case.expected_outcome.value}, "
                        f"got {primary_outcome.value}"
                    )
            
            # Check value if specified
            if test_case.expected_value is not None and actual_value is not None:
                if actual_value != test_case.expected_value:
                    passed = False
                    errors.append(
                        f"Value mismatch: expected {test_case.expected_value}, "
                        f"got {actual_value}"
                    )
            
            return {
                'passed': passed,
                'test_name': test_case.name,
                'errors': errors,
                'actual_actions': actual_actions,
                'actual_outcome': primary_outcome,
                'actual_value': actual_value,
                'game_record': record.to_dict()
            }
            
        except Exception as e:
            import traceback
            return {
                'passed': False,
                'test_name': test_case.name,
                'error': str(e),
                'traceback': traceback.format_exc()
            }
    
    def run_suite(self, test_suite: TestSuite) -> Dict[str, Any]:
        """Run all tests in a suite."""
        self.results = []
        
        for test in test_suite.tests:
            result = self.run_test(test)
            self.results.append(result)
        
        # Calculate summary
        passed = sum(1 for r in self.results if r['passed'])
        failed = len(self.results) - passed
        
        return {
            'total': len(self.results),
            'passed': passed,
            'failed': failed,
            'pass_rate': passed / len(self.results) if self.results else 0,
            'results': self.results
        }
    
    def print_results(self, detailed=False):
        """Print test results."""
        if not self.results:
            print("No test results")
            return
        
        print("\nTest Results")
        print("=" * 70)
        
        for result in self.results:
            status = "✓ PASS" if result['passed'] else "✗ FAIL"
            print(f"\n{status} {result['test_name']}")
            
            if not result['passed']:
                if 'error' in result:
                    print(f"  Error: {result['error']}")
                    if detailed and 'traceback' in result:
                        print(f"  Traceback:\n{result['traceback']}")
                
                if 'errors' in result:
                    for error in result['errors']:
                        print(f"  - {error}")
            
            if detailed or not result['passed']:
                if 'actual_actions' in result:
                    print(f"  Actions: {[a.value for a in result.get('actual_actions', [])]}")
                if 'actual_outcome' in result and result['actual_outcome']:
                    print(f"  Outcome: {result['actual_outcome'].value}")
                if 'actual_value' in result:
                    print(f"  Value: {result['actual_value']}")
        
        # Summary
        passed = sum(1 for r in self.results if r['passed'])
        total = len(self.results)
        
        print("\n" + "=" * 70)
        print(f"Summary: {passed}/{total} passed ({passed/total*100:.1f}%)")


def load_test_cases_from_file(file_path: str) -> TestSuite:
    """Load test cases from test_cases.txt file."""
    parser = TestCaseParser()
    test_cases = parser.parse_file(file_path)
    
    suite = TestSuite()
    for test in test_cases:
        suite.add_test(test)
    
    return suite


def run_standard_tests():
    """Run the standard test cases from test_cases.txt."""
    runner = BlackjackTestRunner()
    
    # Try to load test cases from file
    test_file = os.path.join(os.path.dirname(__file__), 'test_cases.txt')
    if os.path.exists(test_file):
        print(f"Loading test cases from {test_file}")
        suite = load_test_cases_from_file(test_file)
        print(f"Loaded {len(suite.tests)} test cases")
    else:
        print("test_cases.txt not found, using hardcoded test cases")
        # Fallback to basic test cases
        from ..common.card import Card, Suit, Rank
        tests = [
            TestCase(
                name="Player Blackjack beats Dealer 20",
                deck=[
                    Card(Suit.SPADES, Rank.ACE), Card(Suit.HEARTS, Rank.KING),
                    Card(Suit.DIAMONDS, Rank.KING), Card(Suit.CLUBS, Rank.KING),
                ],
                rules={},
                expected_actions=[],
                expected_outcome=Outcome.BLACKJACK_WIN,
                expected_value=21
            ),
        ]
        suite = TestSuite()
        for test in tests:
            suite.add_test(test)
    
    # Run tests
    results = runner.run_suite(suite)
    runner.print_results(detailed=True)
    
    return results


if __name__ == "__main__":
    print("Blackjack Test Runner")
    print("=" * 70)
    
    results = run_standard_tests()
    
    if results['failed'] > 0:
        print("\n⚠️  Some tests failed. This may be due to:")
        print("  1. Strategy implementation differences")
        print("  2. Rule interpretation differences")
        print("  3. Test case errors")
        print("\nRun with detailed=True to see more information.")