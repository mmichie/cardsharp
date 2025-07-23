"""
Pytest configuration and fixtures for blackjack tests.
"""

import pytest
import logging
from typing import Dict, Any
from cardsharp.blackjack.decision_logger import decision_logger


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "strategy: mark test as testing strategy decisions"
    )
    config.addinivalue_line(
        "markers", "blackjack: mark test as testing blackjack scenarios"
    )
    config.addinivalue_line(
        "markers", "split: mark test as testing split scenarios"
    )
    config.addinivalue_line(
        "markers", "surrender: mark test as testing surrender scenarios"
    )
    config.addinivalue_line(
        "markers", "debug: mark test for debugging with full logging"
    )
    config.addinivalue_line(
        "markers", "benchmark: mark test as performance benchmark"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )


@pytest.fixture(scope="session")
def test_results_summary():
    """Collect test results for summary reporting."""
    results = {
        'total': 0,
        'passed': 0,
        'failed': 0,
        'skipped': 0,
        'by_category': {}
    }
    yield results
    
    # Print summary at end of session
    if results['total'] > 0:
        print("\n" + "="*70)
        print("ENGINE VALIDATION TEST SUMMARY")
        print("="*70)
        print(f"Total tests: {results['total']}")
        print(f"Passed: {results['passed']} ({results['passed']/results['total']*100:.1f}%)")
        print(f"Failed: {results['failed']} ({results['failed']/results['total']*100:.1f}%)")
        print(f"Skipped: {results['skipped']} ({results['skipped']/results['total']*100:.1f}%)")
        
        if results['by_category']:
            print("\nBy Category:")
            for category, stats in results['by_category'].items():
                print(f"  {category}: {stats['passed']}/{stats['total']} passed")


@pytest.fixture
def capture_decisions():
    """Fixture to capture decision logs for a test."""
    # Clear existing decisions
    decision_logger.decision_history = []
    decision_logger.current_round_decisions = []
    
    # Set logging level
    original_level = decision_logger.logger.level
    decision_logger.logger.setLevel(logging.INFO)
    
    yield decision_logger
    
    # Restore original level
    decision_logger.logger.setLevel(original_level)


@pytest.fixture
def strategy_test_tolerance():
    """
    Fixture that defines acceptable strategy variations.
    Some tests may fail due to valid strategy differences.
    """
    return {
        # Surrender variations
        'surrender_16_vs_10': ['surrender', 'hit'],  # Both are valid
        'surrender_15_vs_10': ['surrender', 'hit'],  # Both are valid
        
        # Soft hand variations
        'soft_18_vs_3': ['double', 'stand'],  # DS in basic strategy
        'soft_18_vs_2': ['double', 'stand'],  # DS in basic strategy
        
        # Close calls
        'hard_12_vs_2': ['hit', 'stand'],  # Very close EV
        'hard_12_vs_3': ['hit', 'stand'],  # Very close EV
    }


@pytest.fixture
def validate_with_tolerance(strategy_test_tolerance):
    """Fixture that provides a validation function with strategy tolerance."""
    
    def _validate(test_name: str, expected_action: str, actual_action: str) -> bool:
        """Check if actual action is acceptable given strategy variations."""
        # Check for exact match first
        if expected_action == actual_action:
            return True
        
        # Check tolerance rules
        for pattern, valid_actions in strategy_test_tolerance.items():
            if pattern in test_name.lower():
                return (expected_action in valid_actions and 
                       actual_action in valid_actions)
        
        return False
    
    return _validate


# Hook to track test results
def pytest_runtest_logreport(report):
    """Hook to capture test results for summary."""
    if report.when == "call" and hasattr(report, "outcome"):
        # Access the summary fixture if available
        if hasattr(pytest, "_current_summary"):
            summary = pytest._current_summary
            summary['total'] += 1
            
            if report.outcome == "passed":
                summary['passed'] += 1
            elif report.outcome == "failed":
                summary['failed'] += 1
            elif report.outcome == "skipped":
                summary['skipped'] += 1
            
            # Track by category if markers present
            for marker in report.keywords:
                if marker in ['blackjack', 'split', 'surrender', 'strategy']:
                    if marker not in summary['by_category']:
                        summary['by_category'][marker] = {'total': 0, 'passed': 0}
                    
                    summary['by_category'][marker]['total'] += 1
                    if report.outcome == "passed":
                        summary['by_category'][marker]['passed'] += 1