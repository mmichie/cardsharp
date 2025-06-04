"""
Test verification storage and mapping functionality.

These tests ensure that the storage and mapping features work correctly for the
verification system.
"""

import pytest
import tempfile
import os
import time
import json

from cardsharp.verification.events import EventType, GameEvent
from cardsharp.verification.storage import SQLiteEventStore


@pytest.fixture
def event_store():
    """Set up a test database and event store."""
    db_file = tempfile.NamedTemporaryFile(delete=False).name
    store = SQLiteEventStore(db_file)

    # Initialize the database with schema
    cursor = store.conn.cursor()
    from cardsharp.verification.schema import SCHEMA_SQL

    cursor.executescript(SCHEMA_SQL)
    store.conn.commit()

    yield store, db_file

    # Clean up after tests
    store.close()
    if os.path.exists(db_file):
        os.remove(db_file)


@pytest.fixture
def session_data(event_store):
    """Create a test session with basic data."""
    store, _ = event_store

    # Create a test session
    session_id = f"test_session_{int(time.time())}"
    test_info = {
        "rules": {"hit_soft_17": True, "blackjack_pays": 1.5},
        "num_decks": 6,
        "penetration": 0.75,
        "use_csm": False,
        "players": 3,
        "notes": "Test session",
    }
    db_session_id = store.record_session(session_id, test_info)

    return store, session_id, db_session_id, test_info


@pytest.fixture
def round_data(session_data):
    """Create a test round with basic data."""
    store, session_id, _, _ = session_data

    # Create a test round
    round_id = f"test_round_{int(time.time())}"
    round_details = {
        "round_number": 1,
        "dealer_up_card": "A♠",
        "dealer_hole_card": "10♥",
        "dealer_final_hand": ["A♠", "10♥"],
        "dealer_final_value": 21,
        "shuffle_occurred": False,
    }
    db_round_id = store.record_round(round_id, session_id, round_details)

    return store, session_id, round_id, db_round_id, round_details


def test_session_mapping(session_data):
    """Test that session mapping works correctly."""
    store, session_id, db_session_id, _ = session_data

    # Check if the session was created
    assert db_session_id is not None

    # Get internal ID via direct query
    cursor = store.conn.cursor()
    cursor.execute(
        "SELECT internal_id FROM session_mapping WHERE external_id = ?",
        (session_id,),
    )
    result = cursor.fetchone()
    assert result is not None

    # The internal ID should match the returned ID
    assert result[0] == db_session_id


def test_round_mapping(round_data):
    """Test that round mapping works correctly."""
    store, _, round_id, db_round_id, _ = round_data

    # Check if the round was created
    assert db_round_id is not None

    # Get internal ID via direct query
    cursor = store.conn.cursor()
    cursor.execute(
        "SELECT internal_id FROM round_mapping WHERE external_id = ?",
        (round_id,),
    )
    result = cursor.fetchone()
    assert result is not None

    # The internal ID should match the returned ID
    assert result[0] == db_round_id


def test_store_event(round_data):
    """Test storing events with proper ID mappings."""
    store, session_id, round_id, _, _ = round_data

    # Create a test event
    event = GameEvent(
        event_type=EventType.PLAYER_ACTION,
        game_id=session_id,
        round_id=round_id,
        data={
            "player_decision": "hit",
            "player_hand": "10♥,5♦",
            "dealer_upcard": "A♠",
        },
    )

    # Store the event
    event_id = store.store_event(event)
    assert event_id is not None

    # Query the events table directly
    cursor = store.conn.cursor()
    cursor.execute(
        """
        SELECT * FROM events
        WHERE session_id = ? AND round_id = ? AND event_type = ?
        """,
        (session_id, round_id, "PLAYER_ACTION"),
    )

    rows = cursor.fetchall()
    assert len(rows) == 1

    # Convert row to dict and check fields
    event_row = dict(rows[0])
    event_data = json.loads(event_row["event_data"])
    assert event_row["event_type"] == "PLAYER_ACTION"
    assert event_data["player_decision"] == "hit"
    assert event_data["player_hand"] == "10♥,5♦"
    assert event_data["dealer_upcard"] == "A♠"


def test_record_statistical_analysis(session_data):
    """Test recording statistical analysis with mappings."""
    store, session_id, _, _ = session_data

    # Create test data
    analysis_type = "win_rate"
    params = {"hands": 1000, "decks": 6}
    result_data = {"win_rate": 0.42, "std_dev": 0.05}
    confidence = {"lower": 0.40, "upper": 0.44, "level": 0.95}

    # Record the analysis
    analysis_id = store.record_statistical_analysis(
        session_id, analysis_type, params, result_data, confidence, True
    )
    assert analysis_id is not None

    # Retrieve the analysis
    cursor = store.conn.cursor()
    cursor.execute(
        """
        SELECT * FROM statistical_analysis
        WHERE analysis_id = ?
        """,
        (analysis_id,),
    )
    result_row = cursor.fetchone()
    assert result_row is not None

    # Convert to dictionary
    analysis = dict(result_row)

    # Check fields
    assert analysis["analysis_type"] == analysis_type
    assert json.loads(analysis["params"]) == params
    assert json.loads(analysis["result"]) == result_data
    assert json.loads(analysis["confidence_interval"]) == confidence
    assert bool(analysis["passed"]) is True
