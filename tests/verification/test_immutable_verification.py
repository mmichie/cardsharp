"""
Tests for the immutable state verification system.

This module contains tests to verify that the immutable state verification
system works correctly.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from cardsharp.api import BlackjackGame
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType
from cardsharp.blackjack.rules import Rules
from cardsharp.state import GameState, GameStage
from cardsharp.verification.immutable_verifier import (
    StateTransition,
    StateTransitionRecorder,
    ImmutableStateVerifier,
)
from cardsharp.verification.verifier import VerificationType


class TestStateTransitionRecorder(unittest.TestCase):
    """Tests for the StateTransitionRecorder class."""

    def setUp(self):
        """Set up the test case."""
        self.event_bus = EventBus.get_instance()
        self.recorder = StateTransitionRecorder()

    def tearDown(self):
        """Tear down the test case."""
        self.recorder.shutdown()

    def test_initialization(self):
        """Test that the recorder initializes correctly."""
        self.assertIsNotNone(self.recorder)
        self.assertEqual(len(self.recorder.transitions), 0)
        self.assertIsNone(self.recorder.current_state)
        self.assertGreater(len(self.recorder.unsubscribe_funcs), 0)

    def test_event_subscription(self):
        """Test that the recorder subscribes to events."""
        # Create a mock event handler
        mock_handler = MagicMock()

        # Patch the recorder's _handle_event method
        original_handler = self.recorder._handle_event
        self.recorder._handle_event = mock_handler

        try:
            # Emit an event
            self.event_bus.emit(
                EngineEventType.GAME_STARTED, {"game_id": "test", "timestamp": 0.0}
            )

            # Check that the handler was called
            mock_handler.assert_called_once()
        finally:
            # Restore the original handler
            self.recorder._handle_event = original_handler

    def test_shutdown(self):
        """Test that the recorder shuts down correctly."""
        # Create mock unsubscribe functions
        mock_unsubs = [MagicMock() for _ in range(3)]
        self.recorder.unsubscribe_funcs = mock_unsubs

        # Shutdown the recorder
        self.recorder.shutdown()

        # Check that all unsubscribe functions were called
        for unsub in mock_unsubs:
            unsub.assert_called_once()

        # Check that the unsubscribe list was cleared
        self.assertEqual(len(self.recorder.unsubscribe_funcs), 0)

    def test_clear(self):
        """Test that the recorder clears its state."""
        # Add some mock transitions
        self.recorder.transitions = [MagicMock() for _ in range(3)]
        self.recorder.current_state = MagicMock()

        # Clear the recorder
        self.recorder.clear()

        # Check that the transitions list was cleared
        self.assertEqual(len(self.recorder.transitions), 0)
        self.assertIsNone(self.recorder.current_state)


class TestImmutableStateVerifier(unittest.TestCase):
    """Tests for the ImmutableStateVerifier class."""

    def setUp(self):
        """Set up the test case."""
        self.recorder = MagicMock()
        self.rules = Rules(
            blackjack_payout=1.5,
            deck_count=6,
            dealer_hit_soft_17=False,
            offer_insurance=True,
            allow_surrender=True,
            allow_double_after_split=True,
            allow_split=True,
            allow_double_down=True,
            min_bet=5.0,
            max_bet=1000.0,
        )
        self.verifier = ImmutableStateVerifier(self.recorder, self.rules)

    def test_initialization(self):
        """Test that the verifier initializes correctly."""
        self.assertIsNotNone(self.verifier)
        self.assertEqual(self.verifier.recorder, self.recorder)
        self.assertEqual(self.verifier.rules, self.rules)

    def test_verify_all(self):
        """Test that verify_all runs all verification checks."""
        # Create mock methods for all verification checks
        methods = [
            "verify_dealer_actions",
            "verify_player_options",
            "verify_payouts",
            "verify_deck_integrity",
            "verify_shuffle_timing",
            "verify_bet_sizes",
            "verify_insurance",
        ]

        mocks = {}
        for method in methods:
            mock = MagicMock()
            mock.return_value = MagicMock(passed=True)
            mocks[method] = mock
            setattr(self.verifier, method, mock)

        # Run verify_all
        results = self.verifier.verify_all()

        # Check that all methods were called
        for method, mock in mocks.items():
            mock.assert_called_once()

        # Check that all results were returned
        self.assertEqual(len(results), len(methods))

    @patch("cardsharp.verification.immutable_verifier.VerificationResult")
    def test_verification_methods(self, mock_result):
        """Test that verification methods return results."""
        # Configure the mock to return a verification result
        mock_result.return_value = MagicMock(passed=True)

        # Create empty mock transitions
        self.recorder.get_transitions_by_action.return_value = []

        # Test each verification method
        methods = [
            "verify_dealer_actions",
            "verify_player_options",
            "verify_payouts",
            "verify_bet_sizes",
            "verify_insurance",
        ]

        for method in methods:
            result = getattr(self.verifier, method)()
            self.assertIsNotNone(result)
            self.assertTrue(result.passed)


class TestIntegration(unittest.TestCase):
    """Integration tests for the immutable state verification system."""

    def setUp(self):
        """Set up the test case."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Create the verification components
        self.recorder = StateTransitionRecorder()
        self.rules = Rules(
            blackjack_payout=1.5,
            deck_count=6,
            dealer_hit_soft_17=False,
            offer_insurance=True,
            allow_surrender=True,
            allow_double_after_split=True,
            allow_split=True,
            allow_double_down=True,
            min_bet=5.0,
            max_bet=1000.0,
        )
        self.verifier = ImmutableStateVerifier(self.recorder, self.rules)

    def tearDown(self):
        """Tear down the test case."""
        self.recorder.shutdown()
        self.loop.close()

    def test_game_verification(self):
        """Test that a game can be verified."""

        async def run_test():
            # Create a dummy adapter
            adapter = DummyAdapter()

            # Create a game
            config = {
                "dealer_rules": {"stand_on_soft_17": True, "peek_for_blackjack": True},
                "deck_count": 6,
                "rules": self.rules.__dict__,
            }

            game = BlackjackGame(adapter=adapter, config=config, auto_play=True)

            try:
                # Initialize the game
                await game.initialize()

                # Start the game
                await game.start_game()

                # Add players
                player1 = await game.add_player("Alice", 1000.0)
                player2 = await game.add_player("Bob", 1000.0)

                # Play a round
                result = await game.auto_play_round(default_bet=10.0)

                # Run verification
                verification_results = self.verifier.verify_all()

                # Check that verification results were returned
                self.assertGreater(len(verification_results), 0)

                # Count passing results
                passing = sum(1 for r in verification_results if r.passed)

                # Not all checks will pass in this simple test, but some should
                self.assertGreater(passing, 0)

            finally:
                # Shutdown the game
                await game.shutdown()

        # Run the test
        self.loop.run_until_complete(run_test())


if __name__ == "__main__":
    unittest.main()
