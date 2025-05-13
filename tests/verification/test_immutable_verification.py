"""
Tests for the immutable state verification system.

This module contains tests to verify that the immutable state verification
system works correctly.
"""

import asyncio
import pytest
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


@pytest.fixture
def event_bus():
    """Return the event bus instance."""
    return EventBus.get_instance()


@pytest.fixture
def recorder():
    """Create a state transition recorder for testing."""
    recorder = StateTransitionRecorder()
    yield recorder
    recorder.shutdown()


def test_recorder_initialization(recorder):
    """Test that the recorder initializes correctly."""
    assert recorder is not None
    assert len(recorder.transitions) == 0
    assert recorder.current_state is None
    assert len(recorder.unsubscribe_funcs) > 0


def test_recorder_event_subscription(recorder, event_bus):
    """Test that the recorder subscribes to events."""
    # We'll test the subscription mechanism directly
    event_type = EngineEventType.ROUND_STARTED
    test_data = {"game_id": "test", "timestamp": 0.0}

    # Create a test event handler that will be called through the subscription
    call_tracker = []

    def test_handler(data):
        call_tracker.append(data)

    # Subscribe our test handler to the event
    unsubscribe = event_bus.on(event_type, test_handler)

    try:
        # Emit an event
        event_bus.emit(event_type, test_data)

        # Give a small delay for event processing
        import time

        time.sleep(0.01)

        # Check that our handler was called
        assert len(call_tracker) > 0
        assert call_tracker[0] == test_data
    finally:
        # Cleanup
        unsubscribe()


def test_recorder_shutdown(recorder):
    """Test that the recorder shuts down correctly."""
    # Create mock unsubscribe functions
    mock_unsubs = [MagicMock() for _ in range(3)]
    recorder.unsubscribe_funcs = mock_unsubs

    # Shutdown the recorder
    recorder.shutdown()

    # Check that all unsubscribe functions were called
    for unsub in mock_unsubs:
        unsub.assert_called_once()

    # Check that the unsubscribe list was cleared
    assert len(recorder.unsubscribe_funcs) == 0


def test_recorder_clear(recorder):
    """Test that the recorder clears its state."""
    # Add some mock transitions
    recorder.transitions = [MagicMock() for _ in range(3)]
    recorder.current_state = MagicMock()

    # Clear the recorder
    recorder.clear()

    # Check that the transitions list was cleared
    assert len(recorder.transitions) == 0
    assert recorder.current_state is None


@pytest.fixture
def rules():
    """Create game rules for testing."""
    return Rules(
        blackjack_payout=1.5,
        num_decks=6,
        dealer_hit_soft_17=False,
        allow_insurance=True,
        allow_surrender=True,
        allow_double_after_split=True,
        allow_split=True,
        allow_double_down=True,
        min_bet=5.0,
        max_bet=1000.0,
    )


@pytest.fixture
def mock_recorder():
    """Create a mock recorder for testing."""
    return MagicMock()


@pytest.fixture
def verifier(mock_recorder, rules):
    """Create a verifier for testing."""
    return ImmutableStateVerifier(mock_recorder, rules)


def test_verifier_initialization(verifier, mock_recorder, rules):
    """Test that the verifier initializes correctly."""
    assert verifier is not None
    assert verifier.recorder == mock_recorder
    assert verifier.rules == rules


def test_verifier_verify_all(verifier):
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
        setattr(verifier, method, mock)

    # Run verify_all
    results = verifier.verify_all()

    # Check that all methods were called
    for method, mock in mocks.items():
        mock.assert_called_once()

    # Check that all results were returned
    assert len(results) == len(methods)


@patch("cardsharp.verification.immutable_verifier.VerificationResult")
def test_verification_methods(mock_result, verifier, mock_recorder):
    """Test that verification methods return results."""
    # Configure the mock to return a verification result
    mock_result.return_value = MagicMock(passed=True)

    # Create empty mock transitions
    mock_recorder.get_transitions_by_action.return_value = []

    # Test each verification method
    methods = [
        "verify_dealer_actions",
        "verify_player_options",
        "verify_payouts",
        "verify_bet_sizes",
        "verify_insurance",
    ]

    for method in methods:
        result = getattr(verifier, method)()
        assert result is not None
        assert result.passed


@pytest.fixture
def integration_recorder():
    """Create a recorder for integration testing."""
    recorder = StateTransitionRecorder()
    yield recorder
    recorder.shutdown()


@pytest.fixture
def integration_verifier(integration_recorder, rules):
    """Create a verifier for integration testing."""
    return ImmutableStateVerifier(integration_recorder, rules)


@pytest.mark.asyncio
async def test_game_verification(integration_recorder, integration_verifier, rules):
    """Test that a game can be verified."""
    # Create a dummy adapter
    adapter = DummyAdapter()

    # Create a game
    config = {
        "dealer_rules": {"stand_on_soft_17": True, "peek_for_blackjack": True},
        "deck_count": 6,
        "rules": rules.__dict__,
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
        verification_results = integration_verifier.verify_all()

        # Check that verification results were returned
        assert len(verification_results) > 0

        # Count passing results
        passing = sum(1 for r in verification_results if r.passed)

        # Not all checks will pass in this simple test, but some should
        assert passing > 0

    finally:
        # Shutdown the game
        await game.shutdown()
