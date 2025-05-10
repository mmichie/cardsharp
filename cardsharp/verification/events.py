"""
Event types and event capturing system for the blackjack verification framework.

This module defines the event types that are used to track the state of the game
and provides classes for capturing and processing these events.
"""

from enum import Enum, auto
from typing import Any, Dict, List, Optional, Union
import time
import json
import uuid
from dataclasses import dataclass, field, asdict


class EventType(Enum):
    """Types of events that can occur in a blackjack game."""

    GAME_START = auto()
    SHUFFLE = auto()
    BET_PLACED = auto()
    INITIAL_DEAL = auto()
    CARD_DEALT = auto()
    INSURANCE_OFFERED = auto()
    INSURANCE_DECISION = auto()
    PLAYER_DECISION_POINT = auto()  # Records available actions
    PLAYER_ACTION = auto()
    DEALER_DECISION_POINT = auto()
    DEALER_ACTION = auto()
    HAND_RESULT = auto()
    PAYOUT = auto()
    GAME_END = auto()


@dataclass
class GameEvent:
    """
    Records a single event in the blackjack game with complete context.

    Attributes:
        event_type: The type of event
        game_id: Unique identifier for the game session
        round_id: Identifier for the current round
        data: Complete state information relevant to the event
        event_id: Unique identifier for this event
        timestamp: When the event occurred
    """

    event_type: EventType
    game_id: str
    round_id: str
    data: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the event to a dictionary for serialization."""
        result = asdict(self)
        # Convert Enum to string for serialization
        result["event_type"] = self.event_type.name
        return result

    def to_json(self) -> str:
        """Convert the event to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GameEvent":
        """Create an event from a dictionary."""
        # Convert string back to Enum
        data["event_type"] = EventType[data["event_type"]]
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> "GameEvent":
        """Create an event from a JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class EventEmitter:
    """
    Base class for objects that can emit game events.

    This class provides methods for emitting events and registering event listeners.
    Game components should inherit from this class to gain event emission capabilities.
    """

    def __init__(self):
        """Initialize the event emitter."""
        self._listeners: Dict[EventType, List[callable]] = {
            event_type: [] for event_type in EventType
        }
        self._game_id: Optional[str] = None
        self._round_id: Optional[str] = None

    def set_context(self, game_id: str, round_id: str) -> None:
        """
        Set the context for events emitted by this object.

        Args:
            game_id: The unique identifier for the game session
            round_id: The identifier for the current round
        """
        self._game_id = game_id
        self._round_id = round_id

    def add_listener(self, event_type: EventType, listener: callable) -> None:
        """
        Add a listener for a specific event type.

        Args:
            event_type: The type of event to listen for
            listener: A callable that takes a GameEvent as its argument
        """
        self._listeners[event_type].append(listener)

    def remove_listener(self, event_type: EventType, listener: callable) -> None:
        """
        Remove a listener for a specific event type.

        Args:
            event_type: The type of event the listener is registered for
            listener: The listener to remove
        """
        if listener in self._listeners[event_type]:
            self._listeners[event_type].remove(listener)

    def emit(self, event_type: EventType, data: Dict[str, Any]) -> None:
        """
        Emit an event to all registered listeners.

        Args:
            event_type: The type of event to emit
            data: The data to include with the event
        """
        if not self._game_id or not self._round_id:
            raise ValueError(
                "Context not set. Call set_context before emitting events."
            )

        event = GameEvent(
            event_type=event_type,
            game_id=self._game_id,
            round_id=self._round_id,
            data=data,
        )

        # Notify all listeners for this event type
        for listener in self._listeners[event_type]:
            listener(event)


class EventRecorder:
    """
    Records game events for later analysis and verification.

    This class acts as a listener for game events and records them for
    later analysis, verification, or playback.
    """

    def __init__(self):
        """Initialize the event recorder."""
        self.events: List[GameEvent] = []

    def record_event(self, event: GameEvent) -> None:
        """
        Record a game event.

        Args:
            event: The event to record
        """
        self.events.append(event)

    def get_events_by_type(self, event_type: EventType) -> List[GameEvent]:
        """
        Get all events of a specific type.

        Args:
            event_type: The type of events to retrieve

        Returns:
            A list of events of the specified type
        """
        return [event for event in self.events if event.event_type == event_type]

    def get_events_for_round(self, round_id: str) -> List[GameEvent]:
        """
        Get all events for a specific round.

        Args:
            round_id: The identifier for the round

        Returns:
            A list of events for the specified round
        """
        return [event for event in self.events if event.round_id == round_id]

    def get_events_for_game(self, game_id: str) -> List[GameEvent]:
        """
        Get all events for a specific game.

        Args:
            game_id: The identifier for the game

        Returns:
            A list of events for the specified game
        """
        return [event for event in self.events if event.game_id == game_id]

    def clear(self) -> None:
        """Clear all recorded events."""
        self.events = []
