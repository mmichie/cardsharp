"""
Tests for the verification system.

This module contains tests for the blackjack verification system.
"""

import os
import pytest
import tempfile
import sqlite3
import json
from unittest.mock import MagicMock, patch

from cardsharp.verification.schema import initialize_database
from cardsharp.verification.events import EventType, GameEvent, EventEmitter
from cardsharp.verification.storage import SQLiteEventStore
from cardsharp.verification.verifier import (
    VerificationType,
    VerificationResult,
    BlackjackVerifier,
)
from cardsharp.verification.statistics import StatisticalValidator
from cardsharp.verification.main import (
    VerificationSystem,
    init_verification,
    get_verification_system,
)
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.state_events import (
    patch_game_states,
    EventEmittingGameState,
    EventEmittingPlacingBetsState,
)


@pytest.fixture
def test_db():
    """Set up a test database."""
    db_fd, db_path = tempfile.mkstemp()
    conn = initialize_database(db_path)

    yield conn, db_path

    conn.close()
    os.close(db_fd)
    os.unlink(db_path)


def test_database_initialization(test_db):
    """Test that the database is initialized correctly."""
    conn, _ = test_db

    # Check that required tables exist
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name IN (
            'sessions', 'rounds', 'player_hands', 'actions',
            'count_tracking', 'verification_results', 'statistical_analysis'
        )
        """
    )
    tables = [row[0] for row in cursor.fetchall()]

    assert len(tables) == 7, "Not all expected tables were created"

    # Check that the tables have the expected columns
    cursor.execute("PRAGMA table_info(sessions)")
    columns = [row[1] for row in cursor.fetchall()]

    expected_columns = [
        "session_id",
        "timestamp",
        "rules_config",
        "num_decks",
        "penetration",
        "use_csm",
        "player_count",
        "seed",
        "notes",
    ]

    for column in expected_columns:
        assert column in columns, f"Column {column} missing from sessions table"


@pytest.fixture
def event_emitter():
    """Set up an event emitter."""
    emitter = EventEmitter()
    emitter.set_context("test_game", "test_round")

    return emitter


def test_event_emission(event_emitter):
    """Test that events are emitted correctly."""
    emitter = event_emitter
    events = []

    def event_listener(event):
        """Record events for testing."""
        events.append(event)

    # Add a listener
    emitter.add_listener(EventType.GAME_START, event_listener)

    # Emit an event
    emitter.emit(EventType.GAME_START, {"test": "data"})

    # Check that the event was received
    assert len(events) == 1
    assert events[0].event_type == EventType.GAME_START
    assert events[0].data["test"] == "data"
    assert events[0].game_id == "test_game"
    assert events[0].round_id == "test_round"


def test_listener_removal(event_emitter):
    """Test that listeners can be removed."""
    emitter = event_emitter
    events = []

    def event_listener(event):
        """Record events for testing."""
        events.append(event)

    # Add a listener
    emitter.add_listener(EventType.GAME_START, event_listener)

    # Remove the listener
    emitter.remove_listener(EventType.GAME_START, event_listener)

    # Emit an event
    emitter.emit(EventType.GAME_START, {"test": "data"})

    # Check that no events were received
    assert len(events) == 0


@pytest.fixture
def sqlite_event_store():
    """Set up a test database and event store."""
    db_fd, db_path = tempfile.mkstemp()
    event_store = SQLiteEventStore(db_path)

    # Initialize the database with schema
    cursor = event_store.conn.cursor()
    from cardsharp.verification.schema import SCHEMA_SQL

    cursor.executescript(SCHEMA_SQL)
    event_store.conn.commit()

    yield event_store

    event_store.close()
    os.close(db_fd)
    os.unlink(db_path)


def test_create_session(sqlite_event_store):
    """Test that a session can be created."""
    event_store = sqlite_event_store

    # Create a session
    session_id = event_store.create_session(
        rules_config={"test": "config"},
        num_decks=6,
        penetration=0.75,
        use_csm=False,
        player_count=1,
    )

    # Check that the session was created
    assert session_id is not None

    # Check that the session has the expected values
    cursor = event_store.conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    session = cursor.fetchone()

    assert session is not None
    assert json.loads(session["rules_config"]) == {"test": "config"}
    assert session["num_decks"] == 6
    assert session["penetration"] == 0.75
    assert session["use_csm"] == False
    assert session["player_count"] == 1


def test_create_round(sqlite_event_store):
    """Test that a round can be created."""
    event_store = sqlite_event_store

    # Create a session
    session_id = event_store.create_session(
        rules_config={"test": "config"},
        num_decks=6,
        penetration=0.75,
        use_csm=False,
        player_count=1,
    )

    # Create a round
    round_id = event_store.create_round(
        session_id=session_id,
        round_number=1,
        dealer_up_card="A of ♥",
        dealer_hole_card="10 of ♠",
        shuffle_occurred=True,
    )

    # Check that the round was created
    assert round_id is not None

    # Check that the round has the expected values
    cursor = event_store.conn.cursor()
    cursor.execute("SELECT * FROM rounds WHERE round_id = ?", (round_id,))
    round_data = cursor.fetchone()

    assert round_data is not None
    assert round_data["session_id"] == session_id
    assert round_data["round_number"] == 1
    assert round_data["dealer_up_card"] == "A of ♥"
    assert round_data["dealer_hole_card"] == "10 of ♠"
    assert round_data["shuffle_occurred"] == True


@pytest.fixture
def blackjack_verifier(sqlite_event_store):
    """Set up a test database and verifier."""
    event_store = sqlite_event_store
    verifier = BlackjackVerifier(event_store)

    # Set up test data
    rules = Rules(
        dealer_hit_soft_17=True,
        allow_split=True,
        allow_double_down=True,
        allow_insurance=True,
        allow_surrender=True,
        blackjack_payout=1.5,
    )

    # Create a session
    session_id = event_store.create_session(
        rules_config=vars(rules),
        num_decks=6,
        penetration=0.75,
        use_csm=False,
        player_count=1,
    )

    # Create a round
    round_id = event_store.create_round(
        session_id=session_id,
        round_number=1,
        dealer_up_card="A of ♥",
        dealer_hole_card="10 of ♠",
        shuffle_occurred=True,
    )

    return verifier, event_store, session_id, round_id, rules


def test_verify_dealer_actions(blackjack_verifier):
    """Test that dealer actions are verified correctly."""
    verifier, event_store, session_id, round_id, rules = blackjack_verifier

    # Create a player hand
    hand_id = event_store.create_player_hand(
        round_id=round_id, player_id=1, seat_position=1, initial_bet=10.0
    )

    # Update the round with dealer's final hand
    event_store.update_round_final_hand(
        round_id=round_id, final_hand=["A of ♥", "10 of ♠"], final_value=21
    )

    # Record a dealer action
    action_id = event_store.record_action(
        round_id=round_id,
        hand_id=None,
        actor="dealer",
        actor_id=0,
        action_type="stand",
        hand_value_before=21,
        hand_value_after=21,
    )

    # Verify the round
    result = verifier._verify_dealer_actions(round_id, rules)

    # Check that the verification passed
    assert result.passed


@pytest.fixture
def statistical_validator(sqlite_event_store):
    """Set up a test database and validator."""
    event_store = sqlite_event_store
    validator = StatisticalValidator(event_store)

    # Create a session
    session_id = event_store.create_session(
        rules_config={"test": "config"},
        num_decks=6,
        penetration=0.75,
        use_csm=False,
        player_count=1,
    )

    # Create a round
    round_id = event_store.create_round(session_id=session_id, round_number=1)

    # Create a player hand
    hand_id = event_store.create_player_hand(
        round_id=round_id, player_id=1, seat_position=1, initial_bet=10.0
    )

    # Update the hand with result
    event_store.update_player_hand_result(
        hand_id=hand_id,
        final_value=20,
        is_soft=False,
        is_blackjack=False,
        is_busted=False,
        result="win",
        payout=20.0,
    )

    return validator, event_store, session_id, round_id


def test_calculate_expected_value(statistical_validator):
    """Test that expected value is calculated correctly."""
    validator, event_store, session_id, round_id = statistical_validator

    # Calculate expected value
    result = validator.calculate_expected_value(session_id)

    # Check that the expected value is calculated
    assert (
        result["expected_value"] == 1.0
    )  # (payout - bet) / bet = (20 - 10) / 10 = 1.0
    assert result["sample_size"] == 1


@pytest.fixture
def verification_system():
    """Set up a test database and verification system."""
    db_fd, db_path = tempfile.mkstemp()

    # Initialize the database with schema first
    conn = sqlite3.connect(db_path)
    from cardsharp.verification.schema import SCHEMA_SQL

    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()

    # Now initialize the verification system
    system = init_verification(db_path)

    yield system

    system.close()
    os.close(db_fd)
    os.unlink(db_path)


def test_event_handling(verification_system):
    """Test that events are handled correctly."""
    system = verification_system

    # Create an event emitter
    emitter = EventEmitter()
    emitter.set_context("test_game", "test_round")

    # Connect the emitter to the system
    system.connect_events(emitter)

    # Create a mock event
    event = GameEvent(
        event_type=EventType.GAME_START,
        game_id="test_game",
        round_id="test_round",
        data={
            "rules_config": {"num_decks": 6, "penetration": 0.75, "use_csm": False},
            "player_count": 1,
        },
    )

    # Handle the event
    system.handle_event(event)

    # Check that a session was created
    assert system.current_session_id is not None


def test_state_event_emission():
    """Test that state events are emitted correctly."""
    # Apply state patches
    patch_game_states()

    # Create a mock game
    game = MagicMock()
    game.stats.games_played = 0
    game.players = []

    # Create an event state
    state = EventEmittingPlacingBetsState()

    # Create a listener
    events = []

    def listener(event):
        events.append(event)

    # Connect the listener
    state.add_listener(EventType.BET_PLACED, listener)

    # Set context
    state.set_context(game, 1)

    # Create a mock player
    player = MagicMock()
    player.name = "Test Player"

    # Add the player to the game
    game.players.append(player)

    # Place a bet
    with patch.object(state, "place_bet", wraps=state.place_bet):
        state.place_bet(game, player, 10)

    # Check that an event was emitted
    assert len(events) == 1
    assert events[0].event_type == EventType.BET_PLACED
    assert events[0].data["player_name"] == "Test Player"
    assert events[0].data["amount"] == 10
