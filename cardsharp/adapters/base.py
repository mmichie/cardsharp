"""
Base adapter interface for the Cardsharp engine.

This module defines the interface that platform-specific adapters must implement
to interact with the Cardsharp engine.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union, Awaitable
import asyncio
from enum import Enum

# Import Action if available, otherwise define a mock
try:
    from cardsharp.blackjack.action import Action
except ImportError:
    from enum import Enum, auto

    class Action(Enum):
        """Mock Action enum for when blackjack module is not available."""

        HIT = auto()
        STAND = auto()
        DOUBLE = auto()
        SPLIT = auto()
        SURRENDER = auto()


class PlatformAdapter(ABC):
    """
    Base interface for platform-specific adapters.

    This abstract class defines the methods that platform-specific adapters
    must implement to interact with the Cardsharp engine. These methods handle
    rendering the game state, requesting player actions, and notifying of
    game events.

    Implementations of this interface bridge the gap between the platform-agnostic
    game engine and specific platforms like console, web, Discord, etc.
    """

    @abstractmethod
    async def render_game_state(self, state: Dict[str, Any]) -> None:
        """
        Render the current game state to the platform.

        Args:
            state: The current game state (dealer hand, player hands, etc.)
        """
        pass

    @abstractmethod
    async def request_player_action(
        self,
        player_id: str,
        player_name: str,
        valid_actions: List[Action],
        timeout_seconds: Optional[float] = None,
    ) -> Awaitable[Action]:
        """
        Request an action from a player.

        Args:
            player_id: Unique identifier for the player
            player_name: Display name of the player
            valid_actions: List of valid actions the player can take
            timeout_seconds: Optional timeout for the player's decision

        Returns:
            A future that resolves to the player's chosen action

        Raises:
            TimeoutError: If the player doesn't respond within the timeout period
        """
        pass

    @abstractmethod
    async def notify_game_event(
        self, event_type: Union[str, Enum], data: Dict[str, Any]
    ) -> None:
        """
        Notify the platform of a game event.

        Args:
            event_type: The type of event that occurred
            data: Data associated with the event
        """
        pass

    @abstractmethod
    async def handle_timeout(
        self, player_id: str, player_name: str
    ) -> Awaitable[Action]:
        """
        Handle a player timeout.

        Args:
            player_id: Unique identifier for the player
            player_name: Display name of the player

        Returns:
            A future that resolves to the default action to take on timeout
        """
        pass

    # The following methods have default implementations but can be overridden

    async def initialize(self) -> None:
        """
        Initialize the adapter.

        This method is called when the adapter is first connected to the engine.
        It can be used to set up resources, connections, etc.
        """
        pass

    async def shutdown(self) -> None:
        """
        Shutdown the adapter.

        This method is called when the engine is shutting down. It can be used
        to clean up resources, close connections, etc.
        """
        pass

    def get_sync_methods(self) -> Dict[str, callable]:
        """
        Get a dictionary of synchronous methods for platforms that don't support async.

        Returns:
            A dictionary mapping method names to synchronous wrapper functions
        """
        # Default implementation wraps async methods with synchronous versions
        # that run the async method in a new event loop
        methods = {}

        def wrap_async(async_func):
            def sync_wrapper(*args, **kwargs):
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(async_func(*args, **kwargs))
                finally:
                    loop.close()

            return sync_wrapper

        for name in [
            "render_game_state",
            "request_player_action",
            "notify_game_event",
            "handle_timeout",
            "initialize",
            "shutdown",
        ]:
            if hasattr(self, name):
                methods[name] = wrap_async(getattr(self, name))

        return methods
