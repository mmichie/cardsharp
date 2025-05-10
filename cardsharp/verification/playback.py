"""
Visualization and playback system for blackjack game sessions.

This module provides tools for visualizing and replaying blackjack game sessions
from the event database, allowing for detailed analysis and inspection.
"""

import json
import time
from typing import Any, Dict, List, Optional, Tuple, Union, cast
from enum import Enum, auto
import sqlite3
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cardsharp.verification.storage import SQLiteEventStore


class PlaybackSpeed(Enum):
    """Speed options for playback."""

    SLOW = 1.0  # Real-time
    NORMAL = 0.5  # 2x speed
    FAST = 0.1  # 10x speed
    INSTANT = 0.0  # Instant playback


class PlaybackController:
    """
    Controls the playback of a recorded blackjack session.

    This class provides methods for playing back a recorded session,
    stepping through individual events, and jumping to specific points.
    """

    def __init__(self, event_store: SQLiteEventStore):
        """
        Initialize the playback controller.

        Args:
            event_store: The event store containing session data
        """
        self.event_store = event_store
        self.current_session_id: Optional[int] = None
        self.current_round_id: Optional[int] = None
        self.current_index: int = 0
        self.actions: List[Dict[str, Any]] = []
        self.speed = PlaybackSpeed.NORMAL
        self._paused = True

    def load_session(self, session_id: int) -> bool:
        """
        Load a session for playback.

        Args:
            session_id: The ID of the session to load

        Returns:
            True if the session was loaded successfully, False otherwise
        """
        # Check if the session exists
        cursor = self.event_store.conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        session = cursor.fetchone()

        if not session:
            return False

        self.current_session_id = session_id
        self.current_round_id = None
        self.current_index = 0
        self._paused = True

        return True

    def load_round(self, round_id: int) -> bool:
        """
        Load a specific round for playback.

        Args:
            round_id: The ID of the round to load

        Returns:
            True if the round was loaded successfully, False otherwise
        """
        # Check if the round exists
        cursor = self.event_store.conn.cursor()
        cursor.execute("SELECT * FROM rounds WHERE round_id = ?", (round_id,))
        round_data = cursor.fetchone()

        if not round_data:
            return False

        # Load all actions for this round
        cursor.execute(
            """
            SELECT * FROM actions 
            WHERE round_id = ? 
            ORDER BY timestamp
            """,
            (round_id,),
        )

        self.actions = [dict(row) for row in cursor.fetchall()]
        self.current_round_id = round_id
        self.current_session_id = round_data["session_id"]
        self.current_index = 0
        self._paused = True

        return True

    def play(self) -> None:
        """Start playback from the current position."""
        if not self.current_round_id:
            return

        self._paused = False

        while not self._paused and self.current_index < len(self.actions):
            self.step_forward()

            # Sleep based on playback speed
            if self.speed.value > 0:
                time.sleep(self.speed.value)

    def pause(self) -> None:
        """Pause playback."""
        self._paused = True

    def step_forward(self) -> Optional[Dict[str, Any]]:
        """
        Advance to the next action.

        Returns:
            The current action, or None if at the end of the round
        """
        if not self.current_round_id or self.current_index >= len(self.actions):
            return None

        action = self.actions[self.current_index]
        self.current_index += 1

        return action

    def step_backward(self) -> Optional[Dict[str, Any]]:
        """
        Return to the previous action.

        Returns:
            The current action, or None if at the beginning of the round
        """
        if not self.current_round_id or self.current_index <= 0:
            return None

        self.current_index -= 1
        action = self.actions[self.current_index]

        return action

    def jump_to_start(self) -> Optional[Dict[str, Any]]:
        """
        Jump to the start of the round.

        Returns:
            The first action, or None if no actions exist
        """
        if not self.current_round_id or not self.actions:
            return None

        self.current_index = 0
        return self.actions[self.current_index]

    def jump_to_end(self) -> Optional[Dict[str, Any]]:
        """
        Jump to the end of the round.

        Returns:
            The last action, or None if no actions exist
        """
        if not self.current_round_id or not self.actions:
            return None

        self.current_index = len(self.actions) - 1
        return self.actions[self.current_index]

    def jump_to_player_decision(self, forward: bool = True) -> Optional[Dict[str, Any]]:
        """
        Jump to the next or previous player decision point.

        Args:
            forward: If True, jump forward, otherwise jump backward

        Returns:
            The action at the decision point, or None if none exists
        """
        if not self.current_round_id or not self.actions:
            return None

        start_index = self.current_index

        if forward:
            # Search forward
            for i in range(start_index, len(self.actions)):
                action = self.actions[i]
                if action["actor"] == "player" and action["available_actions"]:
                    self.current_index = i
                    return action
        else:
            # Search backward
            for i in range(start_index - 1, -1, -1):
                action = self.actions[i]
                if action["actor"] == "player" and action["available_actions"]:
                    self.current_index = i
                    return action

        return None

    def jump_to_dealer_action(self, forward: bool = True) -> Optional[Dict[str, Any]]:
        """
        Jump to the next or previous dealer action.

        Args:
            forward: If True, jump forward, otherwise jump backward

        Returns:
            The dealer action, or None if none exists
        """
        if not self.current_round_id or not self.actions:
            return None

        start_index = self.current_index

        if forward:
            # Search forward
            for i in range(start_index, len(self.actions)):
                action = self.actions[i]
                if action["actor"] == "dealer":
                    self.current_index = i
                    return action
        else:
            # Search backward
            for i in range(start_index - 1, -1, -1):
                action = self.actions[i]
                if action["actor"] == "dealer":
                    self.current_index = i
                    return action

        return None

    def get_current_state(self) -> Dict[str, Any]:
        """
        Get the current state of the round.

        Returns:
            A dictionary with the current state
        """
        if not self.current_round_id:
            return {"error": "No round loaded"}

        # Get round data
        cursor = self.event_store.conn.cursor()
        cursor.execute(
            "SELECT * FROM rounds WHERE round_id = ?", (self.current_round_id,)
        )
        round_data = cursor.fetchone()

        # Get all player hands for this round
        cursor.execute(
            """
            SELECT * FROM player_hands 
            WHERE round_id = ?
            """,
            (self.current_round_id,),
        )
        hands = [dict(row) for row in cursor.fetchall()]

        # Get all actions up to the current index
        actions_so_far = self.actions[: self.current_index]

        # Reconstruct the state at this point
        state = {
            "round_id": self.current_round_id,
            "round_number": round_data["round_number"],
            "dealer_up_card": round_data["dealer_up_card"],
            "dealer_hole_card": round_data["dealer_hole_card"],
            "dealer_cards_visible": [],
            "player_hands": {},
            "current_player_id": None,
            "current_hand_id": None,
            "last_action": None,
            "progress": f"{self.current_index}/{len(self.actions)}",
        }

        # Process actions to build the current state
        for action in actions_so_far:
            # Track dealer cards
            if action["actor"] == "dealer" and action["card_received"]:
                state["dealer_cards_visible"].append(action["card_received"])

            # Track player cards and current player
            if action["actor"] == "player":
                hand_id = action["hand_id"]
                player_id = action["actor_id"]

                # Initialize player hand if needed
                if player_id not in state["player_hands"]:
                    state["player_hands"][player_id] = {}

                # Initialize hand if needed
                if hand_id not in state["player_hands"][player_id]:
                    state["player_hands"][player_id][hand_id] = {
                        "cards": [],
                        "value": 0,
                        "actions": [],
                    }

                # Update the hand
                player_hand = state["player_hands"][player_id][hand_id]
                player_hand["actions"].append(action["action_type"])

                if action["card_received"]:
                    player_hand["cards"].append(action["card_received"])

                if action["hand_value_after"] is not None:
                    player_hand["value"] = action["hand_value_after"]

                # Track current player and hand
                state["current_player_id"] = player_id
                state["current_hand_id"] = hand_id

            # Track last action
            state["last_action"] = action

        return state


class GameVisualizer:
    """
    Visualizes blackjack game sessions using matplotlib.

    This class provides methods for visualizing various aspects of a blackjack
    game session, such as win rates, bankroll evolution, and hand values.
    """

    def __init__(self, event_store: SQLiteEventStore):
        """
        Initialize the visualizer.

        Args:
            event_store: The event store containing session data
        """
        self.event_store = event_store

    def plot_session_results(
        self, session_id: int, figsize: Tuple[int, int] = (10, 6)
    ) -> plt.Figure:
        """
        Plot the results of a session.

        Args:
            session_id: The ID of the session to visualize
            figsize: The size of the figure

        Returns:
            The matplotlib figure
        """
        # Get all player hands for the session
        cursor = self.event_store.conn.cursor()
        cursor.execute(
            """
            SELECT r.round_number, h.player_id, h.initial_bet, h.payout, h.result
            FROM player_hands h
            JOIN rounds r ON h.round_id = r.round_id
            WHERE r.session_id = ?
            ORDER BY r.round_number
            """,
            (session_id,),
        )

        results = cursor.fetchall()

        if not results:
            fig, ax = plt.subplots(figsize=figsize)
            ax.set_title("No data available for this session")
            return fig

        # Convert to DataFrame for easier analysis
        df = pd.DataFrame([dict(row) for row in results])

        # Calculate net profit per hand
        df["net_profit"] = df["payout"] - df["initial_bet"]

        # Calculate cumulative profit
        df["cumulative_profit"] = df.groupby("player_id")["net_profit"].cumsum()

        # Create figure with subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize)

        # Plot cumulative profit over time
        for player_id, group in df.groupby("player_id"):
            ax1.plot(
                group["round_number"],
                group["cumulative_profit"],
                label=f"Player {player_id}",
            )

        ax1.set_title("Bankroll Evolution")
        ax1.set_xlabel("Round")
        ax1.set_ylabel("Cumulative Profit ($)")
        ax1.grid(True)
        ax1.legend()

        # Plot win/loss/push distribution
        result_counts = df["result"].value_counts()
        ax2.bar(result_counts.index, result_counts.values)
        ax2.set_title("Result Distribution")
        ax2.set_xlabel("Result")
        ax2.set_ylabel("Count")

        plt.tight_layout()
        return fig

    def plot_hand_value_distribution(
        self, session_id: int, figsize: Tuple[int, int] = (10, 6)
    ) -> plt.Figure:
        """
        Plot the distribution of final hand values.

        Args:
            session_id: The ID of the session to visualize
            figsize: The size of the figure

        Returns:
            The matplotlib figure
        """
        # Get all player hands for the session
        cursor = self.event_store.conn.cursor()
        cursor.execute(
            """
            SELECT h.final_value, h.is_busted
            FROM player_hands h
            JOIN rounds r ON h.round_id = r.round_id
            WHERE r.session_id = ?
            """,
            (session_id,),
        )

        results = cursor.fetchall()

        if not results:
            fig, ax = plt.subplots(figsize=figsize)
            ax.set_title("No data available for this session")
            return fig

        # Convert to DataFrame for easier analysis
        df = pd.DataFrame([dict(row) for row in results])

        # For busted hands, create a special category
        df.loc[df["is_busted"], "final_value"] = -1

        # Create figure
        fig, ax = plt.subplots(figsize=figsize)

        # Plot histogram of hand values
        bins = [
            -1.5,
            -0.5,
            1.5,
            2.5,
            3.5,
            4.5,
            5.5,
            6.5,
            7.5,
            8.5,
            9.5,
            10.5,
            11.5,
            12.5,
            13.5,
            14.5,
            15.5,
            16.5,
            17.5,
            18.5,
            19.5,
            20.5,
            21.5,
        ]
        n, bins, patches = ax.hist(df["final_value"], bins=bins, alpha=0.7)

        # Custom x-tick labels
        ax.set_xticks(
            [-1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]
        )
        ax.set_xticklabels(
            [
                "Bust",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
                "10",
                "11",
                "12",
                "13",
                "14",
                "15",
                "16",
                "17",
                "18",
                "19",
                "20",
                "21",
            ]
        )
        plt.xticks(rotation=45)

        ax.set_title("Distribution of Hand Values")
        ax.set_xlabel("Hand Value")
        ax.set_ylabel("Frequency")

        # Highlight the most common value
        most_common_value = df["final_value"].value_counts().idxmax()
        most_common_idx = np.digitize([most_common_value], bins)[0] - 1
        patches[most_common_idx].set_facecolor("red")

        plt.tight_layout()
        return fig

    def plot_dealer_final_values(
        self, session_id: int, figsize: Tuple[int, int] = (10, 6)
    ) -> plt.Figure:
        """
        Plot the distribution of dealer final values.

        Args:
            session_id: The ID of the session to visualize
            figsize: The size of the figure

        Returns:
            The matplotlib figure
        """
        # Get all rounds for the session
        cursor = self.event_store.conn.cursor()
        cursor.execute(
            """
            SELECT dealer_final_value
            FROM rounds
            WHERE session_id = ? AND dealer_final_value IS NOT NULL
            """,
            (session_id,),
        )

        results = cursor.fetchall()

        if not results:
            fig, ax = plt.subplots(figsize=figsize)
            ax.set_title("No data available for this session")
            return fig

        # Convert to DataFrame for easier analysis
        df = pd.DataFrame([dict(row) for row in results])

        # Create figure
        fig, ax = plt.subplots(figsize=figsize)

        # Plot histogram of dealer values
        bins = [16.5, 17.5, 18.5, 19.5, 20.5, 21.5, 22.5]
        n, bins, patches = ax.hist(df["dealer_final_value"], bins=bins, alpha=0.7)

        # Custom x-tick labels
        ax.set_xticks([17, 18, 19, 20, 21, 22])
        ax.set_xticklabels(["17", "18", "19", "20", "21", "Bust"])

        ax.set_title("Distribution of Dealer Final Values")
        ax.set_xlabel("Dealer Value")
        ax.set_ylabel("Frequency")

        # Highlight the most common value
        most_common_value = df["dealer_final_value"].value_counts().idxmax()
        most_common_idx = np.digitize([most_common_value], bins)[0] - 1
        if 0 <= most_common_idx < len(patches):
            patches[most_common_idx].set_facecolor("red")

        plt.tight_layout()
        return fig

    def plot_bet_sizes(
        self, session_id: int, figsize: Tuple[int, int] = (10, 6)
    ) -> plt.Figure:
        """
        Plot the distribution of bet sizes.

        Args:
            session_id: The ID of the session to visualize
            figsize: The size of the figure

        Returns:
            The matplotlib figure
        """
        # Get all player hands for the session
        cursor = self.event_store.conn.cursor()
        cursor.execute(
            """
            SELECT r.round_number, h.player_id, h.initial_bet
            FROM player_hands h
            JOIN rounds r ON h.round_id = r.round_id
            WHERE r.session_id = ?
            ORDER BY r.round_number
            """,
            (session_id,),
        )

        results = cursor.fetchall()

        if not results:
            fig, ax = plt.subplots(figsize=figsize)
            ax.set_title("No data available for this session")
            return fig

        # Convert to DataFrame for easier analysis
        df = pd.DataFrame([dict(row) for row in results])

        # Create figure
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize)

        # Plot bet sizes over time
        for player_id, group in df.groupby("player_id"):
            ax1.plot(
                group["round_number"], group["initial_bet"], label=f"Player {player_id}"
            )

        ax1.set_title("Bet Sizes Over Time")
        ax1.set_xlabel("Round")
        ax1.set_ylabel("Bet Size ($)")
        ax1.grid(True)
        ax1.legend()

        # Plot distribution of bet sizes
        ax2.hist(df["initial_bet"], bins=20, alpha=0.7)
        ax2.set_title("Bet Size Distribution")
        ax2.set_xlabel("Bet Size ($)")
        ax2.set_ylabel("Frequency")

        plt.tight_layout()
        return fig
