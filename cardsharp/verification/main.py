"""
Main module for the verification system.

This module provides functions for initializing the verification system,
connecting event emission to database storage, and running verifications.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import os
from pathlib import Path

from cardsharp.verification.events import EventType, EventEmitter, EventRecorder
from cardsharp.verification.schema import initialize_database, DatabaseInitializer
from cardsharp.verification.storage import SQLiteEventStore
from cardsharp.verification.verifier import BlackjackVerifier
from cardsharp.verification.statistics import StatisticalValidator
from cardsharp.blackjack.state_events import patch_game_states


class VerificationSystem:
    """
    Main class for the verification system.

    This class provides methods for initializing the verification system,
    connecting event emission to database storage, and running verifications.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the verification system.

        Args:
            db_path: Optional path to the database file. If None, uses the default path.
        """
        self.logger = logging.getLogger(__name__)

        # Initialize the database
        self.event_store = SQLiteEventStore(db_path)

        # Create verifiers
        self.verifier = BlackjackVerifier(self.event_store)
        self.statistical_validator = StatisticalValidator(self.event_store)

        # Apply patches to game states
        patch_game_states()

        # Create an event recorder
        self.event_recorder = EventRecorder()

        # Keep track of the current session
        self.current_session_id = None

        self.logger.info("Verification system initialized")

    def connect_events(self, emitter: EventEmitter) -> None:
        """
        Connect an event emitter to the verification system.

        Args:
            emitter: The event emitter to connect
        """
        # Connect all event types
        for event_type in EventType:
            emitter.add_listener(event_type, self.handle_event)

        self.logger.info("Connected events from emitter %s", emitter)

    def handle_event(self, event) -> None:
        """
        Handle an event from an emitter.

        Args:
            event: The event to handle
        """
        # Record the event
        self.event_recorder.record_event(event)

        # Store the event in the database
        self.event_store.record_event(event)

        # If this is a game start event, save the session ID
        if event.event_type == EventType.GAME_START:
            # The session_id might have been created by record_event
            cursor = self.event_store.conn.cursor()
            cursor.execute("SELECT MAX(session_id) FROM sessions")
            self.current_session_id = cursor.fetchone()[0]

            self.logger.info("Started new session %s", self.current_session_id)

    def verify_current_session(self) -> Dict[str, Any]:
        """
        Verify the current session.

        Returns:
            A dictionary with the verification results
        """
        if not self.current_session_id:
            self.logger.warning("No current session to verify")
            return {"error": "No current session"}

        # Run rule verifications
        rule_results = self.verifier.verify_session(self.current_session_id)

        # Run statistical validations
        stat_results = self.statistical_validator.run_all_analyses(
            self.current_session_id
        )

        self.logger.info("Verified session %s", self.current_session_id)

        return {
            "session_id": self.current_session_id,
            "rule_verifications": [str(result) for result in rule_results],
            "statistical_validations": stat_results,
        }

    def close(self) -> None:
        """Close the verification system and its resources."""
        if self.event_store:
            self.event_store.close()

        self.logger.info("Verification system closed")


# Singleton instance for easy access
_instance = None


def init_verification(db_path: Optional[str] = None) -> VerificationSystem:
    """
    Initialize the verification system.

    Args:
        db_path: Optional path to the database file. If None, uses the default path.

    Returns:
        The initialized verification system
    """
    global _instance

    if _instance is None:
        _instance = VerificationSystem(db_path)

    return _instance


def get_verification_system() -> Optional[VerificationSystem]:
    """
    Get the verification system instance.

    Returns:
        The verification system instance, or None if not initialized
    """
    return _instance


def verify_session(session_id: int) -> Dict[str, Any]:
    """
    Verify a specific session.

    Args:
        session_id: The ID of the session to verify

    Returns:
        A dictionary with the verification results
    """
    system = get_verification_system()

    if not system:
        return {"error": "Verification system not initialized"}

    # Run rule verifications
    rule_results = system.verifier.verify_session(session_id)

    # Run statistical validations
    stat_results = system.statistical_validator.run_all_analyses(session_id)

    return {
        "session_id": session_id,
        "rule_verifications": [str(result) for result in rule_results],
        "statistical_validations": stat_results,
    }
