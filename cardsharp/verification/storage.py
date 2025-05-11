"""
SQLite storage for blackjack game events and verification data.

This module provides classes for storing game events and verification data in SQLite.
"""

import sqlite3
import json
from typing import Any, Dict, List, Optional, Tuple, Union
import time
import datetime
from pathlib import Path
from enum import Enum

from cardsharp.verification.events import EventType, GameEvent
from cardsharp.verification.schema import initialize_database


class SQLiteEventStore:
    """
    Store and retrieve blackjack game events from SQLite.

    This class provides methods for storing game events in SQLite and retrieving them
    for analysis and verification.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the SQLite event store.

        Args:
            db_path: Optional path to the database file. If None, uses the default path.
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path if db_path else ":memory:")
        self.conn.row_factory = sqlite3.Row

    def initialize_database(self):
        """
        Initialize the database schema.

        Creates all necessary tables for storing game events, sessions, rounds,
        hands, and verification results if they don't already exist.
        """
        from cardsharp.verification.schema import SCHEMA_SQL

        cursor = self.conn.cursor()
        cursor.executescript(SCHEMA_SQL)
        self.conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()

    def store_event(self, event: GameEvent) -> int:
        """
        Store a game event in the database.

        Args:
            event: The game event to store

        Returns:
            The ID of the stored event
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO events (
                session_id, round_id, event_type, event_data, timestamp
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.game_id,
                event.round_id,
                event.event_type.name
                if isinstance(event.event_type, Enum)
                else event.event_type,
                json.dumps(event.data),
                event.timestamp,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def _serialize_card(self, card) -> str:
        """
        Serialize a card object to a string representation.

        Args:
            card: The card object to serialize

        Returns:
            A string representation of the card
        """
        return str(card)

    def _serialize_cards(self, cards) -> str:
        """
        Serialize a list of card objects to a JSON string.

        Args:
            cards: The list of card objects to serialize

        Returns:
            A JSON string representation of the cards
        """
        return json.dumps([self._serialize_card(card) for card in cards])

    def _serialize_actions(self, actions) -> str:
        """
        Serialize a list of action objects to a JSON string.

        Args:
            actions: The list of action objects to serialize

        Returns:
            A JSON string representation of the actions
        """
        from enum import Enum

        return json.dumps(
            [
                action.name if isinstance(action, Enum) else str(action)
                for action in actions
            ]
        )

    def record_session(self, session_id: str, info: Dict[str, Any]) -> int:
        """
        Record a new game session.

        Args:
            session_id: Unique identifier for the session
            info: Dictionary with session information

        Returns:
            The database ID of the created session
        """
        cursor = self.conn.cursor()

        # Extract relevant information from the info dictionary
        rules_config = info.get("rules", {})
        if isinstance(rules_config, dict):
            rules_config = json.dumps(rules_config)

        num_decks = info.get("num_decks", 6)
        penetration = info.get("penetration", 0.75)
        use_csm = info.get("use_csm", False)
        player_count = info.get("players", 1)
        seed = info.get("seed")
        notes = info.get("notes", "")

        cursor.execute(
            """
            INSERT INTO sessions (
                rules_config, num_decks, penetration, use_csm,
                player_count, seed, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (rules_config, num_decks, penetration, use_csm, player_count, seed, notes),
        )

        db_session_id = cursor.lastrowid
        self.conn.commit()

        # Create mapping between external session ID and database ID
        cursor.execute(
            """
            INSERT INTO session_mapping (
                external_id, internal_id
            ) VALUES (?, ?)
            """,
            (session_id, db_session_id),
        )
        self.conn.commit()

        return db_session_id

    def create_session(
        self,
        rules_config: Dict[str, Any],
        num_decks: int,
        penetration: float,
        use_csm: bool,
        player_count: int,
        seed: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> int:
        """
        Create a new game session record.

        Args:
            rules_config: The rules configuration for the session
            num_decks: The number of decks used
            penetration: The deck penetration before reshuffling
            use_csm: Whether continuous shuffling is used
            player_count: The number of players
            seed: Optional random seed for reproducibility
            notes: Optional notes about the session

        Returns:
            The session_id of the created session
        """
        cursor = self.conn.cursor()

        # Convert rules_config to JSON if it's a dictionary
        if isinstance(rules_config, dict):
            rules_config = json.dumps(rules_config)

        cursor.execute(
            """
            INSERT INTO sessions (
                rules_config, num_decks, penetration, use_csm,
                player_count, seed, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rules_config,
                num_decks,
                penetration,
                use_csm,
                player_count,
                seed,
                notes or "",
            ),
        )

        session_id = cursor.lastrowid
        self.conn.commit()
        return session_id

    def record_round(
        self, round_id: str, session_id: str, details: Dict[str, Any]
    ) -> int:
        """
        Record a new round in a session.

        Args:
            round_id: Unique identifier for the round
            session_id: Identifier for the session
            details: Dictionary with round details

        Returns:
            The database ID of the created round
        """
        cursor = self.conn.cursor()

        # Get the internal session ID from mapping
        cursor.execute(
            "SELECT internal_id FROM session_mapping WHERE external_id = ?",
            (session_id,),
        )
        result = cursor.fetchone()
        if result:
            internal_session_id = result[0]
        else:
            # If no mapping exists, create one with session_id as both external and internal ID
            cursor.execute(
                """
                INSERT INTO sessions (rules_config, num_decks, penetration, use_csm, player_count, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("{}", 6, 0.75, False, 1, "Auto-created session"),
            )
            internal_session_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO session_mapping (external_id, internal_id)
                VALUES (?, ?)
                """,
                (session_id, internal_session_id),
            )
            self.conn.commit()

        # Extract round details
        round_number = details.get("round_number", 0)
        dealer_up_card = details.get("dealer_up_card", "")
        dealer_hole_card = details.get("dealer_hole_card", "")
        dealer_final_hand = details.get("dealer_final_hand", [])
        if isinstance(dealer_final_hand, list):
            dealer_final_hand = json.dumps(dealer_final_hand)
        dealer_final_value = details.get("dealer_final_value", 0)
        shuffle_occurred = details.get("shuffle_occurred", False)

        cursor.execute(
            """
            INSERT INTO rounds (
                session_id, round_number, dealer_up_card,
                dealer_hole_card, dealer_final_hand, dealer_final_value,
                shuffle_occurred
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                internal_session_id,
                round_number,
                dealer_up_card,
                dealer_hole_card,
                dealer_final_hand,
                dealer_final_value,
                shuffle_occurred,
            ),
        )

        db_round_id = cursor.lastrowid
        self.conn.commit()

        # Create mapping between external round_id and database id
        cursor.execute(
            """
            INSERT INTO round_mapping (
                external_id, internal_id
            ) VALUES (?, ?)
            """,
            (round_id, db_round_id),
        )
        self.conn.commit()

        return db_round_id

    def get_events(
        self,
        round_id: str = None,
        session_id: str = None,
        event_type: str = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve events from the database with optional filtering.

        Args:
            round_id: Optional round ID to filter by
            session_id: Optional session ID to filter by
            event_type: Optional event type to filter by
            limit: Maximum number of events to return

        Returns:
            A list of event dictionaries
        """
        cursor = self.conn.cursor()
        query = "SELECT * FROM events WHERE 1=1"
        params = []

        # If round_id is provided, check if it's an external ID and get internal ID
        if round_id:
            cursor.execute(
                "SELECT internal_id FROM round_mapping WHERE external_id = ?",
                (round_id,),
            )
            mapped_id = cursor.fetchone()
            if mapped_id:
                # If we found a mapping, use the internal ID for the query
                query += " AND round_id = ?"
                params.append(str(mapped_id[0]))
            else:
                # If no mapping exists, just use the original ID as is
                query += " AND round_id = ?"
                params.append(round_id)

        # If session_id is provided, check if it's an external ID and get internal ID
        if session_id:
            cursor.execute(
                "SELECT internal_id FROM session_mapping WHERE external_id = ?",
                (session_id,),
            )
            mapped_id = cursor.fetchone()
            if mapped_id:
                # If we found a mapping, use the internal ID for the query
                query += " AND session_id = ?"
                params.append(str(mapped_id[0]))
            else:
                # If no mapping exists, just use the original ID as is
                query += " AND session_id = ?"
                params.append(session_id)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        query += " ORDER BY timestamp LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Convert rows to dictionaries
        events = []
        for row in rows:
            event = dict(row)
            # Parse the event data back to a dictionary
            if "event_data" in event and event["event_data"]:
                try:
                    event["event_data"] = json.loads(event["event_data"])
                except json.JSONDecodeError:
                    pass
            events.append(event)

        return events

    def record_statistical_analysis(
        self,
        session_id: str,
        analysis_type: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        confidence_interval: Dict[str, Any] = None,
        passed: bool = True,
    ) -> int:
        """
        Record the results of a statistical analysis.

        Args:
            session_id: The session ID
            analysis_type: The type of analysis performed
            params: Parameters for the analysis
            result: The analysis results
            confidence_interval: Optional confidence interval data
            passed: Whether the analysis passed validation

        Returns:
            The ID of the recorded analysis
        """
        cursor = self.conn.cursor()

        # Get internal session ID from mapping if it exists
        cursor.execute(
            "SELECT internal_id FROM session_mapping WHERE external_id = ?",
            (session_id,),
        )
        result_map = cursor.fetchone()
        if result_map:
            internal_session_id = result_map[0]
        else:
            # If no mapping exists, use the session_id directly
            internal_session_id = session_id

        # Convert dictionaries to JSON strings
        params_json = json.dumps(params)
        result_json = json.dumps(result)
        ci_json = json.dumps(confidence_interval) if confidence_interval else "{}"

        cursor.execute(
            """
            INSERT INTO statistical_analysis (
                session_id, analysis_type, params, result,
                confidence_interval, passed
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                internal_session_id,
                analysis_type,
                params_json,
                result_json,
                ci_json,
                passed,
            ),
        )

        analysis_id = cursor.lastrowid
        self.conn.commit()
        return analysis_id

    def create_round(
        self,
        session_id: int,
        round_number: int,
        dealer_up_card: Any = None,
        dealer_hole_card: Any = None,
        shuffle_occurred: bool = False,
    ) -> int:
        """
        Create a new round record.

        Args:
            session_id: The ID of the session this round belongs to
            round_number: The sequence number of this round within the session
            dealer_up_card: The dealer's up card (optional)
            dealer_hole_card: The dealer's hole card (optional)
            shuffle_occurred: Whether the deck was shuffled before this round

        Returns:
            The round_id of the created round
        """
        cursor = self.conn.cursor()

        dealer_up_card_str = (
            self._serialize_card(dealer_up_card) if dealer_up_card else None
        )
        dealer_hole_card_str = (
            self._serialize_card(dealer_hole_card) if dealer_hole_card else None
        )

        cursor.execute(
            """
            INSERT INTO rounds 
            (session_id, round_number, dealer_up_card, dealer_hole_card, shuffle_occurred)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                round_number,
                dealer_up_card_str,
                dealer_hole_card_str,
                shuffle_occurred,
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def update_round_final_hand(
        self, round_id: int, final_hand: List[Any], final_value: int
    ) -> None:
        """
        Update a round with the dealer's final hand.

        Args:
            round_id: The ID of the round to update
            final_hand: The dealer's final hand
            final_value: The value of the dealer's final hand
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            UPDATE rounds 
            SET dealer_final_hand = ?, dealer_final_value = ?
            WHERE round_id = ?
            """,
            (self._serialize_cards(final_hand), final_value, round_id),
        )

        self.conn.commit()

    def create_player_hand(
        self,
        round_id: int,
        player_id: int,
        seat_position: int,
        initial_bet: float,
        is_split: bool = False,
        original_hand_id: Optional[int] = None,
    ) -> int:
        """
        Create a new player hand record.

        Args:
            round_id: The ID of the round this hand belongs to
            player_id: The ID of the player
            seat_position: The player's seat position at the table
            initial_bet: The initial bet on this hand
            is_split: Whether this hand was created by splitting
            original_hand_id: The ID of the original hand if this is a split hand

        Returns:
            The hand_id of the created hand
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO player_hands 
            (round_id, player_id, seat_position, initial_bet, is_split, original_hand_id,
             final_bet, insurance_bet)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                round_id,
                player_id,
                seat_position,
                initial_bet,
                is_split,
                original_hand_id,
                initial_bet,  # Initialize final_bet to initial_bet
                0.0,  # Initialize insurance_bet to 0
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def update_player_hand_cards(
        self,
        hand_id: int,
        initial_cards: List[Any] = None,
        final_cards: List[Any] = None,
    ) -> None:
        """
        Update a player hand with card information.

        Args:
            hand_id: The ID of the hand to update
            initial_cards: The initial cards dealt to the hand
            final_cards: The final cards in the hand
        """
        cursor = self.conn.cursor()

        update_sql = "UPDATE player_hands SET "
        params = []

        if initial_cards is not None:
            update_sql += "initial_cards = ?, "
            params.append(self._serialize_cards(initial_cards))

        if final_cards is not None:
            update_sql += "final_cards = ?, "
            params.append(self._serialize_cards(final_cards))

        # Remove the trailing comma and space
        update_sql = update_sql.rstrip(", ")

        update_sql += " WHERE hand_id = ?"
        params.append(hand_id)

        cursor.execute(update_sql, params)
        self.conn.commit()

    def update_player_hand_result(
        self,
        hand_id: int,
        final_value: int,
        is_soft: bool,
        is_blackjack: bool,
        is_busted: bool,
        result: str,
        payout: float,
        final_bet: Optional[float] = None,
        insurance_bet: Optional[float] = None,
    ) -> None:
        """
        Update a player hand with the final result.

        Args:
            hand_id: The ID of the hand to update
            final_value: The final value of the hand
            is_soft: Whether the hand's value is soft
            is_blackjack: Whether the hand is a blackjack
            is_busted: Whether the hand is busted
            result: The result of the hand (win, lose, push, blackjack, surrender)
            payout: The payout amount
            final_bet: The final bet amount (after doubles)
            insurance_bet: The insurance bet amount
        """
        cursor = self.conn.cursor()

        update_sql = """
        UPDATE player_hands 
        SET final_value = ?, is_soft = ?, is_blackjack = ?, is_busted = ?, 
            result = ?, payout = ?
        """
        params = [final_value, is_soft, is_blackjack, is_busted, result, payout]

        if final_bet is not None:
            update_sql += ", final_bet = ?"
            params.append(final_bet)

        if insurance_bet is not None:
            update_sql += ", insurance_bet = ?"
            params.append(insurance_bet)

        update_sql += " WHERE hand_id = ?"
        params.append(hand_id)

        cursor.execute(update_sql, params)
        self.conn.commit()

    def record_action(
        self,
        round_id: int,
        hand_id: Optional[int],
        actor: str,
        actor_id: int,
        action_type: str,
        available_actions: List[str] = None,
        card_received: Any = None,
        hand_value_before: Optional[int] = None,
        hand_value_after: Optional[int] = None,
    ) -> int:
        """
        Record an action in the game.

        Args:
            round_id: The ID of the round
            hand_id: The ID of the hand (may be None for dealer actions)
            actor: The type of actor ('player' or 'dealer')
            actor_id: The ID of the actor
            action_type: The type of action
            available_actions: The actions that were available at this point
            card_received: The card received as a result of the action
            hand_value_before: The hand value before the action
            hand_value_after: The hand value after the action

        Returns:
            The action_id of the recorded action
        """
        cursor = self.conn.cursor()

        available_actions_json = (
            json.dumps(available_actions) if available_actions else None
        )
        card_received_str = (
            self._serialize_card(card_received) if card_received else None
        )

        cursor.execute(
            """
            INSERT INTO actions 
            (round_id, hand_id, actor, actor_id, action_type, available_actions,
             card_received, hand_value_before, hand_value_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                round_id,
                hand_id,
                actor,
                actor_id,
                action_type,
                available_actions_json,
                card_received_str,
                hand_value_before,
                hand_value_after,
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def record_count(
        self,
        round_id: int,
        action_id: int,
        running_count: int,
        true_count: float,
        remaining_decks: float,
    ) -> int:
        """
        Record card counting information.

        Args:
            round_id: The ID of the round
            action_id: The ID of the action that triggered the count update
            running_count: The running count
            true_count: The true count
            remaining_decks: The number of remaining decks

        Returns:
            The count_id of the recorded count
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO count_tracking 
            (round_id, action_id, running_count, true_count, remaining_decks)
            VALUES (?, ?, ?, ?, ?)
            """,
            (round_id, action_id, running_count, true_count, remaining_decks),
        )

        self.conn.commit()
        return cursor.lastrowid

    def record_verification_result(
        self,
        session_id: int,
        round_id: int,
        verification_type: str,
        passed: bool,
        error_detail: Optional[str] = None,
    ) -> int:
        """
        Record the result of a verification check.

        Args:
            session_id: The ID of the session
            round_id: The ID of the round
            verification_type: The type of verification check
            passed: Whether the check passed
            error_detail: Details about the error if the check failed

        Returns:
            The verification_id of the recorded result
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO verification_results 
            (session_id, round_id, verification_type, passed, error_detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, round_id, verification_type, passed, error_detail),
        )

        self.conn.commit()
        return cursor.lastrowid

    def record_statistical_analysis(
        self,
        session_id: int,
        analysis_type: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        confidence_interval: Dict[str, Any],
        passed: bool,
    ) -> int:
        """
        Record the result of a statistical analysis.

        Args:
            session_id: The ID of the session
            analysis_type: The type of analysis
            params: The parameters used for the analysis
            result: The results of the analysis
            confidence_interval: The confidence interval for the analysis
            passed: Whether the result matches the expected theoretical value

        Returns:
            The analysis_id of the recorded analysis
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO statistical_analysis 
            (session_id, analysis_type, params, result, confidence_interval, passed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                analysis_type,
                json.dumps(params),
                json.dumps(result),
                json.dumps(confidence_interval),
                passed,
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def record_performance_metric(
        self,
        session_id: int,
        hands_per_second: float,
        memory_usage: int,
        cpu_usage: float,
    ) -> int:
        """
        Record performance metrics for a session.

        Args:
            session_id: The ID of the session
            hands_per_second: The number of hands processed per second
            memory_usage: The memory usage in bytes
            cpu_usage: The CPU usage as a percentage

        Returns:
            The metric_id of the recorded metric
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO performance_metrics 
            (session_id, hands_per_second, memory_usage, cpu_usage)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, hands_per_second, memory_usage, cpu_usage),
        )

        self.conn.commit()
        return cursor.lastrowid

    def get_rounds_for_session(self, session_id: int) -> List[Dict[str, Any]]:
        """
        Get all rounds for a session.

        Args:
            session_id: The ID of the session

        Returns:
            A list of dictionaries containing round data
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT * FROM rounds
            WHERE session_id = ?
            ORDER BY round_number
            """,
            (session_id,),
        )

        return [dict(row) for row in cursor.fetchall()]

    def get_player_hands(self, round_id: int) -> List[Dict[str, Any]]:
        """
        Get all player hands for a round.

        Args:
            round_id: The ID of the round

        Returns:
            A list of dictionaries containing hand data
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT * FROM player_hands
            WHERE round_id = ?
            ORDER BY player_id, seat_position
            """,
            (round_id,),
        )

        return [dict(row) for row in cursor.fetchall()]

    def get_dealer_actions(self, round_id: int) -> List[Dict[str, Any]]:
        """
        Get all dealer actions for a round.

        Args:
            round_id: The ID of the round

        Returns:
            A list of dictionaries containing action data
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT * FROM actions
            WHERE round_id = ? AND actor = 'dealer'
            ORDER BY timestamp
            """,
            (round_id,),
        )

        return [dict(row) for row in cursor.fetchall()]

    def get_player_actions(self, hand_id: int) -> List[Dict[str, Any]]:
        """
        Get all player actions for a hand.

        Args:
            hand_id: The ID of the hand

        Returns:
            A list of dictionaries containing action data
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT * FROM actions
            WHERE hand_id = ? AND actor = 'player'
            ORDER BY timestamp
            """,
            (hand_id,),
        )

        return [dict(row) for row in cursor.fetchall()]

    def get_player_decision_points(self, round_id: int) -> List[Dict[str, Any]]:
        """
        Get all player decision points for a round.

        Args:
            round_id: The ID of the round

        Returns:
            A list of dictionaries containing action data with available actions
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT * FROM actions
            WHERE round_id = ? AND actor = 'player' AND available_actions IS NOT NULL
            ORDER BY timestamp
            """,
            (round_id,),
        )

        return [dict(row) for row in cursor.fetchall()]

    def record_event(self, event: GameEvent) -> None:
        """
        Record a game event to the appropriate tables.

        This method maps events to the appropriate database operations based on the event type.

        Args:
            event: The game event to record
        """
        event_type = event.event_type
        data = event.data

        if event_type == EventType.GAME_START:
            # Create a new session
            self.create_session(
                rules_config=data.get("rules_config", {}),
                num_decks=data.get("num_decks", 1),
                penetration=data.get("penetration", 0.75),
                use_csm=data.get("use_csm", False),
                player_count=data.get("player_count", 1),
                seed=data.get("seed"),
                notes=data.get("notes"),
            )

        elif event_type == EventType.SHUFFLE:
            # Update the round with shuffle information
            round_id = data.get("round_id")
            if round_id:
                # Find the existing round record or create one
                cursor = self.conn.cursor()
                cursor.execute("SELECT * FROM rounds WHERE round_id = ?", (round_id,))
                row = cursor.fetchone()

                if row:
                    # Update shuffle flag
                    cursor.execute(
                        "UPDATE rounds SET shuffle_occurred = ? WHERE round_id = ?",
                        (True, round_id),
                    )
                    self.conn.commit()
                else:
                    # This shouldn't happen in normal operation
                    session_id = data.get("session_id")
                    round_number = data.get("round_number", 0)

                    if session_id:
                        self.create_round(
                            session_id=session_id,
                            round_number=round_number,
                            shuffle_occurred=True,
                        )

        # Handle other event types similarly, mapping each to the appropriate database operations
        # This is a simplified version - a full implementation would handle all event types

        # For now, let's implement a few more common events

        elif event_type == EventType.BET_PLACED:
            # Record a bet
            round_id = data.get("round_id")
            player_id = data.get("player_id")
            seat_position = data.get("seat_position", 0)
            amount = data.get("amount", 0.0)

            if round_id and player_id:
                # Create a player hand record
                self.create_player_hand(
                    round_id=round_id,
                    player_id=player_id,
                    seat_position=seat_position,
                    initial_bet=amount,
                )

        elif event_type == EventType.CARD_DEALT:
            # Record a card being dealt
            round_id = data.get("round_id")
            hand_id = data.get("hand_id")
            card = data.get("card")
            actor = data.get("actor", "player")
            actor_id = data.get("actor_id", 0)
            hand_value_before = data.get("hand_value_before")
            hand_value_after = data.get("hand_value_after")

            if round_id and card:
                # Record an action
                self.record_action(
                    round_id=round_id,
                    hand_id=hand_id,
                    actor=actor,
                    actor_id=actor_id,
                    action_type="deal",
                    card_received=card,
                    hand_value_before=hand_value_before,
                    hand_value_after=hand_value_after,
                )

        elif event_type == EventType.PLAYER_ACTION:
            # Record a player action
            round_id = data.get("round_id")
            hand_id = data.get("hand_id")
            player_id = data.get("player_id")
            action_type = data.get("action_type")
            available_actions = data.get("available_actions")
            card_received = data.get("card_received")
            hand_value_before = data.get("hand_value_before")
            hand_value_after = data.get("hand_value_after")

            if round_id and hand_id and player_id and action_type:
                # Record an action
                self.record_action(
                    round_id=round_id,
                    hand_id=hand_id,
                    actor="player",
                    actor_id=player_id,
                    action_type=action_type,
                    available_actions=available_actions,
                    card_received=card_received,
                    hand_value_before=hand_value_before,
                    hand_value_after=hand_value_after,
                )

        elif event_type == EventType.HAND_RESULT:
            # Record a hand result
            hand_id = data.get("hand_id")
            final_value = data.get("final_value")
            is_soft = data.get("is_soft", False)
            is_blackjack = data.get("is_blackjack", False)
            is_busted = data.get("is_busted", False)
            result = data.get("result")
            payout = data.get("payout", 0.0)
            final_bet = data.get("final_bet")
            insurance_bet = data.get("insurance_bet")

            if hand_id and final_value and result:
                # Update the player hand with the result
                self.update_player_hand_result(
                    hand_id=hand_id,
                    final_value=final_value,
                    is_soft=is_soft,
                    is_blackjack=is_blackjack,
                    is_busted=is_busted,
                    result=result,
                    payout=payout,
                    final_bet=final_bet,
                    insurance_bet=insurance_bet,
                )

        # Additional event types would be handled similarly
