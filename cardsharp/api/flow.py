"""
Event-driven flow control for the Cardsharp API.

This module provides enhanced tools for event-driven flow control,
allowing for more complex interactions with the event system.
"""

import asyncio
import time
from typing import (
    Dict,
    Any,
    List,
    Optional,
    Union,
    Tuple,
    Callable,
    TypeVar,
    Generic,
    Set,
)
from enum import Enum
import uuid
import functools
import inspect

from cardsharp.events import EventBus, EngineEventType, EventPriority

# Type for event data
EventData = Dict[str, Any]
# Type for event predicate functions
EventPredicate = Callable[[str, EventData], bool]
# Type for event handler functions
EventHandler = Callable[[EventData], None]
# Type variable for awaitable results
T = TypeVar("T")


class EventWaiter:
    """
    Utility for waiting for specific events or conditions.

    This class allows waiting for events with specific conditions,
    with optional timeout handling.

    Example:
        ```python
        # Wait for player action with specific player_id
        waiter = EventWaiter()
        player_id = "player123"
        event, data = await waiter.wait_for(
            EngineEventType.PLAYER_ACTION,
            lambda evt, data: data.get("player_id") == player_id,
            timeout=5.0
        )
        ```
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        """
        Initialize a new event waiter.

        Args:
            event_bus: Event bus to use. If None, the global instance will be used.
        """
        self.event_bus = event_bus or EventBus.get_instance()
        self._waiters = {}

    async def wait_for(
        self,
        event_type: Union[str, EngineEventType],
        condition: Optional[EventPredicate] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[Union[str, EngineEventType], EventData]:
        """
        Wait for a specific event with an optional condition.

        Args:
            event_type: The event type to wait for
            condition: Optional predicate function to check event data
            timeout: Optional timeout in seconds

        Returns:
            Tuple of (event_type, event_data)

        Raises:
            asyncio.TimeoutError: If the timeout is reached
        """
        # Create a future to wait on
        future = asyncio.Future()
        waiter_id = str(uuid.uuid4())

        # Store the waiter info
        self._waiters[waiter_id] = {
            "future": future,
            "event_type": event_type,
            "condition": condition,
        }

        # Create event handler
        def event_handler(data):
            if waiter_id not in self._waiters:
                return

            waiter_info = self._waiters[waiter_id]

            # Check condition if provided
            if waiter_info["condition"] and not waiter_info["condition"](
                event_type, data
            ):
                return

            # Resolve the future
            if not waiter_info["future"].done():
                waiter_info["future"].set_result((event_type, data))

            # Clean up
            self._cleanup_waiter(waiter_id)

        # Register event handler
        unsubscribe = self.event_bus.on(event_type, event_handler)

        try:
            # Wait for the event with optional timeout
            if timeout is not None:
                return await asyncio.wait_for(future, timeout)
            else:
                return await future
        except asyncio.TimeoutError:
            # Clean up on timeout
            self._cleanup_waiter(waiter_id)
            raise
        finally:
            # Always unsubscribe
            unsubscribe()

    async def wait_for_all(
        self,
        event_specs: List[Tuple[Union[str, EngineEventType], Optional[EventPredicate]]],
        timeout: Optional[float] = None,
    ) -> List[Tuple[Union[str, EngineEventType], EventData]]:
        """
        Wait for all specified events to occur.

        Args:
            event_specs: List of (event_type, condition) tuples
            timeout: Optional timeout in seconds

        Returns:
            List of (event_type, event_data) tuples in the order of occurrence

        Raises:
            asyncio.TimeoutError: If the timeout is reached
        """
        if not event_specs:
            return []

        # Create a future to wait on
        future = asyncio.Future()
        waiter_id = str(uuid.uuid4())

        # Track event occurrences
        pending_events = set(range(len(event_specs)))
        results = [None] * len(event_specs)

        # Store the waiter info
        self._waiters[waiter_id] = {
            "future": future,
            "event_specs": event_specs,
            "pending": pending_events,
            "results": results,
        }

        # Create event handlers for each event spec
        unsubscribe_funcs = []

        for i, (event_type, condition) in enumerate(event_specs):
            # Create event handler
            def make_handler(index):
                def event_handler(data):
                    if waiter_id not in self._waiters:
                        return

                    waiter_info = self._waiters[waiter_id]
                    evt_type, evt_condition = waiter_info["event_specs"][index]

                    # Check condition if provided
                    if evt_condition and not evt_condition(evt_type, data):
                        return

                    # Record the result
                    if index in waiter_info["pending"]:
                        waiter_info["pending"].remove(index)
                        waiter_info["results"][index] = (evt_type, data)

                    # If all events have occurred, resolve the future
                    if not waiter_info["pending"] and not waiter_info["future"].done():
                        waiter_info["future"].set_result(waiter_info["results"])
                        self._cleanup_waiter(waiter_id)

                return event_handler

            # Register event handler
            unsubscribe = self.event_bus.on(event_type, make_handler(i))
            unsubscribe_funcs.append(unsubscribe)

        try:
            # Wait for all events with optional timeout
            if timeout is not None:
                return await asyncio.wait_for(future, timeout)
            else:
                return await future
        except asyncio.TimeoutError:
            # Clean up on timeout
            self._cleanup_waiter(waiter_id)
            raise
        finally:
            # Always unsubscribe
            for unsubscribe in unsubscribe_funcs:
                unsubscribe()

    async def wait_for_any(
        self,
        event_specs: List[Tuple[Union[str, EngineEventType], Optional[EventPredicate]]],
        timeout: Optional[float] = None,
    ) -> Tuple[int, Union[str, EngineEventType], EventData]:
        """
        Wait for any of the specified events to occur.

        Args:
            event_specs: List of (event_type, condition) tuples
            timeout: Optional timeout in seconds

        Returns:
            Tuple of (index, event_type, event_data) where index is the index in the event_specs list

        Raises:
            asyncio.TimeoutError: If the timeout is reached
        """
        if not event_specs:
            raise ValueError("Must provide at least one event spec")

        # Create a future to wait on
        future = asyncio.Future()
        waiter_id = str(uuid.uuid4())

        # Store the waiter info
        self._waiters[waiter_id] = {
            "future": future,
            "event_specs": event_specs,
        }

        # Create event handlers for each event spec
        unsubscribe_funcs = []

        for i, (event_type, condition) in enumerate(event_specs):
            # Create event handler
            def make_handler(index):
                def event_handler(data):
                    if waiter_id not in self._waiters:
                        return

                    waiter_info = self._waiters[waiter_id]
                    evt_type, evt_condition = waiter_info["event_specs"][index]

                    # Check condition if provided
                    if evt_condition and not evt_condition(evt_type, data):
                        return

                    # Resolve the future with the index and data
                    if not waiter_info["future"].done():
                        waiter_info["future"].set_result((index, evt_type, data))
                        self._cleanup_waiter(waiter_id)

                return event_handler

            # Register event handler
            unsubscribe = self.event_bus.on(event_type, make_handler(i))
            unsubscribe_funcs.append(unsubscribe)

        try:
            # Wait for any event with optional timeout
            if timeout is not None:
                return await asyncio.wait_for(future, timeout)
            else:
                return await future
        except asyncio.TimeoutError:
            # Clean up on timeout
            self._cleanup_waiter(waiter_id)
            raise
        finally:
            # Always unsubscribe
            for unsubscribe in unsubscribe_funcs:
                unsubscribe()

    def _cleanup_waiter(self, waiter_id: str) -> None:
        """
        Clean up a waiter by ID.

        Args:
            waiter_id: ID of the waiter to clean up
        """
        if waiter_id in self._waiters:
            del self._waiters[waiter_id]


class EventSequence:
    """
    Utility for creating and executing sequences of events.

    This class allows defining a sequence of events with conditions
    and timeouts, and executing them in order.

    Example:
        ```python
        # Create a sequence of player actions
        sequence = EventSequence()

        # Add steps to the sequence
        sequence.add_step(
            "place_bet",
            lambda engine: engine.place_bet("player1", 10.0),
            EngineEventType.PLAYER_BET,
            lambda evt, data: data.get("player_id") == "player1"
        )
        sequence.add_step(
            "hit",
            lambda engine: engine.execute_player_action("player1", "HIT"),
            EngineEventType.PLAYER_ACTION,
            lambda evt, data: data.get("player_id") == "player1" and data.get("action") == "HIT"
        )

        # Execute the sequence
        await sequence.execute(game_engine)
        ```
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        """
        Initialize a new event sequence.

        Args:
            event_bus: Event bus to use. If None, the global instance will be used.
        """
        self.event_bus = event_bus or EventBus.get_instance()
        self.steps = []
        self.event_waiter = EventWaiter(event_bus)

    def add_step(
        self,
        name: str,
        action: Callable[[Any], Any],
        wait_event: Optional[Union[str, EngineEventType]] = None,
        wait_condition: Optional[EventPredicate] = None,
        timeout: Optional[float] = None,
    ) -> "EventSequence":
        """
        Add a step to the sequence.

        Args:
            name: Name of the step
            action: Function to call to execute the step
            wait_event: Event to wait for after executing the action
            wait_condition: Condition to check for the wait event
            timeout: Timeout for waiting

        Returns:
            Self for chaining
        """
        self.steps.append(
            {
                "name": name,
                "action": action,
                "wait_event": wait_event,
                "wait_condition": wait_condition,
                "timeout": timeout,
            }
        )
        return self

    async def execute(
        self, context: Any, stop_on_error: bool = True
    ) -> Dict[str, Tuple[bool, Optional[Any], Optional[Exception]]]:
        """
        Execute the sequence of steps.

        Args:
            context: Context object to pass to step actions
            stop_on_error: Whether to stop on the first error

        Returns:
            Dictionary of step results, with each entry being (success, result, error)
        """
        results = {}

        for step in self.steps:
            try:
                # Execute the step action
                action_result = step["action"](context)

                # If the action returns a coroutine, await it
                if inspect.iscoroutine(action_result):
                    action_result = await action_result

                # Wait for the event if specified
                if step["wait_event"]:
                    try:
                        evt, data = await self.event_waiter.wait_for(
                            step["wait_event"], step["wait_condition"], step["timeout"]
                        )
                        # Store the event data with the result
                        results[step["name"]] = (True, (action_result, data), None)
                    except asyncio.TimeoutError:
                        # Timeout waiting for event
                        results[step["name"]] = (
                            False,
                            action_result,
                            asyncio.TimeoutError(
                                f"Timeout waiting for event {step['wait_event']}"
                            ),
                        )
                        if stop_on_error:
                            return results
                else:
                    # No event to wait for, just store the action result
                    results[step["name"]] = (True, action_result, None)

            except Exception as e:
                # Error executing the step
                results[step["name"]] = (False, None, e)
                if stop_on_error:
                    return results

        return results


class EventFilter:
    """
    Utility for filtering events.

    This class allows filtering events based on conditions,
    and routing them to different handlers.

    Example:
        ```python
        # Create an event filter
        filter = EventFilter()

        # Add handlers for specific events
        filter.add_handler(
            EngineEventType.PLAYER_ACTION,
            lambda data: data.get("player_id") == "player1",
            handle_player1_action
        )
        filter.add_handler(
            EngineEventType.PLAYER_ACTION,
            lambda data: data.get("player_id") == "player2",
            handle_player2_action
        )

        # Activate the filter
        filter.activate()

        # Later, deactivate it
        filter.deactivate()
        ```
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        """
        Initialize a new event filter.

        Args:
            event_bus: Event bus to use. If None, the global instance will be used.
        """
        self.event_bus = event_bus or EventBus.get_instance()
        self.handlers = {}
        self.unsubscribe_funcs = {}
        self.active = False

    def add_handler(
        self,
        event_type: Union[str, EngineEventType],
        condition: Optional[Callable[[EventData], bool]] = None,
        handler: EventHandler = None,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> str:
        """
        Add a handler for a specific event type and condition.

        Args:
            event_type: The event type to handle
            condition: Function to check if the event should be handled
            handler: Function to call when the event occurs
            priority: Priority of the handler

        Returns:
            Handler ID that can be used to remove the handler
        """
        handler_id = str(uuid.uuid4())

        self.handlers[handler_id] = {
            "event_type": event_type,
            "condition": condition,
            "handler": handler,
            "priority": priority,
        }

        # If active, register the handler
        if self.active:
            self._register_handler(handler_id)

        return handler_id

    def remove_handler(self, handler_id: str) -> bool:
        """
        Remove a handler by ID.

        Args:
            handler_id: ID of the handler to remove

        Returns:
            True if the handler was found and removed
        """
        if handler_id not in self.handlers:
            return False

        # If active, unsubscribe
        if self.active and handler_id in self.unsubscribe_funcs:
            self.unsubscribe_funcs[handler_id]()
            del self.unsubscribe_funcs[handler_id]

        # Remove the handler
        del self.handlers[handler_id]
        return True

    def activate(self) -> None:
        """
        Activate the filter, registering all handlers.
        """
        if self.active:
            return

        # Register all handlers
        for handler_id in self.handlers:
            self._register_handler(handler_id)

        self.active = True

    def deactivate(self) -> None:
        """
        Deactivate the filter, unregistering all handlers.
        """
        if not self.active:
            return

        # Unsubscribe all handlers
        for handler_id, unsubscribe in self.unsubscribe_funcs.items():
            unsubscribe()

        self.unsubscribe_funcs.clear()
        self.active = False

    def _register_handler(self, handler_id: str) -> None:
        """
        Register a handler with the event bus.

        Args:
            handler_id: ID of the handler to register
        """
        handler_info = self.handlers[handler_id]

        # Create the event handler function
        def event_handler(data):
            # Check condition if provided
            if handler_info["condition"] and not handler_info["condition"](data):
                return

            # Call the handler
            handler_info["handler"](data)

        # Register with the event bus
        unsubscribe = self.event_bus.on(
            handler_info["event_type"], event_handler, handler_info["priority"]
        )

        # Store the unsubscribe function
        self.unsubscribe_funcs[handler_id] = unsubscribe


def event_driven(
    event_type: Union[str, EngineEventType],
    condition: Optional[Callable[[EventData], bool]] = None,
    timeout: Optional[float] = None,
):
    """
    Decorator to make a function event-driven.

    This decorator transforms a function to wait for a specific event
    before returning.

    Example:
        ```python
        @event_driven(EngineEventType.PLAYER_ACTION, lambda data: data.get("action") == "HIT")
        async def hit_card(game, player_id):
            await game.execute_action(player_id, "HIT")
            # This function will only return after the player action event occurs
        ```

    Args:
        event_type: Event type to wait for
        condition: Condition to check event data
        timeout: Timeout for waiting

    Returns:
        Decorated function
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get the event bus from the first arg if it's a CardsharpGame
            from cardsharp.api.base import CardsharpGame

            if args and isinstance(args[0], CardsharpGame):
                event_bus = args[0].event_bus
            else:
                event_bus = EventBus.get_instance()

            # Create an event waiter
            waiter = EventWaiter(event_bus)

            # Call the original function
            result = await func(*args, **kwargs)

            # Wait for the event
            try:
                evt, data = await waiter.wait_for(event_type, condition, timeout)
                # Return both the original result and the event data
                return result, data
            except asyncio.TimeoutError:
                # Return just the original result on timeout
                return result, None

        return wrapper

    return decorator


class EventDrivenContext:
    """
    Context manager for event-driven execution.

    This class provides a context manager that sets up event handlers
    and cleans them up when the context exits.

    Example:
        ```python
        async with EventDrivenContext() as ctx:
            # Register handlers
            ctx.on(EngineEventType.PLAYER_ACTION, handle_player_action)

            # Execute actions
            await game.execute_action(player_id, "HIT")

            # Wait for events
            evt, data = await ctx.wait_for(EngineEventType.HAND_BUSTED)
        ```
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        """
        Initialize a new event-driven context.

        Args:
            event_bus: Event bus to use. If None, the global instance will be used.
        """
        self.event_bus = event_bus or EventBus.get_instance()
        self.event_waiter = EventWaiter(self.event_bus)
        self.unsubscribe_funcs = []

    async def __aenter__(self):
        """
        Enter the context.

        Returns:
            Self
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the context, cleaning up event handlers.
        """
        # Unsubscribe all handlers
        for unsubscribe in self.unsubscribe_funcs:
            unsubscribe()

        self.unsubscribe_funcs.clear()

    def on(
        self,
        event_type: Union[str, EngineEventType],
        handler: EventHandler,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """
        Register an event handler for the duration of the context.

        Args:
            event_type: Event type to handle
            handler: Handler function
            priority: Handler priority
        """
        unsubscribe = self.event_bus.on(event_type, handler, priority)
        self.unsubscribe_funcs.append(unsubscribe)

    def once(
        self,
        event_type: Union[str, EngineEventType],
        handler: EventHandler,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """
        Register a one-time event handler for the duration of the context.

        Args:
            event_type: Event type to handle
            handler: Handler function
            priority: Handler priority
        """
        unsubscribe = self.event_bus.once(event_type, handler, priority)
        self.unsubscribe_funcs.append(unsubscribe)

    async def wait_for(
        self,
        event_type: Union[str, EngineEventType],
        condition: Optional[EventPredicate] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[Union[str, EngineEventType], EventData]:
        """
        Wait for a specific event with an optional condition.

        Args:
            event_type: The event type to wait for
            condition: Optional predicate function to check event data
            timeout: Optional timeout in seconds

        Returns:
            Tuple of (event_type, event_data)

        Raises:
            asyncio.TimeoutError: If the timeout is reached
        """
        return await self.event_waiter.wait_for(event_type, condition, timeout)

    async def wait_for_all(
        self,
        event_specs: List[Tuple[Union[str, EngineEventType], Optional[EventPredicate]]],
        timeout: Optional[float] = None,
    ) -> List[Tuple[Union[str, EngineEventType], EventData]]:
        """
        Wait for all specified events to occur.

        Args:
            event_specs: List of (event_type, condition) tuples
            timeout: Optional timeout in seconds

        Returns:
            List of (event_type, event_data) tuples in the order of occurrence

        Raises:
            asyncio.TimeoutError: If the timeout is reached
        """
        return await self.event_waiter.wait_for_all(event_specs, timeout)

    async def wait_for_any(
        self,
        event_specs: List[Tuple[Union[str, EngineEventType], Optional[EventPredicate]]],
        timeout: Optional[float] = None,
    ) -> Tuple[int, Union[str, EngineEventType], EventData]:
        """
        Wait for any of the specified events to occur.

        Args:
            event_specs: List of (event_type, condition) tuples
            timeout: Optional timeout in seconds

        Returns:
            Tuple of (index, event_type, event_data) where index is the index in the event_specs list

        Raises:
            asyncio.TimeoutError: If the timeout is reached
        """
        return await self.event_waiter.wait_for_any(event_specs, timeout)
