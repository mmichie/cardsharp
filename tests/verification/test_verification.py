"""
Tests for the verification system.

This module contains tests for the blackjack verification system.
"""

import os
import unittest
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


class TestVerificationDatabase(unittest.TestCase):
    """Tests for the verification database."""

    def setUp(self):
        """Set up a test database."""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = initialize_database(self.db_path)

    def tearDown(self):
        """Clean up the test database."""
        self.conn.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_database_initialization(self):
        """Test that the database is initialized correctly."""
        # Check that required tables exist
        cursor = self.conn.cursor()
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

        self.assertEqual(len(tables), 7, "Not all expected tables were created")

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
            self.assertIn(
                column, columns, f"Column {column} missing from sessions table"
            )


class TestEventEmitter(unittest.TestCase):
    """Tests for the event emitter."""

    def setUp(self):
        """Set up an event emitter."""
        self.emitter = EventEmitter()
        self.emitter.set_context("test_game", "test_round")
        self.events = []

    def event_listener(self, event):
        """Record events for testing."""
        self.events.append(event)

    def test_event_emission(self):
        """Test that events are emitted correctly."""
        # Add a listener
        self.emitter.add_listener(EventType.GAME_START, self.event_listener)

        # Emit an event
        self.emitter.emit(EventType.GAME_START, {"test": "data"})

        # Check that the event was received
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0].event_type, EventType.GAME_START)
        self.assertEqual(self.events[0].data["test"], "data")
        self.assertEqual(self.events[0].game_id, "test_game")
        self.assertEqual(self.events[0].round_id, "test_round")

    def test_listener_removal(self):
        """Test that listeners can be removed."""
        # Add a listener
        self.emitter.add_listener(EventType.GAME_START, self.event_listener)

        # Remove the listener
        self.emitter.remove_listener(EventType.GAME_START, self.event_listener)

        # Emit an event
        self.emitter.emit(EventType.GAME_START, {"test": "data"})

        # Check that no events were received
        self.assertEqual(len(self.events), 0)


class TestSQLiteEventStore(unittest.TestCase):
    """Tests for the SQLite event store."""

    def setUp(self):
        """Set up a test database and event store."""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.event_store = SQLiteEventStore(self.db_path)

        # Initialize the database with schema
        cursor = self.event_store.conn.cursor()
        from cardsharp.verification.schema import SCHEMA_SQL

        cursor.executescript(SCHEMA_SQL)
        self.event_store.conn.commit()

    def tearDown(self):
        """Clean up the test database."""
        self.event_store.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_create_session(self):
        """Test that a session can be created."""
        # Create a session
        session_id = self.event_store.create_session(
            rules_config={"test": "config"},
            num_decks=6,
            penetration=0.75,
            use_csm=False,
            player_count=1,
        )

        # Check that the session was created
        self.assertIsNotNone(session_id)

        # Check that the session has the expected values
        cursor = self.event_store.conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        session = cursor.fetchone()

        self.assertIsNotNone(session)
        self.assertEqual(json.loads(session["rules_config"]), {"test": "config"})
        self.assertEqual(session["num_decks"], 6)
        self.assertEqual(session["penetration"], 0.75)
        self.assertEqual(session["use_csm"], False)
        self.assertEqual(session["player_count"], 1)

    def test_create_round(self):
        """Test that a round can be created."""
        # Create a session
        session_id = self.event_store.create_session(
            rules_config={"test": "config"},
            num_decks=6,
            penetration=0.75,
            use_csm=False,
            player_count=1,
        )

        # Create a round
        round_id = self.event_store.create_round(
            session_id=session_id,
            round_number=1,
            dealer_up_card="A of ♥",
            dealer_hole_card="10 of ♠",
            shuffle_occurred=True,
        )

        # Check that the round was created
        self.assertIsNotNone(round_id)

        # Check that the round has the expected values
        cursor = self.event_store.conn.cursor()
        cursor.execute("SELECT * FROM rounds WHERE round_id = ?", (round_id,))
        round_data = cursor.fetchone()

        self.assertIsNotNone(round_data)
        self.assertEqual(round_data["session_id"], session_id)
        self.assertEqual(round_data["round_number"], 1)
        self.assertEqual(round_data["dealer_up_card"], "A of ♥")
        self.assertEqual(round_data["dealer_hole_card"], "10 of ♠")
        self.assertEqual(round_data["shuffle_occurred"], True)


class TestBlackjackVerifier(unittest.TestCase):
    """Tests for the blackjack verifier."""

    def setUp(self):
        """Set up a test database and verifier."""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.event_store = SQLiteEventStore(self.db_path)

        # Initialize the database with schema
        cursor = self.event_store.conn.cursor()
        from cardsharp.verification.schema import SCHEMA_SQL

        cursor.executescript(SCHEMA_SQL)
        self.event_store.conn.commit()

        self.verifier = BlackjackVerifier(self.event_store)

        # Set up test data
        self.rules = Rules(
            dealer_hit_soft_17=True,
            allow_split=True,
            allow_double_down=True,
            allow_insurance=True,
            allow_surrender=True,
            blackjack_payout=1.5,
        )

        # Create a session
        self.session_id = self.event_store.create_session(
            rules_config=vars(self.rules),
            num_decks=6,
            penetration=0.75,
            use_csm=False,
            player_count=1,
        )

        # Create a round
        self.round_id = self.event_store.create_round(
            session_id=self.session_id,
            round_number=1,
            dealer_up_card="A of ♥",
            dealer_hole_card="10 of ♠",
            shuffle_occurred=True,
        )

    def tearDown(self):
        """Clean up the test database."""
        self.event_store.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_verify_dealer_actions(self):
        """Test that dealer actions are verified correctly."""
        # Create a player hand
        hand_id = self.event_store.create_player_hand(
            round_id=self.round_id, player_id=1, seat_position=1, initial_bet=10.0
        )

        # Update the round with dealer's final hand
        self.event_store.update_round_final_hand(
            round_id=self.round_id, final_hand=["A of ♥", "10 of ♠"], final_value=21
        )

        # Record a dealer action
        action_id = self.event_store.record_action(
            round_id=self.round_id,
            hand_id=None,
            actor="dealer",
            actor_id=0,
            action_type="stand",
            hand_value_before=21,
            hand_value_after=21,
        )

        # Verify the round
        result = self.verifier._verify_dealer_actions(self.round_id, self.rules)

        # Check that the verification passed
        self.assertTrue(result.passed)


class TestStatisticalValidator(unittest.TestCase):
    """Tests for the statistical validator."""

    def setUp(self):
        """Set up a test database and validator."""
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.event_store = SQLiteEventStore(self.db_path)

        # Initialize the database with schema
        cursor = self.event_store.conn.cursor()
        from cardsharp.verification.schema import SCHEMA_SQL

        cursor.executescript(SCHEMA_SQL)
        self.event_store.conn.commit()

        self.validator = StatisticalValidator(self.event_store)

        # Create a session
        self.session_id = self.event_store.create_session(
            rules_config={"test": "config"},
            num_decks=6,
            penetration=0.75,
            use_csm=False,
            player_count=1,
        )

        # Create a round
        self.round_id = self.event_store.create_round(
            session_id=self.session_id, round_number=1
        )

        # Create a player hand
        self.hand_id = self.event_store.create_player_hand(
            round_id=self.round_id, player_id=1, seat_position=1, initial_bet=10.0
        )

        # Update the hand with result
        self.event_store.update_player_hand_result(
            hand_id=self.hand_id,
            final_value=20,
            is_soft=False,
            is_blackjack=False,
            is_busted=False,
            result="win",
            payout=20.0,
        )

    def tearDown(self):
        """Clean up the test database."""
        self.event_store.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_calculate_expected_value(self):
        """Test that expected value is calculated correctly."""
        # Calculate expected value
        result = self.validator.calculate_expected_value(self.session_id)

        # Check that the expected value is calculated
        self.assertEqual(
            result["expected_value"], 1.0
        )  # (payout - bet) / bet = (20 - 10) / 10 = 1.0
        self.assertEqual(result["sample_size"], 1)


class TestVerificationSystem(unittest.TestCase):
    """Tests for the verification system."""

    def setUp(self):
        """Set up a test database and verification system."""
        self.db_fd, self.db_path = tempfile.mkstemp()

        # Initialize the database with schema first
        conn = sqlite3.connect(self.db_path)
        from cardsharp.verification.schema import SCHEMA_SQL

        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

        # Now initialize the verification system
        self.system = init_verification(self.db_path)

    def tearDown(self):
        """Clean up the test database."""
        self.system.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_event_handling(self):
        """Test that events are handled correctly."""
        # Create an event emitter
        emitter = EventEmitter()
        emitter.set_context("test_game", "test_round")

        # Connect the emitter to the system
        self.system.connect_events(emitter)

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
        self.system.handle_event(event)

        # Check that a session was created
        self.assertIsNotNone(self.system.current_session_id)


class TestStateEvents(unittest.TestCase):
    """Tests for the state event emitters."""

    def setUp(self):
        """Set up test objects."""
        # Apply state patches
        patch_game_states()

        # Create a mock game
        self.game = MagicMock()
        self.game.stats.games_played = 0
        self.game.players = []

        # Create an event state
        self.state = EventEmittingPlacingBetsState()

    def test_state_event_emission(self):
        """Test that state events are emitted correctly."""
        # Create a listener
        events = []

        def listener(event):
            events.append(event)

        # Connect the listener
        self.state.add_listener(EventType.BET_PLACED, listener)

        # Set context
        self.state.set_context(self.game, 1)

        # Create a mock player
        player = MagicMock()
        player.name = "Test Player"

        # Add the player to the game
        self.game.players.append(player)

        # Place a bet
        with patch.object(self.state, "place_bet", wraps=self.state.place_bet):
            self.state.place_bet(self.game, player, 10)

        # Check that an event was emitted
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, EventType.BET_PLACED)
        self.assertEqual(events[0].data["player_name"], "Test Player")
        self.assertEqual(events[0].data["amount"], 10)


if __name__ == "__main__":
    unittest.main()
