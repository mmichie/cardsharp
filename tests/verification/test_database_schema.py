"""
Test the database schema for the verification system.

This test ensures that the database schema is created correctly.
"""

import unittest
import tempfile
import os
import sqlite3
from pathlib import Path

from cardsharp.verification.schema import initialize_database, SCHEMA_SQL


class TestDatabaseSchema(unittest.TestCase):
    """Test suite for database schema functionality."""

    def setUp(self):
        """Set up a test database."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False).name
        self.conn = sqlite3.connect(self.db_file)

        # Create the schema
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def tearDown(self):
        """Clean up after tests."""
        self.conn.close()
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_tables_created(self):
        """Test that all expected tables are created."""
        cursor = self.conn.cursor()

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
            self.assertIn(table, tables, f"Table {table} was not created")

    def test_session_mapping_structure(self):
        """Test that the session_mapping table has the correct structure."""
        cursor = self.conn.cursor()

        # Get info about the table
        cursor.execute("PRAGMA table_info(session_mapping)")
        columns = {row[1]: row for row in cursor.fetchall()}

        # Check columns
        self.assertIn("mapping_id", columns)
        self.assertIn("external_id", columns)
        self.assertIn("internal_id", columns)
        self.assertIn("created_at", columns)

        # Check foreign key
        cursor.execute("PRAGMA foreign_key_list(session_mapping)")
        foreign_keys = cursor.fetchall()

        # Should have a foreign key to sessions.session_id
        self.assertEqual(len(foreign_keys), 1)
        fk = foreign_keys[0]
        self.assertEqual(fk[2], "sessions")  # References table
        self.assertEqual(fk[3], "internal_id")  # From column
        self.assertEqual(fk[4], "session_id")  # To column

    def test_round_mapping_structure(self):
        """Test that the round_mapping table has the correct structure."""
        cursor = self.conn.cursor()

        # Get info about the table
        cursor.execute("PRAGMA table_info(round_mapping)")
        columns = {row[1]: row for row in cursor.fetchall()}

        # Check columns
        self.assertIn("mapping_id", columns)
        self.assertIn("external_id", columns)
        self.assertIn("internal_id", columns)
        self.assertIn("created_at", columns)

        # Check foreign key
        cursor.execute("PRAGMA foreign_key_list(round_mapping)")
        foreign_keys = cursor.fetchall()

        # Should have a foreign key to rounds.round_id
        self.assertEqual(len(foreign_keys), 1)
        fk = foreign_keys[0]
        self.assertEqual(fk[2], "rounds")  # References table
        self.assertEqual(fk[3], "internal_id")  # From column
        self.assertEqual(fk[4], "round_id")  # To column

    def test_indexes_created(self):
        """Test that all expected indexes are created."""
        cursor = self.conn.cursor()

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
            self.assertIn(index, indexes, f"Index {index} was not created")


if __name__ == "__main__":
    unittest.main()
