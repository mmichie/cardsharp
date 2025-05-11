"""
Database schema for the Blackjack verification system.

This module defines the SQLite schema used to store detailed information about
blackjack games for verification and statistical analysis.
"""

from typing import List, Optional
import sqlite3
import json
import os
from pathlib import Path


SCHEMA_SQL = """
-- Main schema for blackjack simulation verification

-- Game sessions
CREATE TABLE IF NOT EXISTS sessions (
    session_id INTEGER PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    rules_config TEXT,  -- JSON of rule configurations
    num_decks INTEGER,
    penetration REAL,
    use_csm BOOLEAN,
    player_count INTEGER,
    seed INTEGER,  -- For reproducibility
    notes TEXT
);

-- Rounds within a session
CREATE TABLE IF NOT EXISTS rounds (
    round_id INTEGER PRIMARY KEY,
    session_id INTEGER,
    round_number INTEGER,
    dealer_up_card TEXT,  -- Card representation
    dealer_hole_card TEXT,
    dealer_final_hand TEXT,  -- JSON array of cards
    dealer_final_value INTEGER,
    shuffle_occurred BOOLEAN,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- Player hands within a round
CREATE TABLE IF NOT EXISTS player_hands (
    hand_id INTEGER PRIMARY KEY,
    round_id INTEGER,
    player_id INTEGER,
    seat_position INTEGER,
    is_split BOOLEAN,
    original_hand_id INTEGER,  -- For tracking split hands
    initial_bet REAL,
    final_bet REAL,
    insurance_bet REAL,
    initial_cards TEXT,  -- JSON array of initial cards
    final_cards TEXT,  -- JSON array of final cards
    final_value INTEGER,
    is_soft BOOLEAN,
    is_blackjack BOOLEAN,
    is_busted BOOLEAN,
    result TEXT,  -- win, lose, push, blackjack, surrender
    payout REAL,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id),
    FOREIGN KEY (original_hand_id) REFERENCES player_hands(hand_id)
);

-- Individual actions during the game
CREATE TABLE IF NOT EXISTS actions (
    action_id INTEGER PRIMARY KEY,
    hand_id INTEGER,
    round_id INTEGER,
    actor TEXT,  -- 'player' or 'dealer'
    actor_id INTEGER,
    action_type TEXT,  -- hit, stand, double, split, surrender, insurance
    available_actions TEXT,  -- JSON array of actions that were available
    card_received TEXT,  -- If action resulted in receiving a card
    hand_value_before INTEGER,
    hand_value_after INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hand_id) REFERENCES player_hands(hand_id),
    FOREIGN KEY (round_id) REFERENCES rounds(round_id)
);

-- Card counting information (for strategy verification)
CREATE TABLE IF NOT EXISTS count_tracking (
    count_id INTEGER PRIMARY KEY,
    round_id INTEGER,
    action_id INTEGER,
    running_count INTEGER,
    true_count REAL,
    remaining_decks REAL,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id),
    FOREIGN KEY (action_id) REFERENCES actions(action_id)
);

-- Verification results
CREATE TABLE IF NOT EXISTS verification_results (
    verification_id INTEGER PRIMARY KEY,
    session_id INTEGER,
    round_id INTEGER,
    verification_type TEXT,  -- 'dealer_actions', 'payouts', 'player_options', etc.
    passed BOOLEAN,
    error_detail TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (round_id) REFERENCES rounds(round_id)
);

-- Statistical analysis
CREATE TABLE IF NOT EXISTS statistical_analysis (
    analysis_id INTEGER PRIMARY KEY,
    session_id INTEGER,
    analysis_type TEXT,  -- 'ev', 'hand_distribution', 'win_rate', etc.
    params TEXT,  -- JSON parameters for the analysis
    result TEXT,  -- JSON results
    confidence_interval TEXT,  -- JSON confidence interval data
    passed BOOLEAN,  -- Whether it matches expected theoretical results
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- Raw event storage for detailed event analysis and replay
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY,
    session_id TEXT,
    round_id TEXT,
    event_type TEXT,
    event_data TEXT,  -- JSON data for the event
    timestamp REAL,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Performance tracking
CREATE TABLE IF NOT EXISTS performance_metrics (
    metric_id INTEGER PRIMARY KEY,
    session_id INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    hands_per_second REAL,
    memory_usage INTEGER,
    cpu_usage REAL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- Session ID mapping (external UUID to internal ID)
CREATE TABLE IF NOT EXISTS session_mapping (
    mapping_id INTEGER PRIMARY KEY,
    external_id TEXT UNIQUE NOT NULL,  -- UUID or other external identifier
    internal_id INTEGER NOT NULL,      -- Database session_id
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (internal_id) REFERENCES sessions(session_id)
);

-- Round ID mapping (external UUID to internal ID)
CREATE TABLE IF NOT EXISTS round_mapping (
    mapping_id INTEGER PRIMARY KEY,
    external_id TEXT UNIQUE NOT NULL,  -- UUID or other external identifier
    internal_id INTEGER NOT NULL,      -- Database round_id
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (internal_id) REFERENCES rounds(round_id)
);

-- Player hand ID mapping (external UUID to internal ID)
CREATE TABLE IF NOT EXISTS hand_mapping (
    mapping_id INTEGER PRIMARY KEY,
    external_id TEXT UNIQUE NOT NULL,  -- UUID or other external identifier
    internal_id INTEGER NOT NULL,      -- Database hand_id
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (internal_id) REFERENCES player_hands(hand_id)
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_rounds_session ON rounds(session_id);
CREATE INDEX IF NOT EXISTS idx_hands_round ON player_hands(round_id);
CREATE INDEX IF NOT EXISTS idx_actions_hand ON actions(hand_id);
CREATE INDEX IF NOT EXISTS idx_actions_round ON actions(round_id);
CREATE INDEX IF NOT EXISTS idx_count_round ON count_tracking(round_id);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_round ON events(round_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_session_mapping_external ON session_mapping(external_id);
CREATE INDEX IF NOT EXISTS idx_round_mapping_external ON round_mapping(external_id);
CREATE INDEX IF NOT EXISTS idx_hand_mapping_external ON hand_mapping(external_id);
"""


class DatabaseInitializer:
    """Initialize and manage the verification database."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the database with the required schema.

        Args:
            db_path: Optional path to the database file. If None, uses the default path.
        """
        if db_path is None:
            # Use a default path in the user's home directory
            home_dir = Path.home()
            cardsharp_dir = home_dir / ".cardsharp"
            cardsharp_dir.mkdir(exist_ok=True)
            db_path = str(cardsharp_dir / "verification.db")

        self.db_path = db_path
        self.conn = self._initialize_database()

    def _initialize_database(self) -> sqlite3.Connection:
        """
        Initialize the database with the schema.

        Returns:
            sqlite3.Connection: An open connection to the database.
        """
        conn = sqlite3.connect(self.db_path)

        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")

        # Create the tables
        conn.executescript(SCHEMA_SQL)
        conn.commit()

        return conn

    def reset_database(self) -> None:
        """
        Reset the database by dropping all tables and recreating them.
        Use with caution as this will delete all data.
        """
        self.conn.close()

        if os.path.exists(self.db_path):
            os.remove(self.db_path)

        self.conn = self._initialize_database()

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()


def initialize_database(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Initialize the verification database with the required schema.

    Args:
        db_path: Optional path to the database file. If None, uses the default path.

    Returns:
        sqlite3.Connection: An open connection to the database.
    """
    initializer = DatabaseInitializer(db_path)
    return initializer.conn


if __name__ == "__main__":
    # If the script is run directly, initialize the database
    db = initialize_database()
    print(f"Database initialized successfully.")
    db.close()
