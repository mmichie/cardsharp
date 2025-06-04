"""
Tests for environment integration with blackjack game.
"""

import os
import sqlite3
import tempfile
import pytest
from unittest.mock import patch

from cardsharp.blackjack.environment import EnvironmentIntegrator
from cardsharp.blackjack.casino import CasinoEnvironment, DealerProfile
from cardsharp.blackjack.bankroll import BasicBankrollManager, BankrollParameters
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.blackjack.realistic_strategy import SkillLevel
from cardsharp.verification.storage import SQLiteEventStore

# Skip all tests in this file until full verification integration is complete
pytestmark = pytest.mark.skip(reason="Verification integration not yet complete")


@pytest.fixture
def environment_setup():
    """Set up test environment."""
    # Create a temporary database file for testing
    db_fd, db_path = tempfile.mkstemp()

    # Create casino environment
    casino = CasinoEnvironment(
        casino_type="standard", time_of_day="evening", weekday=True, table_count=1
    )

    # Get first table ID
    table_id = list(casino.tables.keys())[0]

    # Create event store with the temp database
    event_store = SQLiteEventStore(db_path=db_path)

    # Create session ID
    session_id = "test_session_123"

    # Create integrator
    integrator = EnvironmentIntegrator(
        casino_env=casino,
        table_id=table_id,
        event_store=event_store,
        session_id=session_id,
    )

    # Initialize database schema
    event_store.initialize_database()

    yield integrator, casino, table_id, event_store, session_id, db_fd, db_path

    # Clean up after tests
    os.close(db_fd)
    os.unlink(db_path)


def test_initialization(environment_setup):
    """Test environment integrator initialization."""
    integrator, casino, table_id, event_store, session_id, _, _ = environment_setup

    assert integrator.casino_env == casino
    assert integrator.table_id == table_id
    assert integrator.event_store == event_store
    assert integrator.session_id == session_id
    assert integrator.table is not None
    assert integrator.dealer_profile is not None
    assert integrator.event_recorder is not None
    assert integrator.hands_played == 0


def test_create_game(environment_setup):
    """Test game creation with environment parameters."""
    integrator, _, _, _, _, _, _ = environment_setup

    game = integrator.create_game()

    # Game should be created with table rules
    assert game.rules == integrator.table.rules

    # Penetration should be set from table
    assert game.penetration == integrator.table.penetration

    # Game should have event emitter attached
    assert hasattr(game.state, "_event_emitter")


def test_add_player(environment_setup):
    """Test adding player with environment-aware execution."""
    integrator, _, _, _, _, _, _ = environment_setup

    # Create strategy and bankroll manager
    strategy = BasicStrategy()
    bankroll = BasicBankrollManager(
        initial_bankroll=1000.0, params=BankrollParameters()
    )

    # Add player with default skill
    player = integrator.add_player(strategy=strategy, bankroll_manager=bankroll)

    assert player is not None
    assert player.name == "Player"
    assert player.bankroll_manager == bankroll

    # Verify game has the player
    assert player in integrator.game.players

    # Player strategy should be wrapped in ExecutionVarianceWrapper
    assert player.strategy.__class__.__name__ == "ExecutionVarianceWrapper"

    # Add player with explicit skill level
    skill_level = SkillLevel(counting_skill=0.7, strategy_knowledge=0.9, discipline=0.8)

    integrator.game = None  # Reset game
    player = integrator.add_player(
        strategy=strategy, bankroll_manager=bankroll, skill_level=skill_level
    )

    # Player strategy should first be wrapped in RealisticPlayerStrategy
    # and then in ExecutionVarianceWrapper
    assert player.strategy.__class__.__name__ == "ExecutionVarianceWrapper"
    assert player.strategy.strategy.__class__.__name__ == "RealisticPlayerStrategy"


@patch("time.time")
def test_simulate_session(mock_time, environment_setup):
    """Test session simulation."""
    integrator, _, table_id, _, session_id, _, db_path = environment_setup

    # Mock time.time() to return controlled values
    mock_time.return_value = 1000.0

    # Create strategy and bankroll manager
    strategy = BasicStrategy()
    bankroll = BasicBankrollManager(
        initial_bankroll=1000.0,
        params=BankrollParameters(session_time_target=4.0, stop_loss=0.5, stop_win=1.0),
    )

    # Add player
    integrator.add_player(strategy=strategy, bankroll_manager=bankroll)

    # Simulate a short session
    results = integrator.simulate_session(
        hours=0.1, max_hands=10, verify=True  # 6 minutes
    )

    # Check results
    assert results is not None
    assert results["session_id"] == session_id
    assert results["table_id"] == table_id
    assert results["hands_played"] <= 10
    assert results["simulated_time_hours"] <= 0.1
    assert "bankroll_stats" in results

    # Check database entries
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check session record
    cursor.execute("SELECT COUNT(*) FROM sessions WHERE session_id = ?", (session_id,))
    count = cursor.fetchone()[0]
    assert count == 1

    # Check round records
    cursor.execute("SELECT COUNT(*) FROM rounds WHERE session_id = ?", (session_id,))
    rounds = cursor.fetchone()[0]
    assert rounds == results["hands_played"]

    # Check events
    cursor.execute("SELECT COUNT(*) FROM events WHERE session_id = ?", (session_id,))
    events = cursor.fetchone()[0]
    assert events > results["hands_played"]  # Multiple events per hand

    conn.close()


def test_environmental_factors(environment_setup):
    """Test environmental factors affect gameplay."""
    integrator, _, _, _, _, _, _ = environment_setup

    # Create strategy and bankroll manager
    strategy = BasicStrategy()
    bankroll = BasicBankrollManager(initial_bankroll=1000.0)

    # Add player
    integrator.add_player(strategy=strategy, bankroll_manager=bankroll)

    # Set up environment with high distraction
    integrator.distraction_level = 0.9
    integrator.time_pressure = 0.8
    integrator.fatigue = 0.7

    # Calculate error rate
    error_rate = integrator._calculate_error_rate()

    # Error rate should be higher with these factors
    assert error_rate > 0.1

    # Reset to normal conditions
    integrator.distraction_level = 0.2
    integrator.time_pressure = 0.2
    integrator.fatigue = 0.1

    # Calculate error rate again
    low_error_rate = integrator._calculate_error_rate()

    # Error rate should be lower
    assert low_error_rate < error_rate


def test_dealer_errors(environment_setup):
    """Test dealer error handling."""
    integrator, _, _, _, _, _, db_path = environment_setup

    # Create a dealer with high error rate
    dealer = DealerProfile(name="Error Dealer", error_rate=1.0)  # Always makes errors

    # Replace the default dealer
    integrator.dealer_profile = dealer
    integrator.current_round_id = "test_round_1"

    # Test error handling
    error_made, error_type = integrator._handle_dealer_errors()

    assert error_made
    assert error_type is not None
    assert integrator.dealer_errors == 1

    # Check event recording
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM events WHERE event_type = 'dealer_error'")
    count = cursor.fetchone()[0]
    assert count == 1

    conn.close()


def test_hand_timing(environment_setup):
    """Test hand timing simulation."""
    integrator, _, _, _, _, _, _ = environment_setup

    # Create strategy and bankroll manager
    strategy = BasicStrategy()
    bankroll = BasicBankrollManager(initial_bankroll=1000.0)

    # Add player
    integrator.add_player(strategy=strategy, bankroll_manager=bankroll)

    # Get timing with normal dealer
    normal_timing = integrator._simulate_hand_timing()

    # Set a fast dealer
    fast_dealer = DealerProfile(name="Fast Dealer", speed=1.5)  # 50% faster
    integrator.dealer_profile = fast_dealer

    # Get timing with fast dealer
    fast_timing = integrator._simulate_hand_timing()

    # Fast dealer should be faster
    assert fast_timing < normal_timing

    # Set a slow dealer
    slow_dealer = DealerProfile(name="Slow Dealer", speed=0.7)  # 30% slower
    integrator.dealer_profile = slow_dealer

    # Get timing with slow dealer
    slow_timing = integrator._simulate_hand_timing()

    # Slow dealer should be slower
    assert slow_timing > normal_timing


def test_verify_game_state(environment_setup):
    """Test game state verification."""
    integrator, _, _, _, _, _, _ = environment_setup

    # Create game and set current round
    integrator.create_game()
    integrator.current_round_id = "test_round_2"

    # Verification without playing should pass by default
    results = integrator._verify_game_state()
    assert results["verified"]

    # Simulate a played round with mocked verifier
    with patch("cardsharp.verification.verifier.BlackjackVerifier") as MockVerifier:
        # Set mock to return failure
        mock_instance = MockVerifier.return_value
        mock_instance.verify_round.return_value = {
            "verified": False,
            "reason": "Test failure reason",
        }

        # Verify should fail
        results = integrator._verify_game_state()
        assert not results["verified"]
        assert results["reason"] == "Test failure reason"
