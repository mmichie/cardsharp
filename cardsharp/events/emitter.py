"""
Enhanced event system for the Cardsharp engine.

This module provides a robust event system that serves as the foundation for the 
event-driven architecture. It extends the current event recording capabilities
to support bidirectional events and subscriptions.
"""

from collections import defaultdict
from typing import Any, Dict, List, Callable, Optional, Set, Union
import uuid
import time
import threading
import logging
from enum import Enum

# Import existing event system
try:
    from cardsharp.verification.events import EventType as VerificationEventType
    from cardsharp.verification.events import (
        GameEvent,
        EventEmitter as OriginalEventEmitter,
    )

    _has_verification = True
except ImportError:
    # Define mock versions if verification module is not available
    from enum import Enum

    class VerificationEventType(Enum):
        GAME_START = "game_start"
        SHUFFLE = "shuffle"
        BET_PLACED = "bet_placed"
        PLAYER_ACTION = "player_action"

    class GameEvent:
        def __init__(self, event_type, game_id, round_id, data, **kwargs):
            self.event_type = event_type
            self.game_id = game_id
            self.round_id = round_id
            self.data = data
            for k, v in kwargs.items():
                setattr(self, k, v)

    class OriginalEventEmitter:
        def __init__(self, **kwargs):
            pass

    _has_verification = False

# Create a logger for the event system
logger = logging.getLogger("cardsharp.events")


class EventPriority(Enum):
    """Priority levels for event handlers."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EventEmitter:
    """
    Enhanced event emitter for Cardsharp engine.

    This class provides both the original event recording capabilities and
    adds support for subscribing to events with priority-based handling.

    Features:
    - Backward compatible with existing EventEmitter
    - Supports event subscription with priorities
    - Allows once-only subscriptions
    - Supports subscribing to all events with event type filtering in handler
    - Thread-safe event emission
    """

    def __init__(self):
        """Initialize the event emitter."""
        self._listeners = defaultdict(list)
        self._global_listeners = []
        self._listener_lock = threading.RLock()

        # Context variables for event recording
        self._game_id: Optional[str] = None
        self._round_id: Optional[str] = None

        # Optional recorder for event persistence
        self._recorder = None

    def set_recorder(self, recorder):
        """
        Set an event recorder for persistence.

        Args:
            recorder: An EventRecorder instance or compatible object with record_event method
        """
        self._recorder = recorder

    def set_context(self, game_id: str, round_id: str) -> None:
        """
        Set the context for events emitted by this object.

        Args:
            game_id: The unique identifier for the game session
            round_id: The identifier for the current round
        """
        self._game_id = game_id
        self._round_id = round_id

    def on(
        self,
        event_type: Union[str, Enum],
        callback: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> Callable:
        """
        Subscribe to an event type.

        Args:
            event_type: The event type to subscribe to (string or enum)
            callback: Function to call when event occurs, signature: fn(event_data)
            priority: Priority level for this handler

        Returns:
            Unsubscribe function that can be called to remove this subscription
        """
        if isinstance(event_type, Enum):
            event_type = event_type.name

        handler = {"callback": callback, "priority": priority.value}

        with self._listener_lock:
            # Insert handler in order of priority (higher numbers first)
            handlers = self._listeners[event_type]

            # Find insertion point based on priority
            for i, existing in enumerate(handlers):
                if existing["priority"] < priority.value:
                    handlers.insert(i, handler)
                    break
            else:
                # If we didn't break, append to the end
                handlers.append(handler)

        def unsubscribe():
            with self._listener_lock:
                handlers = self._listeners[event_type]
                for i, existing in enumerate(handlers):
                    if existing["callback"] == callback:
                        handlers.pop(i)
                        break

        return unsubscribe

    def once(
        self,
        event_type: Union[str, Enum],
        callback: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> Callable:
        """
        Subscribe to an event type for a single occurrence.

        Args:
            event_type: The event type to subscribe to (string or enum)
            callback: Function to call when event occurs
            priority: Priority level for this handler

        Returns:
            Unsubscribe function that can be called to remove this subscription
        """
        if isinstance(event_type, Enum):
            event_type = event_type.name

        # Create a wrapper that will unsubscribe after first call
        unsubscribe_ref = []

        def one_time_handler(event_data):
            try:
                callback(event_data)
            finally:
                # Unsubscribe in any case, even if callback raises an exception
                if unsubscribe_ref and callable(unsubscribe_ref[0]):
                    unsubscribe_ref[0]()

        unsubscribe_ref.append(self.on(event_type, one_time_handler, priority))
        return unsubscribe_ref[0]

    def on_any(
        self, callback: Callable, priority: EventPriority = EventPriority.NORMAL
    ) -> Callable:
        """
        Subscribe to all events.

        Args:
            callback: Function to call for any event, signature: fn(event_type, event_data)
            priority: Priority level for this handler

        Returns:
            Unsubscribe function that can be called to remove this subscription
        """
        handler = {"callback": callback, "priority": priority.value}

        with self._listener_lock:
            # Insert handler in order of priority
            for i, existing in enumerate(self._global_listeners):
                if existing["priority"] < priority.value:
                    self._global_listeners.insert(i, handler)
                    break
            else:
                # If we didn't break, append to the end
                self._global_listeners.append(handler)

        def unsubscribe():
            with self._listener_lock:
                for i, existing in enumerate(self._global_listeners):
                    if existing["callback"] == callback:
                        self._global_listeners.pop(i)
                        break

        return unsubscribe

    def emit(self, event_type: Union[str, Enum], data: Dict[str, Any]) -> None:
        """
        Emit an event to all registered listeners.

        Args:
            event_type: The type of event to emit
            data: The data to include with the event
        """
        original_event_type = event_type

        # If enum, convert to string for consistency
        if isinstance(event_type, Enum):
            event_type = event_type.name

        # Create a GameEvent for the recorder if context is set
        if self._recorder and self._game_id and self._round_id:
            # Only create a GameEvent for verification event types if they exist
            if _has_verification and isinstance(
                original_event_type, VerificationEventType
            ):
                event = GameEvent(
                    event_type=original_event_type,
                    game_id=self._game_id,
                    round_id=self._round_id,
                    data=data,
                )
                self._recorder.record_event(event)

        # Call all registered listeners with data
        handlers_to_call = []

        with self._listener_lock:
            # Collect specific event handlers
            for handler in self._listeners.get(event_type, []):
                handlers_to_call.append((handler["callback"], data))

            # Collect global event handlers
            for handler in self._global_listeners:
                handlers_to_call.append((handler["callback"], (event_type, data)))

        # Call handlers outside of the lock to avoid deadlocks
        for callback, args in handlers_to_call:
            try:
                callback(args)
            except Exception as e:
                logger.error(
                    f"Error in event handler for {event_type}: {e}", exc_info=True
                )

    async def emit_async(
        self, event_type: Union[str, Enum], data: Dict[str, Any]
    ) -> None:
        """
        Emit an event asynchronously to all registered listeners.

        Args:
            event_type: The type of event to emit
            data: The data to include with the event
        """
        # This is a basic async implementation that still calls all handlers
        # sequentially. In a more complex implementation, we could consider
        # allowing truly parallel execution of handlers.
        self.emit(event_type, data)

    def emit_deferred(
        self, event_type: Union[str, Enum], data: Dict[str, Any], delay_ms: int
    ) -> None:
        """
        Emit an event after a specified delay.

        Args:
            event_type: The type of event to emit
            data: The data to include with the event
            delay_ms: Delay in milliseconds before emitting the event
        """
        if delay_ms <= 0:
            self.emit(event_type, data)
            return

        def delayed_emit():
            time.sleep(delay_ms / 1000.0)
            self.emit(event_type, data)

        thread = threading.Thread(target=delayed_emit)
        thread.daemon = True
        thread.start()

    def remove_all_listeners(
        self, event_type: Optional[Union[str, Enum]] = None
    ) -> None:
        """
        Remove all listeners for a specific event type or all events.

        Args:
            event_type: Optional event type. If None, removes all listeners for all events.
        """
        with self._listener_lock:
            if event_type is None:
                self._listeners.clear()
                self._global_listeners.clear()
            else:
                if isinstance(event_type, Enum):
                    event_type = event_type.name
                self._listeners[event_type].clear()


class EventBus:
    """
    Global event bus for the application.

    This singleton class provides a centralized event bus that can be accessed
    from anywhere in the application.
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> EventEmitter:
        """
        Get the singleton instance of the EventBus.

        Returns:
            EventEmitter instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = EventEmitter()
        return cls._instance


# Define more comprehensive event types for the engine
class EngineEventType(Enum):
    """
    Event types for the Cardsharp engine architecture.

    These event types cover the entire game flow and provide hooks for
    platform adapters to respond to game state changes.
    """

    # Core lifecycle events
    ENGINE_INIT = "engine_init"
    ENGINE_SHUTDOWN = "engine_shutdown"

    # Game lifecycle
    GAME_CREATED = "game_created"
    GAME_STARTED = "game_started"
    GAME_ENDED = "game_ended"
    ROUND_STARTED = "round_started"
    ROUND_ENDED = "round_ended"

    # Player events
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    PLAYER_BET = "player_bet"
    PLAYER_DECISION_NEEDED = "player_decision_needed"
    PLAYER_ACTION = "player_action"
    PLAYER_TIMEOUT = "player_timeout"

    # Card events
    CARD_DEALT = "card_dealt"
    CARD_REVEALED = "card_revealed"
    CARD_HIDDEN = "card_hidden"

    # Hand events
    HAND_CREATED = "hand_created"
    HAND_SPLIT = "hand_split"
    HAND_BUSTED = "hand_busted"
    HAND_COMPLETED = "hand_completed"
    HAND_RESULT = "hand_result"

    # Dealer events
    DEALER_UPCARD = "dealer_upcard"
    DEALER_ACTION = "dealer_action"
    DEALER_ERROR = "dealer_error"

    # Insurance events
    INSURANCE_OFFERED = "insurance_offered"
    INSURANCE_DECISION = "insurance_decision"

    # Money events
    MONEY_BET = "money_bet"
    MONEY_PAYOUT = "money_payout"
    BANKROLL_UPDATED = "bankroll_updated"

    # Strategy events
    STRATEGY_DECISION = "strategy_decision"
    STRATEGY_DEVIATION = "strategy_deviation"
    COUNT_UPDATED = "count_updated"
    SHUFFLE = "shuffle"

    # Error events
    ERROR = "error"
    WARNING = "warning"

    # Simulation events
    SIMULATION_PROGRESS = "simulation_progress"
    SIMULATION_RESULT = "simulation_result"

    # Platform adapter events
    UI_UPDATE_NEEDED = "ui_update_needed"
    USER_INTERACTION_NEEDED = "user_interaction_needed"
    USER_INTERACTION_RECEIVED = "user_interaction_received"

    # Custom events
    CUSTOM_EVENT = "custom_event"
