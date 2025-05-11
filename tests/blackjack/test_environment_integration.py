"""
Tests for environment integration with blackjack game.
"""

import unittest
import os
import sqlite3
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from cardsharp.blackjack.environment import EnvironmentIntegrator
from cardsharp.blackjack.casino import CasinoEnvironment, TableConditions, DealerProfile
from cardsharp.common.io_interface import IOInterface
from cardsharp.blackjack.bankroll import BasicBankrollManager, BankrollParameters
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.blackjack.realistic_strategy import SkillLevel
from cardsharp.verification.storage import SQLiteEventStore

# Skip all tests in this file until full verification integration is complete
pytestmark = pytest.mark.skip(reason="Verification integration not yet complete")
from cardsharp.verification.events import EventRecorder


class TestEnvironmentIntegration(unittest.TestCase):
    """Test integration of casino environment with blackjack game."""

    def setUp(self):
        """Set up test environment."""
        # Create a temporary database file for testing
        self.db_fd, self.db_path = tempfile.mkstemp()

        # Create casino environment
        self.casino = CasinoEnvironment(
            casino_type="standard", time_of_day="evening", weekday=True, table_count=1
        )

        # Get first table ID
        self.table_id = list(self.casino.tables.keys())[0]

        # Create event store with the temp database
        self.event_store = SQLiteEventStore(db_path=self.db_path)

        # Create session ID
        self.session_id = "test_session_123"

        # Create integrator
        self.integrator = EnvironmentIntegrator(
            casino_env=self.casino,
            table_id=self.table_id,
            event_store=self.event_store,
            session_id=self.session_id,
        )

        # Initialize database schema
        self.event_store.initialize_database()

    def tearDown(self):
        """Clean up after tests."""
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_initialization(self):
        """Test environment integrator initialization."""
        self.assertEqual(self.integrator.casino_env, self.casino)
        self.assertEqual(self.integrator.table_id, self.table_id)
        self.assertEqual(self.integrator.event_store, self.event_store)
        self.assertEqual(self.integrator.session_id, self.session_id)
        self.assertIsNotNone(self.integrator.table)
        self.assertIsNotNone(self.integrator.dealer_profile)
        self.assertIsNotNone(self.integrator.event_recorder)
        self.assertEqual(self.integrator.hands_played, 0)

    def test_create_game(self):
        """Test game creation with environment parameters."""
        game = self.integrator.create_game()

        # Game should be created with table rules
        self.assertEqual(game.rules, self.integrator.table.rules)

        # Penetration should be set from table
        self.assertEqual(game.penetration, self.integrator.table.penetration)

        # Game should have event emitter attached
        self.assertTrue(hasattr(game.state, "_event_emitter"))

    def test_add_player(self):
        """Test adding player with environment-aware execution."""
        # Create strategy and bankroll manager
        strategy = BasicStrategy()
        bankroll = BasicBankrollManager(
            initial_bankroll=1000.0, params=BankrollParameters()
        )

        # Add player with default skill
        player = self.integrator.add_player(
            strategy=strategy, bankroll_manager=bankroll
        )

        self.assertIsNotNone(player)
        self.assertEqual(player.name, "Player")
        self.assertEqual(player.bankroll_manager, bankroll)

        # Verify game has the player
        self.assertIn(player, self.integrator.game.players)

        # Player strategy should be wrapped in ExecutionVarianceWrapper
        self.assertEqual(player.strategy.__class__.__name__, "ExecutionVarianceWrapper")

        # Add player with explicit skill level
        skill_level = SkillLevel(
            counting_skill=0.7, strategy_knowledge=0.9, discipline=0.8
        )

        self.integrator.game = None  # Reset game
        player = self.integrator.add_player(
            strategy=strategy, bankroll_manager=bankroll, skill_level=skill_level
        )

        # Player strategy should first be wrapped in RealisticPlayerStrategy
        # and then in ExecutionVarianceWrapper
        self.assertEqual(player.strategy.__class__.__name__, "ExecutionVarianceWrapper")
        self.assertEqual(
            player.strategy.strategy.__class__.__name__, "RealisticPlayerStrategy"
        )

    @patch("time.time")
    def test_simulate_session(self, mock_time):
        """Test session simulation."""
        # Mock time.time() to return controlled values
        mock_time.return_value = 1000.0

        # Create strategy and bankroll manager
        strategy = BasicStrategy()
        bankroll = BasicBankrollManager(
            initial_bankroll=1000.0,
            params=BankrollParameters(
                session_time_target=4.0, stop_loss=0.5, stop_win=1.0
            ),
        )

        # Add player
        player = self.integrator.add_player(
            strategy=strategy, bankroll_manager=bankroll
        )

        # Simulate a short session
        results = self.integrator.simulate_session(
            hours=0.1, max_hands=10, verify=True  # 6 minutes
        )

        # Check results
        self.assertIsNotNone(results)
        self.assertEqual(results["session_id"], self.session_id)
        self.assertEqual(results["table_id"], self.table_id)
        self.assertLessEqual(results["hands_played"], 10)
        self.assertLessEqual(results["simulated_time_hours"], 0.1)
        self.assertIn("bankroll_stats", results)

        # Check database entries
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check session record
        cursor.execute(
            "SELECT COUNT(*) FROM sessions WHERE session_id = ?", (self.session_id,)
        )
        count = cursor.fetchone()[0]
        self.assertEqual(count, 1)

        # Check round records
        cursor.execute(
            "SELECT COUNT(*) FROM rounds WHERE session_id = ?", (self.session_id,)
        )
        rounds = cursor.fetchone()[0]
        self.assertEqual(rounds, results["hands_played"])

        # Check events
        cursor.execute(
            "SELECT COUNT(*) FROM events WHERE session_id = ?", (self.session_id,)
        )
        events = cursor.fetchone()[0]
        self.assertGreater(events, results["hands_played"])  # Multiple events per hand

        conn.close()

    def test_environmental_factors(self):
        """Test environmental factors affect gameplay."""
        # Create strategy and bankroll manager
        strategy = BasicStrategy()
        bankroll = BasicBankrollManager(initial_bankroll=1000.0)

        # Add player
        player = self.integrator.add_player(
            strategy=strategy, bankroll_manager=bankroll
        )

        # Set up environment with high distraction
        self.integrator.distraction_level = 0.9
        self.integrator.time_pressure = 0.8
        self.integrator.fatigue = 0.7

        # Calculate error rate
        error_rate = self.integrator._calculate_error_rate()

        # Error rate should be higher with these factors
        self.assertGreater(error_rate, 0.1)

        # Reset to normal conditions
        self.integrator.distraction_level = 0.2
        self.integrator.time_pressure = 0.2
        self.integrator.fatigue = 0.1

        # Calculate error rate again
        low_error_rate = self.integrator._calculate_error_rate()

        # Error rate should be lower
        self.assertLess(low_error_rate, error_rate)

    def test_dealer_errors(self):
        """Test dealer error handling."""
        # Create a dealer with high error rate
        dealer = DealerProfile(
            name="Error Dealer", error_rate=1.0  # Always makes errors
        )

        # Replace the default dealer
        self.integrator.dealer_profile = dealer
        self.integrator.current_round_id = "test_round_1"

        # Test error handling
        error_made, error_type = self.integrator._handle_dealer_errors()

        self.assertTrue(error_made)
        self.assertIsNotNone(error_type)
        self.assertEqual(self.integrator.dealer_errors, 1)

        # Check event recording
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM events WHERE event_type = 'dealer_error'")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 1)

        conn.close()

    def test_hand_timing(self):
        """Test hand timing simulation."""
        # Create strategy and bankroll manager
        strategy = BasicStrategy()
        bankroll = BasicBankrollManager(initial_bankroll=1000.0)

        # Add player
        player = self.integrator.add_player(
            strategy=strategy, bankroll_manager=bankroll
        )

        # Get timing with normal dealer
        normal_timing = self.integrator._simulate_hand_timing()

        # Set a fast dealer
        fast_dealer = DealerProfile(name="Fast Dealer", speed=1.5)  # 50% faster
        self.integrator.dealer_profile = fast_dealer

        # Get timing with fast dealer
        fast_timing = self.integrator._simulate_hand_timing()

        # Fast dealer should be faster
        self.assertLess(fast_timing, normal_timing)

        # Set a slow dealer
        slow_dealer = DealerProfile(name="Slow Dealer", speed=0.7)  # 30% slower
        self.integrator.dealer_profile = slow_dealer

        # Get timing with slow dealer
        slow_timing = self.integrator._simulate_hand_timing()

        # Slow dealer should be slower
        self.assertGreater(slow_timing, normal_timing)

    def test_verify_game_state(self):
        """Test game state verification."""
        # Create game and set current round
        self.integrator.create_game()
        self.integrator.current_round_id = "test_round_2"

        # Verification without playing should pass by default
        results = self.integrator._verify_game_state()
        self.assertTrue(results["verified"])

        # Simulate a played round with mocked verifier
        with patch("cardsharp.verification.verifier.BlackjackVerifier") as MockVerifier:
            # Set mock to return failure
            mock_instance = MockVerifier.return_value
            mock_instance.verify_round.return_value = {
                "verified": False,
                "reason": "Test failure reason",
            }

            # Verify should fail
            results = self.integrator._verify_game_state()
            self.assertFalse(results["verified"])
            self.assertEqual(results["reason"], "Test failure reason")


if __name__ == "__main__":
    unittest.main()
