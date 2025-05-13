"""
War card game API module for Cardsharp.

This module provides a high-level, platform-agnostic API for working with the
Cardsharp War engine, supporting both synchronous and asynchronous operation.
"""

import asyncio
import time
import uuid
from typing import Dict, Any, List, Optional, Union, Tuple, Callable

from cardsharp.adapters import PlatformAdapter, CLIAdapter, DummyAdapter
from cardsharp.engine.war import WarEngine
from cardsharp.events import EventBus, EngineEventType, EventPriority
from cardsharp.war.state import GameState, GameStage
from cardsharp.api.base import CardsharpGame


class WarGame(CardsharpGame):
    """
    High-level, platform-agnostic API for War card games.

    This class provides a simple interface for creating and running War games
    with the Cardsharp engine, abstracting away the details of engine operation and
    event handling.

    Example:
        ```python
        # Async usage
        game = WarGame()
        await game.initialize()
        await game.start_game()
        player1_id = await game.add_player("Alice")
        player2_id = await game.add_player("Bob")
        results = await game.play_round()
        await game.shutdown()

        # Sync usage
        game = WarGame(use_async=False)
        game.initialize_sync()
        game.start_game_sync()
        player1_id = game.add_player_sync("Alice")
        player2_id = game.add_player_sync("Bob")
        results = game.play_round_sync()
        game.shutdown_sync()
        ```
    """

    def __init__(
        self,
        adapter: Optional[PlatformAdapter] = None,
        config: Optional[Dict[str, Any]] = None,
        use_async: bool = True,
    ):
        """
        Initialize a new War card game.

        Args:
            adapter: Platform adapter to use for rendering and input.
                    If None, a CLI adapter will be used.
            config: Configuration options for the game
            use_async: Whether to use async mode
        """
        super().__init__(adapter, config, use_async)

        # Apply default War configuration
        default_config = {
            "shuffle_threshold": 5,
            "deal_delay": 0.3,
        }

        # Merge with provided config
        if config:
            default_config.update(config)

        self.config = default_config

        # Engine will be initialized in initialize()
        self.engine = None

        # Keep track of players
        self._players = {}

        # Set up event flow control
        self._round_complete_event = asyncio.Event()

    async def initialize(self) -> None:
        """
        Initialize the War game and prepare for play.

        This method initializes the adapter and engine, and sets up
        event handlers for game flow control.
        """
        # First initialize the adapter
        await self.adapter.initialize()

        # Initialize the engine
        self.engine = WarEngine(self.adapter, self.config)
        await self.engine.initialize()

        # Set up event handlers for game flow control
        self.on(EngineEventType.ROUND_ENDED, self._on_round_ended)

    async def shutdown(self) -> None:
        """
        Shut down the War game and clean up resources.
        """
        # Clear event handlers
        for event_type, handlers in self.event_handlers.items():
            for handler in handlers:
                # Each handler is actually the unsubscribe function returned by event_bus.on()
                if callable(handler):
                    handler()  # Call the unsubscribe function

        # Shutdown the engine and adapter
        await self.engine.shutdown()

    async def start_game(self) -> None:
        """
        Start a new War game.

        This creates a new game with the configured options.
        """
        await self.engine.start_game()

    async def add_player(self, name: str, balance: float = 0.0) -> str:
        """
        Add a player to the War game.

        Args:
            name: Player's display name
            balance: Not used in War but included for API consistency

        Returns:
            Player ID that can be used for future operations
        """
        player_id = await self.engine.add_player(name)

        # Keep track of the player
        self._players[player_id] = {"name": name}

        return player_id

    async def remove_player(self, player_id: str) -> bool:
        """
        Remove a player from the War game.

        Args:
            player_id: ID of the player to remove

        Returns:
            True if the player was successfully removed
        """
        # The engine doesn't have a remove_player method, so we need
        # to use the state transition engine directly
        from cardsharp.war.transitions import StateTransitionEngine

        current_state = self.engine.state

        # Check if the player exists
        player_exists = False
        for player in current_state.players:
            if player.id == player_id:
                player_exists = True
                break

        if not player_exists:
            return False

        # Remove the player from the state
        new_state = StateTransitionEngine.remove_player(current_state, player_id)

        # Update the engine state
        self.engine.state = new_state

        # Remove from our player tracking
        if player_id in self._players:
            del self._players[player_id]

        return True

    async def get_state(self) -> GameState:
        """
        Get the current game state.

        Returns:
            Current GameState object
        """
        return self.engine.state

    async def play_round(self) -> Dict[str, Any]:
        """
        Play a round of War.

        Returns:
            Dictionary containing round results
        """
        # Reset the round completion event
        self._round_complete_event.clear()

        # Play the round
        round_results = await self.engine.play_round()

        # Wait for the round to complete
        await self._round_complete_event.wait()
        self._round_complete_event.clear()

        return round_results

    async def play_multiple_rounds(self, count: int) -> List[Dict[str, Any]]:
        """
        Play multiple rounds of War.

        Args:
            count: Number of rounds to play

        Returns:
            List of round results
        """
        results = []

        for _ in range(count):
            round_result = await self.play_round()
            results.append(round_result)

        return results

    # Synchronous API wrappers

    def play_round_sync(self) -> Dict[str, Any]:
        """
        Synchronous wrapper for play_round method.
        """
        return self._run_async(self.play_round())

    def play_multiple_rounds_sync(self, count: int) -> List[Dict[str, Any]]:
        """
        Synchronous wrapper for play_multiple_rounds method.
        """
        return self._run_async(self.play_multiple_rounds(count))

    # Event handlers for flow control

    def _on_round_ended(self, data: Dict[str, Any]) -> None:
        """
        Handle round ended events for flow control.
        """
        # Set the round complete event
        self._round_complete_event.set()
