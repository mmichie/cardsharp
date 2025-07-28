"""
Base API module for Cardsharp.

This module provides the abstract base class for platform-agnostic game APIs
that wrap the Cardsharp engine components.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import (
    Dict,
    Any,
    List,
    Optional,
    Union,
    Tuple,
    Callable,
    TypeVar,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from cardsharp.engine.base import BaseEngine
import threading
import inspect
import time
import uuid

from cardsharp.adapters import PlatformAdapter, CLIAdapter
from cardsharp.events import EventBus, EngineEventType, EventPriority
from cardsharp.api.flow import (
    EventWaiter,
    EventSequence,
    EventFilter,
    EventDrivenContext,
)

# Type variable for game-specific state types
T = TypeVar("T")


class CardsharpGame(ABC):
    """
    Abstract base class for platform-agnostic card game APIs.

    This class defines the common interface for all card game APIs in the Cardsharp
    framework, providing methods for game creation, player management, and game flow
    that work consistently across different game types.

    It also provides utilities for converting between synchronous and asynchronous
    operation modes, making the API flexible for different usage patterns.

    Attributes:
        adapter: The platform adapter used for UI interaction
        engine: The underlying game engine
        config: Game configuration options
        event_bus: The event bus for event-based communication
        event_handlers: Dictionary of registered event handlers
        _is_async_mode: Whether the game is operating in async mode
        event_waiter: EventWaiter for waiting for specific events
    """

    def __init__(
        self,
        adapter: Optional[PlatformAdapter] = None,
        config: Optional[Dict[str, Any]] = None,
        use_async: bool = True,
    ):
        """
        Initialize a new card game.

        Args:
            adapter: Platform adapter to use for rendering and input.
                    If None, a CLI adapter will be used.
            config: Configuration options for the game
            use_async: Whether to use async mode
        """
        self.adapter = adapter or CLIAdapter()
        self.config = config or {}
        self.event_bus = EventBus.get_instance()
        self.event_handlers = {}
        self._is_async_mode = use_async
        self._loop = None  # Event loop for async operations
        self._async_lock = threading.Lock()
        self._game_id = str(uuid.uuid4())

        # Flow control utilities
        self.event_waiter = EventWaiter(self.event_bus)

        # Engine will be initialized by concrete subclasses
        self.engine: Optional[BaseEngine] = None

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the game and prepare for play.

        This method must be implemented by concrete subclasses to set up
        the specific game engine and perform any game-specific initialization.
        """
        await self.adapter.initialize()

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Shut down the game and clean up resources.

        This method must be implemented by concrete subclasses to properly
        shut down the specific game engine and perform cleanup.
        """
        await self.adapter.shutdown()

    @abstractmethod
    async def start_game(self) -> None:
        """
        Start a new game session.

        This method must be implemented by concrete subclasses to start
        a new game with the configured options.
        """
        pass

    @abstractmethod
    async def add_player(self, name: str, balance: float = 1000.0) -> str:
        """
        Add a player to the game.

        Args:
            name: Player's display name
            balance: Starting balance for the player

        Returns:
            Player ID that can be used for future operations
        """
        pass

    @abstractmethod
    async def remove_player(self, player_id: str) -> bool:
        """
        Remove a player from the game.

        Args:
            player_id: ID of the player to remove

        Returns:
            True if the player was successfully removed
        """
        pass

    @abstractmethod
    async def get_state(self) -> T:
        """
        Get the current game state.

        Returns:
            Current game state object
        """
        pass

    def on(
        self,
        event_type: Union[str, EngineEventType],
        handler: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> Callable:
        """
        Register an event handler.

        Args:
            event_type: Type of event to listen for
            handler: Event handler function
            priority: Priority level for the handler

        Returns:
            Function to call to unsubscribe the handler
        """
        # Convert string event types to enum if possible
        if isinstance(event_type, str):
            try:
                event_type = getattr(EngineEventType, event_type.upper())
            except (AttributeError, KeyError):
                # Keep as string if not a known enum value
                pass

        # Register with the event bus and get the unsubscribe function
        unsubscribe_func = self.event_bus.on(event_type, handler, priority)

        # Store the unsubscribe function with its type for later reference
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(unsubscribe_func)

        return unsubscribe_func

    def once(
        self,
        event_type: Union[str, EngineEventType],
        handler: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> Callable:
        """
        Register an event handler that will be called only once.

        Args:
            event_type: Type of event to listen for
            handler: Event handler function
            priority: Priority level for the handler

        Returns:
            Function to call to unsubscribe the handler
        """
        # Convert string event types to enum if possible
        if isinstance(event_type, str):
            try:
                event_type = getattr(EngineEventType, event_type.upper())
            except (AttributeError, KeyError):
                # Keep as string if not a known enum value
                pass

        # Register with the event bus and get the unsubscribe function
        unsubscribe_func = self.event_bus.once(event_type, handler, priority)

        # Store the unsubscribe function with its type for later reference
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(unsubscribe_func)

        return unsubscribe_func

    def emit(
        self, event_type: Union[str, EngineEventType], data: Dict[str, Any]
    ) -> None:
        """
        Emit an event to the event bus.

        Args:
            event_type: Type of event to emit
            data: Event data
        """
        # Add game ID and timestamp if not present
        if "game_id" not in data:
            data["game_id"] = self._game_id
        if "timestamp" not in data:
            data["timestamp"] = time.time()

        # Convert string event types to enum if possible
        if isinstance(event_type, str):
            try:
                event_type = getattr(EngineEventType, event_type.upper())
            except (AttributeError, KeyError):
                # Keep as string if not a known enum value
                pass

        # Emit the event
        self.event_bus.emit(event_type, data)

    # Synchronous API wrappers

    def initialize_sync(self) -> None:
        """
        Synchronous wrapper for initialize method.
        """
        return self._run_async(self.initialize())

    def shutdown_sync(self) -> None:
        """
        Synchronous wrapper for shutdown method.
        """
        return self._run_async(self.shutdown())

    def start_game_sync(self) -> None:
        """
        Synchronous wrapper for start_game method.
        """
        return self._run_async(self.start_game())

    def add_player_sync(self, name: str, balance: float = 1000.0) -> str:
        """
        Synchronous wrapper for add_player method.
        """
        return self._run_async(self.add_player(name, balance))

    def remove_player_sync(self, player_id: str) -> bool:
        """
        Synchronous wrapper for remove_player method.
        """
        return self._run_async(self.remove_player(player_id))

    def get_state_sync(self) -> T:
        """
        Synchronous wrapper for get_state method.
        """
        return self._run_async(self.get_state())

    # Event-driven flow control methods

    async def wait_for_event(
        self,
        event_type: Union[str, EngineEventType],
        condition: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[Union[str, EngineEventType], Dict[str, Any]]:
        """
        Wait for a specific event to occur.

        Args:
            event_type: Type of event to wait for
            condition: Optional condition to check event data
            timeout: Optional timeout in seconds

        Returns:
            Tuple of (event_type, event_data)

        Raises:
            asyncio.TimeoutError: If the timeout is reached
        """
        return await self.event_waiter.wait_for(event_type, condition, timeout)

    async def wait_for_all_events(
        self,
        event_specs: List[
            Tuple[
                Union[str, EngineEventType],
                Optional[Callable[[str, Dict[str, Any]], bool]],
            ]
        ],
        timeout: Optional[float] = None,
    ) -> List[Tuple[Union[str, EngineEventType], Dict[str, Any]]]:
        """
        Wait for all specified events to occur.

        Args:
            event_specs: List of (event_type, condition) tuples
            timeout: Optional timeout in seconds

        Returns:
            List of (event_type, event_data) tuples in the order of specification

        Raises:
            asyncio.TimeoutError: If the timeout is reached
        """
        return await self.event_waiter.wait_for_all(event_specs, timeout)

    async def wait_for_any_event(
        self,
        event_specs: List[
            Tuple[
                Union[str, EngineEventType],
                Optional[Callable[[str, Dict[str, Any]], bool]],
            ]
        ],
        timeout: Optional[float] = None,
    ) -> Tuple[int, Union[str, EngineEventType], Dict[str, Any]]:
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

    def create_event_sequence(self) -> EventSequence:
        """
        Create a new event sequence for chaining actions and events.

        Returns:
            A new EventSequence object
        """
        return EventSequence(self.event_bus)

    def create_event_filter(self) -> EventFilter:
        """
        Create a new event filter for routing events to handlers.

        Returns:
            A new EventFilter object
        """
        return EventFilter(self.event_bus)

    async def with_event_context(self) -> EventDrivenContext:
        """
        Create an event-driven context manager.

        Returns:
            An EventDrivenContext object
        """
        return EventDrivenContext(self.event_bus)

    # Synchronous wrappers for flow control methods

    def wait_for_event_sync(
        self,
        event_type: Union[str, EngineEventType],
        condition: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[Union[str, EngineEventType], Dict[str, Any]]:
        """
        Synchronous wrapper for wait_for_event method.
        """
        return self._run_async(self.wait_for_event(event_type, condition, timeout))

    def wait_for_all_events_sync(
        self,
        event_specs: List[
            Tuple[
                Union[str, EngineEventType],
                Optional[Callable[[str, Dict[str, Any]], bool]],
            ]
        ],
        timeout: Optional[float] = None,
    ) -> List[Tuple[Union[str, EngineEventType], Dict[str, Any]]]:
        """
        Synchronous wrapper for wait_for_all_events method.
        """
        return self._run_async(self.wait_for_all_events(event_specs, timeout))

    def wait_for_any_event_sync(
        self,
        event_specs: List[
            Tuple[
                Union[str, EngineEventType],
                Optional[Callable[[str, Dict[str, Any]], bool]],
            ]
        ],
        timeout: Optional[float] = None,
    ) -> Tuple[int, Union[str, EngineEventType], Dict[str, Any]]:
        """
        Synchronous wrapper for wait_for_any_event method.
        """
        return self._run_async(self.wait_for_any_event(event_specs, timeout))

    # Utility methods for async/sync conversion

    def _run_async(self, coro):
        """
        Run an async coroutine from a synchronous context.

        Args:
            coro: Coroutine to run

        Returns:
            Result of the coroutine
        """
        # If we're already in async mode, this is a programming error
        if self._is_async_mode and asyncio.get_event_loop().is_running():
            raise RuntimeError(
                "Attempting to use synchronous method in async mode. "
                "Use the async version of this method instead."
            )

        # Create or get the event loop
        with self._async_lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)

            # Run the coroutine in the event loop
            return self._loop.run_until_complete(coro)

    @staticmethod
    def _is_async_caller() -> bool:
        """
        Check if the calling function is an async function.

        Returns:
            True if caller is async, False otherwise
        """
        # Inspect the call stack to check if we're in an async context
        for frame in inspect.stack():
            if inspect.iscoroutinefunction(frame.frame.f_code):
                return True
        return False
