"""
Durak API module for Cardsharp.

This module provides a high-level, platform-agnostic API for working with the
Cardsharp Durak engine, supporting both synchronous and asynchronous operation.
"""

import asyncio
import time
import uuid
from typing import Dict, Any, List, Optional, Union, Tuple, Callable

from cardsharp.adapters import PlatformAdapter, CLIAdapter, DummyAdapter
from cardsharp.engine import DurakEngine
from cardsharp.events import EventBus, EngineEventType, EventPriority
from cardsharp.durak.state import GameState, GameStage, DurakRules
from cardsharp.api.base import CardsharpGame


class DurakGame(CardsharpGame):
    """
    High-level, platform-agnostic API for Durak games.

    This class provides a simple interface for creating and running Durak games
    with the Cardsharp engine, abstracting away the details of engine operation and
    event handling.

    Example:
        ```python
        # Async usage
        game = DurakGame(config={'deck_size': 36, 'allow_passing': True})
        await game.initialize()
        await game.start_game()
        player1_id = await game.add_player("Alice")
        player2_id = await game.add_player("Bob")
        await game.deal_initial_cards()
        # Get valid moves
        valid_actions = await game.get_valid_actions(player1_id)
        # Play a card
        await game.play_card(player1_id, 0)  # Play first card in hand
        # Or take all cards (if defending)
        await game.take_cards(player1_id)
        # Or pass (if attacking)
        await game.pass_turn(player1_id)
        # Check if game is over
        is_over = await game.is_game_over()
        await game.shutdown()

        # Sync usage
        game = DurakGame(use_async=False)
        game.initialize_sync()
        # etc.
        ```
    """

    def __init__(
        self,
        adapter: Optional[PlatformAdapter] = None,
        config: Optional[Dict[str, Any]] = None,
        use_async: bool = True,
    ):
        """
        Initialize a new Durak game.

        Args:
            adapter: Platform adapter to use for rendering and input.
                   If None, a CLI adapter will be used.
            config: Configuration options for the game
            use_async: Whether to use async mode
        """
        super().__init__(adapter, config, use_async)

        # Apply default Durak configuration
        default_config = {
            "deck_size": 36,  # 20, 36, or 52
            "allow_passing": False,  # "Perevodnoy" variant
            "allow_throwing_in": True,  # "Podkidnoy" variant
            "max_attack_cards": -1,  # -1 means unlimited
            "attack_limit_by_hand_size": True,
            "trump_selection_method": "bottom_card",
            "lowest_card_starts": True,
            "refill_hands_threshold": 6,
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
        self._action_complete_event = asyncio.Event()

    async def initialize(self) -> None:
        """
        Initialize the Durak game and prepare for play.

        This method initializes the adapter and engine, and sets up
        event handlers for game flow control.
        """
        # First initialize the adapter
        await self.adapter.initialize()

        # Initialize the engine
        self.engine = DurakEngine(self.adapter, self.config)
        await self.engine.initialize()

        # Set up event handlers for game flow control
        self.on(EngineEventType.ROUND_ENDED, self._on_round_ended)
        self.on(EngineEventType.GAME_ENDED, self._on_game_ended)
        self.on(EngineEventType.CUSTOM_EVENT, self._on_custom_event)

    async def shutdown(self) -> None:
        """
        Shut down the Durak game and clean up resources.
        """
        # Clear event handlers by calling the unsubscribe functions
        for event_type, unsubscribe_funcs in self.event_handlers.items():
            for unsubscribe in unsubscribe_funcs:
                unsubscribe()

        # Clear the handlers dictionary
        self.event_handlers.clear()

        # Shutdown the engine and adapter
        await self.engine.shutdown()

    async def start_game(self) -> None:
        """
        Start a new Durak game.

        This creates a new game with the configured options.
        """
        await self.engine.start_game()

    async def add_player(self, name: str, balance: float = 0.0) -> str:
        """
        Add a player to the Durak game.

        Args:
            name: Player's display name
            balance: Not used in Durak but included for API consistency

        Returns:
            Player ID that can be used for future operations
        """
        player_id = await self.engine.add_player(name)

        # Keep track of the player
        self._players[player_id] = {"name": name}

        return player_id

    async def remove_player(self, player_id: str) -> bool:
        """
        Remove a player from the Durak game.

        Args:
            player_id: ID of the player to remove

        Returns:
            True if the player was successfully removed
        """
        # The engine doesn't have a remove_player method, so we need
        # to use the state transition engine directly
        from cardsharp.durak.transitions import StateTransitionEngine

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

    async def deal_initial_cards(self) -> None:
        """
        Deal initial cards to players and start the game.
        """
        await self.engine.deal_initial_cards()

    async def play_card(self, player_id: str, card_index: int) -> bool:
        """
        Play a card from a player's hand.

        Args:
            player_id: ID of the player
            card_index: Index of the card in the player's hand to play

        Returns:
            True if the card was successfully played
        """
        # Reset the action completion event
        self._action_complete_event.clear()

        try:
            await self.engine.execute_player_action(
                player_id=player_id, action="PLAY_CARD", card_index=card_index
            )

            # Wait for the action to complete
            await self._action_complete_event.wait()
            self._action_complete_event.clear()

            return True
        except ValueError:
            # Invalid action
            return False

    async def take_cards(self, player_id: str) -> bool:
        """
        Take all cards on the table (for the defender).

        Args:
            player_id: ID of the player

        Returns:
            True if the cards were successfully taken
        """
        # Reset the action completion event
        self._action_complete_event.clear()

        try:
            await self.engine.execute_player_action(
                player_id=player_id, action="TAKE_CARDS"
            )

            # Wait for the action to complete
            await self._action_complete_event.wait()
            self._action_complete_event.clear()

            return True
        except ValueError:
            # Invalid action
            return False

    async def pass_turn(self, player_id: str) -> bool:
        """
        Pass the turn (for attackers).

        Args:
            player_id: ID of the player

        Returns:
            True if the pass was successful
        """
        # Reset the action completion event
        self._action_complete_event.clear()

        try:
            await self.engine.execute_player_action(player_id=player_id, action="PASS")

            # Wait for the action to complete
            await self._action_complete_event.wait()
            self._action_complete_event.clear()

            return True
        except ValueError:
            # Invalid action
            return False

    async def pass_to_player(self, player_id: str, target_player_id: str) -> bool:
        """
        Pass the attack to another player (Perevodnoy variant).

        Args:
            player_id: ID of the current defender
            target_player_id: ID of the player to pass the attack to

        Returns:
            True if the pass was successful
        """
        # Reset the action completion event
        self._action_complete_event.clear()

        try:
            await self.engine.execute_player_action(
                player_id=player_id,
                action="PASS_TO_PLAYER",
                target_player_id=target_player_id,
            )

            # Wait for the action to complete
            await self._action_complete_event.wait()
            self._action_complete_event.clear()

            return True
        except ValueError:
            # Invalid action
            return False

    async def get_valid_actions(
        self, player_id: str
    ) -> Dict[str, List[Union[int, str]]]:
        """
        Get the valid actions for a player.

        Args:
            player_id: ID of the player

        Returns:
            Dictionary mapping action types to lists of valid parameters
        """
        return self.engine.get_valid_actions(player_id)

    async def is_game_over(self) -> bool:
        """
        Check if the game is over.

        Returns:
            True if the game is over, False otherwise
        """
        return self.engine.is_game_over()

    async def get_loser(self) -> Optional[str]:
        """
        Get the ID of the player who lost the game.

        Returns:
            ID of the losing player, or None if the game is not over
        """
        return self.engine.get_loser()

    # Synchronous API wrappers

    def deal_initial_cards_sync(self) -> None:
        """
        Synchronous wrapper for deal_initial_cards method.
        """
        return self._run_async(self.deal_initial_cards())

    def play_card_sync(self, player_id: str, card_index: int) -> bool:
        """
        Synchronous wrapper for play_card method.
        """
        return self._run_async(self.play_card(player_id, card_index))

    def take_cards_sync(self, player_id: str) -> bool:
        """
        Synchronous wrapper for take_cards method.
        """
        return self._run_async(self.take_cards(player_id))

    def pass_turn_sync(self, player_id: str) -> bool:
        """
        Synchronous wrapper for pass_turn method.
        """
        return self._run_async(self.pass_turn(player_id))

    def pass_to_player_sync(self, player_id: str, target_player_id: str) -> bool:
        """
        Synchronous wrapper for pass_to_player method.
        """
        return self._run_async(self.pass_to_player(player_id, target_player_id))

    def get_valid_actions_sync(
        self, player_id: str
    ) -> Dict[str, List[Union[int, str]]]:
        """
        Synchronous wrapper for get_valid_actions method.
        """
        return self._run_async(self.get_valid_actions(player_id))

    def is_game_over_sync(self) -> bool:
        """
        Synchronous wrapper for is_game_over method.
        """
        return self._run_async(self.is_game_over())

    def get_loser_sync(self) -> Optional[str]:
        """
        Synchronous wrapper for get_loser method.
        """
        return self._run_async(self.get_loser())

    # Event handlers

    def _on_round_ended(self, data: Dict[str, Any]) -> None:
        """
        Handle round ended events for flow control.
        """
        # Set the round complete event
        self._round_complete_event.set()
        # Also set the action complete event
        self._action_complete_event.set()

    def _on_game_ended(self, data: Dict[str, Any]) -> None:
        """
        Handle game ended events.
        """
        # Set the action complete event
        self._action_complete_event.set()

    def _on_custom_event(self, data: Dict[str, Any]) -> None:
        """
        Handle custom events.
        """
        # Set the action complete event for certain custom events
        if data.get("event_name") in [
            "ATTACK_CARD_PLAYED",
            "DEFENSE_CARD_PLAYED",
            "CARD_THROWN_IN",
            "DEFENDER_TOOK_CARDS",
            "ATTACK_PASSED",
            "THROW_IN_PASSED",
            "ATTACK_PASSED_TO_PLAYER",
        ]:
            self._action_complete_event.set()
