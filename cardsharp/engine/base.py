"""
Base engine class for the Cardsharp framework.

This module provides the abstract base class for all game engines in the
Cardsharp framework. It defines the common interface that all game engines
must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union

from cardsharp.adapters import PlatformAdapter
from cardsharp.events import EventBus


class CardsharpEngine(ABC):
    """
    Abstract base class for all game engines.

    This class defines the common interface that all game engines must implement,
    providing methods for starting games, handling player actions, and managing
    the game state.
    """

    def __init__(self, adapter: PlatformAdapter, config: Dict[str, Any] = None):
        """
        Initialize the engine.

        Args:
            adapter: Platform adapter to use for rendering and input
            config: Configuration options for the game
        """
        self.adapter = adapter
        self.config = config or {}
        self.event_bus = EventBus.get_instance()
        self.state = None

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the engine and prepare for a game.
        """
        await self.adapter.initialize()

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Shut down the engine and clean up resources.
        """
        await self.adapter.shutdown()

    @abstractmethod
    async def start_game(self) -> None:
        """
        Start a new game.
        """
        pass

    @abstractmethod
    async def add_player(self, name: str, balance: float = 1000.0) -> str:
        """
        Add a player to the game.

        Args:
            name: Name of the player
            balance: Starting balance for the player

        Returns:
            ID of the added player
        """
        pass

    @abstractmethod
    async def place_bet(self, player_id: str, amount: float) -> None:
        """
        Place a bet for a player.

        Args:
            player_id: ID of the player placing the bet
            amount: Amount to bet
        """
        pass

    @abstractmethod
    async def execute_player_action(self, player_id: str, action: str) -> None:
        """
        Execute a player action.

        Args:
            player_id: ID of the player
            action: Action to perform
        """
        pass

    @abstractmethod
    async def render_state(self) -> None:
        """
        Render the current game state.
        """
        pass
