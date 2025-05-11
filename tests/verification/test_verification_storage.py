"""
Test verification storage and mapping functionality.

These tests ensure that the storage and mapping features work correctly for the
verification system.
"""

import unittest
import tempfile
import os
import time
import json
from pathlib import Path

from cardsharp.verification.events import EventType, GameEvent
from cardsharp.verification.storage import SQLiteEventStore


class TestVerificationStorage(unittest.TestCase):
    """Test suite for verification storage functionality."""

    def setUp(self):
        """Set up a test database."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False).name
        self.store = SQLiteEventStore(self.db_file)

        # Initialize the database with schema
        cursor = self.store.conn.cursor()
        from cardsharp.verification.schema import SCHEMA_SQL

        cursor.executescript(SCHEMA_SQL)
        self.store.conn.commit()

        # Create a test session and round
        self.session_id = f"test_session_{int(time.time())}"
        self.test_info = {
            "rules": {"hit_soft_17": True, "blackjack_pays": 1.5},
            "num_decks": 6,
            "penetration": 0.75,
            "use_csm": False,
            "players": 3,
            "notes": "Test session",
        }
        self.db_session_id = self.store.record_session(self.session_id, self.test_info)

        # Create a test round
        self.round_id = f"test_round_{int(time.time())}"
        self.round_details = {
            "round_number": 1,
            "dealer_up_card": "A♠",
            "dealer_hole_card": "10♥",
            "dealer_final_hand": ["A♠", "10♥"],
            "dealer_final_value": 21,
            "shuffle_occurred": False,
        }
        self.db_round_id = self.store.record_round(
            self.round_id, self.session_id, self.round_details
        )

    def tearDown(self):
        """Clean up after tests."""
        self.store.close()
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_session_mapping(self):
        """Test that session mapping works correctly."""
        # Check if the session was created
        self.assertIsNotNone(self.db_session_id)

        # Get internal ID via direct query
        cursor = self.store.conn.cursor()
        cursor.execute(
            "SELECT internal_id FROM session_mapping WHERE external_id = ?",
            (self.session_id,),
        )
        result = cursor.fetchone()
        self.assertIsNotNone(result)

        # The internal ID should match the returned ID
        self.assertEqual(result[0], self.db_session_id)

    def test_round_mapping(self):
        """Test that round mapping works correctly."""
        # Check if the round was created
        self.assertIsNotNone(self.db_round_id)

        # Get internal ID via direct query
        cursor = self.store.conn.cursor()
        cursor.execute(
            "SELECT internal_id FROM round_mapping WHERE external_id = ?",
            (self.round_id,),
        )
        result = cursor.fetchone()
        self.assertIsNotNone(result)

        # The internal ID should match the returned ID
        self.assertEqual(result[0], self.db_round_id)

    def test_store_event(self):
        """Test storing events with proper ID mappings."""
        # Create a test event
        event = GameEvent(
            event_type=EventType.PLAYER_ACTION,
            game_id=self.session_id,
            round_id=self.round_id,
            data={
                "player_decision": "hit",
                "player_hand": "10♥,5♦",
                "dealer_upcard": "A♠",
            },
        )

        # Store the event
        event_id = self.store.store_event(event)
        self.assertIsNotNone(event_id)

        # Query the events table directly
        cursor = self.store.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM events
            WHERE session_id = ? AND round_id = ? AND event_type = ?
            """,
            (self.session_id, self.round_id, "PLAYER_ACTION"),
        )

        rows = cursor.fetchall()
        self.assertEqual(len(rows), 1)

        # Convert row to dict and check fields
        event_row = dict(rows[0])
        event_data = json.loads(event_row["event_data"])
        self.assertEqual(event_row["event_type"], "PLAYER_ACTION")
        self.assertEqual(event_data["player_decision"], "hit")
        self.assertEqual(event_data["player_hand"], "10♥,5♦")
        self.assertEqual(event_data["dealer_upcard"], "A♠")

    def test_record_statistical_analysis(self):
        """Test recording statistical analysis with mappings."""
        # Create test data
        analysis_type = "win_rate"
        params = {"hands": 1000, "decks": 6}
        result_data = {"win_rate": 0.42, "std_dev": 0.05}
        confidence = {"lower": 0.40, "upper": 0.44, "level": 0.95}

        # Record the analysis
        analysis_id = self.store.record_statistical_analysis(
            self.session_id, analysis_type, params, result_data, confidence, True
        )
        self.assertIsNotNone(analysis_id)

        # Retrieve the analysis
        cursor = self.store.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM statistical_analysis
            WHERE analysis_id = ?
            """,
            (analysis_id,),
        )
        result_row = cursor.fetchone()
        self.assertIsNotNone(result_row)

        # Convert to dictionary
        analysis = dict(result_row)

        # Check fields
        self.assertEqual(analysis["analysis_type"], analysis_type)
        self.assertEqual(json.loads(analysis["params"]), params)
        self.assertEqual(json.loads(analysis["result"]), result_data)
        self.assertEqual(json.loads(analysis["confidence_interval"]), confidence)
        self.assertTrue(bool(analysis["passed"]))


if __name__ == "__main__":
    unittest.main()
