"""
Test the database schema for the verification system.

This test ensures that the database schema is created correctly.
"""

import pytest
import tempfile
import os
import sqlite3
from pathlib import Path

from cardsharp.verification.schema import initialize_database, SCHEMA_SQL


@pytest.fixture
def test_db():
    """Set up a test database."""
    db_file = tempfile.NamedTemporaryFile(delete=False).name
    conn = sqlite3.connect(db_file)

    # Create the schema
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    yield conn, db_file

    # Clean up after tests
    conn.close()
    if os.path.exists(db_file):
        os.remove(db_file)


def test_tables_created(test_db):
    """Test that all expected tables are created."""
    conn, _ = test_db
    cursor = conn.cursor()

    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    # Check for required tables
    expected_tables = [
        "sessions",
        "rounds",
        "player_hands",
        "actions",
        "count_tracking",
        "verification_results",
        "statistical_analysis",
        "events",
        "performance_metrics",
        "session_mapping",
        "round_mapping",
        "hand_mapping",
    ]

    for table in expected_tables:
        assert table in tables, f"Table {table} was not created"


def test_session_mapping_structure(test_db):
    """Test that the session_mapping table has the correct structure."""
    conn, _ = test_db
    cursor = conn.cursor()

    # Get info about the table
    cursor.execute("PRAGMA table_info(session_mapping)")
    columns = {row[1]: row for row in cursor.fetchall()}

    # Check columns
    assert "mapping_id" in columns
    assert "external_id" in columns
    assert "internal_id" in columns
    assert "created_at" in columns

    # Check foreign key
    cursor.execute("PRAGMA foreign_key_list(session_mapping)")
    foreign_keys = cursor.fetchall()

    # Should have a foreign key to sessions.session_id
    assert len(foreign_keys) == 1
    fk = foreign_keys[0]
    assert fk[2] == "sessions"  # References table
    assert fk[3] == "internal_id"  # From column
    assert fk[4] == "session_id"  # To column


def test_round_mapping_structure(test_db):
    """Test that the round_mapping table has the correct structure."""
    conn, _ = test_db
    cursor = conn.cursor()

    # Get info about the table
    cursor.execute("PRAGMA table_info(round_mapping)")
    columns = {row[1]: row for row in cursor.fetchall()}

    # Check columns
    assert "mapping_id" in columns
    assert "external_id" in columns
    assert "internal_id" in columns
    assert "created_at" in columns

    # Check foreign key
    cursor.execute("PRAGMA foreign_key_list(round_mapping)")
    foreign_keys = cursor.fetchall()

    # Should have a foreign key to rounds.round_id
    assert len(foreign_keys) == 1
    fk = foreign_keys[0]
    assert fk[2] == "rounds"  # References table
    assert fk[3] == "internal_id"  # From column
    assert fk[4] == "round_id"  # To column


def test_indexes_created(test_db):
    """Test that all expected indexes are created."""
    conn, _ = test_db
    cursor = conn.cursor()

    # Get all indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = [row[0] for row in cursor.fetchall()]

    # Check for required indexes related to mapping
    expected_indexes = [
        "idx_session_mapping_external",
        "idx_round_mapping_external",
        "idx_hand_mapping_external",
        "idx_events_session",
        "idx_events_round",
        "idx_events_type",
    ]

    for index in expected_indexes:
        assert index in indexes, f"Index {index} was not created"
