"""
Dummy adapter for the Cardsharp engine, used for testing and simulation.

This module provides a non-interactive adapter that can be used for automated
testing, simulations, and benchmarks where no user interaction is needed.
"""

from typing import List, Dict, Any, Optional, Union, Awaitable
from enum import Enum
import random

from cardsharp.adapters.base import PlatformAdapter

# Import Action from base which will handle the import or mock it
from cardsharp.adapters.base import Action


class DummyAdapter(PlatformAdapter):
    """
    Dummy adapter for testing and simulation.

    This adapter doesn't interact with any real platform and is designed for
    automated tests, simulations, and benchmarks. It can be configured to
    automatically select actions according to different strategies.
    """

    def __init__(
        self,
        auto_actions: Optional[Dict[str, List[Action]]] = None,
        strategy_function: Optional[callable] = None,
        verbose: bool = False,
    ):
        """
        Initialize the dummy adapter.

        Args:
            auto_actions: Optional dictionary mapping player IDs to lists of actions
                         to take in sequence
            strategy_function: Optional function that takes (player_id, valid_actions)
                              and returns an action to take
            verbose: Whether to print events to stdout (useful for debugging)
        """
        self.auto_actions = auto_actions or {}
        self.strategy_function = strategy_function
        self.verbose = verbose

        # Track action index for each player
        self.action_index = {}

        # Track events for later inspection
        self.events = []

        # Track rendered states for testing
        self.rendered_states = []

    async def render_game_state(self, state: Dict[str, Any]) -> None:
        """
        Store the game state for later inspection.

        Args:
            state: The current game state
        """
        self.rendered_states.append(state)

        if self.verbose:
            print("\n=== Game State ===")
            print(f"Dealer: {state.get('dealer', {}).get('hand', [])}")

            for player in state.get("players", []):
                hands = player.get("hands", [])
                for i, hand in enumerate(hands):
                    print(
                        f"Player {player.get('name')}, Hand {i+1}: {hand.get('cards', [])} - {hand.get('value', 0)}"
                    )

            print("==================\n")

    async def request_player_action(
        self,
        player_id: str,
        player_name: str,
        valid_actions: List[Action],
        timeout_seconds: Optional[float] = None,
    ) -> Awaitable[Action]:
        """
        Return a predefined action or select one using the strategy function.

        Args:
            player_id: Unique identifier for the player
            player_name: Display name of the player
            valid_actions: List of valid actions the player can take
            timeout_seconds: Optional timeout (ignored in this adapter)

        Returns:
            A selected action
        """
        # Initialize action index for this player if not already done
        if player_id not in self.action_index:
            self.action_index[player_id] = 0

        # Determine the action to take
        selected_action = None

        # If player has predefined actions, use those
        if player_id in self.auto_actions:
            actions_list = self.auto_actions[player_id]
            if self.action_index[player_id] < len(actions_list):
                selected_action = actions_list[self.action_index[player_id]]
                self.action_index[player_id] += 1

        # If no predefined action or we ran out, use strategy function
        if selected_action is None and self.strategy_function:
            selected_action = self.strategy_function(player_id, valid_actions)

        # If still no action, default to STAND if available, otherwise pick randomly
        if selected_action is None:
            if Action.STAND in valid_actions:
                selected_action = Action.STAND
            else:
                selected_action = random.choice(valid_actions)

        # Make sure the selected action is valid
        if selected_action not in valid_actions:
            selected_action = random.choice(valid_actions)

        if self.verbose:
            print(f"Player {player_name} selects {selected_action.name}")

        return selected_action

    async def notify_game_event(
        self, event_type: Union[str, Enum], data: Dict[str, Any]
    ) -> None:
        """
        Store the event for later inspection.

        Args:
            event_type: The type of event that occurred
            data: Data associated with the event
        """
        # Convert enum to string if necessary
        event_type_str = event_type.name if isinstance(event_type, Enum) else event_type

        # Store the event
        self.events.append((event_type_str, data))

        if self.verbose:
            print(f"Event: {event_type_str}")
            for key, value in data.items():
                print(f"  {key}: {value}")

    async def handle_timeout(
        self, player_id: str, player_name: str
    ) -> Awaitable[Action]:
        """
        Handle a player timeout by returning STAND.

        Args:
            player_id: Unique identifier for the player
            player_name: Display name of the player

        Returns:
            The default action (STAND)
        """
        if self.verbose:
            print(f"Player {player_name} timed out. Standing by default.")

        return Action.STAND

    def get_events_by_type(self, event_type: Union[str, Enum]) -> List[Dict[str, Any]]:
        """
        Get all events of a specific type.

        Args:
            event_type: The type of events to retrieve

        Returns:
            A list of event data dictionaries
        """
        event_type_str = event_type.name if isinstance(event_type, Enum) else event_type
        return [data for typ, data in self.events if typ == event_type_str]

    def clear(self) -> None:
        """Clear all stored events and states."""
        self.events.clear()
        self.rendered_states.clear()
        self.action_index.clear()
