"""
Blackjack API module for Cardsharp.

This module provides a high-level, platform-agnostic API for working with the
Cardsharp Blackjack engine, supporting both synchronous and asynchronous operation.
"""

import asyncio
from typing import Dict, Any, List, Optional, Union, Callable, TYPE_CHECKING

from cardsharp.adapters import PlatformAdapter
from cardsharp.engine import BlackjackEngine

if TYPE_CHECKING:
    from asyncio import Task
from cardsharp.events import EngineEventType
from cardsharp.state import GameState, GameStage, StateTransitionEngine
from cardsharp.blackjack.action import Action
from cardsharp.api.base import CardsharpGame


class BlackjackGame(CardsharpGame):
    """
    High-level, platform-agnostic API for Blackjack games.

    This class provides a simple interface for creating and running Blackjack games
    with the Cardsharp engine, abstracting away the details of engine operation and
    event handling.

    Example:
        ```python
        # Async usage
        game = BlackjackGame()
        await game.initialize()
        await game.start_game()
        player_id = await game.add_player("Alice")
        await game.place_bet(player_id, 10.0)
        await game.auto_play_round()
        await game.shutdown()

        # Sync usage
        game = BlackjackGame(use_async=False)
        game.initialize_sync()
        game.start_game_sync()
        player_id = game.add_player_sync("Bob")
        game.place_bet_sync(player_id, 25.0)
        game.auto_play_round_sync()
        game.shutdown_sync()
        ```

    Attributes:
        adapter: The platform adapter used for UI interaction
        engine: The underlying BlackjackEngine
        config: Game configuration options
        event_bus: The event bus for event-based communication
        event_handlers: Dictionary of registered event handlers
        _is_async_mode: Whether the game is operating in async mode
        _auto_actions: Dictionary of automatic actions for players
    """

    def __init__(
        self,
        adapter: Optional[PlatformAdapter] = None,
        config: Optional[Dict[str, Any]] = None,
        use_async: bool = True,
        auto_play: bool = False,
    ):
        """
        Initialize a new Blackjack game.

        Args:
            adapter: Platform adapter to use for rendering and input.
                    If None, a CLI adapter will be used.
            config: Configuration options for the game
            use_async: Whether to use async mode
            auto_play: Whether to automatically play for all players
        """
        super().__init__(adapter, config, use_async)

        # Apply default Blackjack configuration
        default_config = {
            "dealer_rules": {"stand_on_soft_17": True, "peek_for_blackjack": True},
            "deck_count": 6,
            "rules": {
                "blackjack_pays": 1.5,
                "deck_count": 6,
                "dealer_hit_soft_17": False,
                "offer_insurance": True,
                "allow_surrender": True,
                "allow_double_after_split": True,
                "min_bet": 5.0,
                "max_bet": 1000.0,
            },
        }

        # Merge with provided config
        if config:
            # Deep merge the dictionaries
            for key, value in config.items():
                if (
                    key in default_config
                    and isinstance(value, dict)
                    and isinstance(default_config[key], dict)
                ):
                    default_config[key].update(value)
                else:
                    default_config[key] = value

        self.config = default_config
        self._auto_actions = {}
        self._auto_play = auto_play

        # Engine will be initialized in initialize()
        self.engine: Optional[BlackjackEngine] = None

        # Keep track of players for auto-play
        self._players = {}

        # Set up event flow control
        self._round_complete_event = asyncio.Event()
        self._action_complete_events = {}

    @property
    def _engine(self) -> BlackjackEngine:
        """Get the engine, raising an error if not initialized."""
        if not self.engine:
            raise RuntimeError("Game not initialized. Call initialize() first.")
        return self.engine

    async def initialize(self) -> None:
        """
        Initialize the Blackjack game and prepare for play.

        This method initializes the adapter and engine, and sets up
        event handlers for game flow control.
        """
        # First initialize the adapter
        await self.adapter.initialize()

        # Initialize the engine
        self.engine = BlackjackEngine(self.adapter, self.config)
        await self.engine.initialize()

        # Set up event handlers for game flow control
        self.on(EngineEventType.ROUND_ENDED, self._on_round_ended)
        self.on(EngineEventType.PLAYER_ACTION, self._on_player_action)

        if self._auto_play:
            # Set up auto-play handler
            self.on(EngineEventType.USER_INTERACTION_NEEDED, self._handle_auto_play)

    async def shutdown(self) -> None:
        """
        Shut down the Blackjack game and clean up resources.
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
        Start a new Blackjack game.

        This creates a new game with the configured options.
        """
        await self.engine.start_game()

    async def add_player(self, name: str, balance: float = 1000.0) -> str:
        """
        Add a player to the Blackjack game.

        Args:
            name: Player's display name
            balance: Starting balance for the player

        Returns:
            Player ID that can be used for future operations
        """
        player_id = await self.engine.add_player(name, balance)

        # Keep track of the player for auto-play
        self._players[player_id] = {"name": name, "balance": balance}

        return player_id

    async def remove_player(self, player_id: str) -> bool:
        """
        Remove a player from the Blackjack game.

        Args:
            player_id: ID of the player to remove

        Returns:
            True if the player was successfully removed
        """
        # The engine doesn't have a remove_player method, so we need
        # to use the state transition engine directly
        current_state = self._engine.state

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
        self._engine.state = new_state

        # Remove from our player tracking
        if player_id in self._players:
            del self._players[player_id]

        # Remove from auto actions
        if player_id in self._auto_actions:
            del self._auto_actions[player_id]

        return True

    async def get_state(self) -> GameState:
        """
        Get the current game state.

        Returns:
            Current GameState object
        """
        return self._engine.state

    async def place_bet(self, player_id: str, amount: float) -> bool:
        """
        Place a bet for a player.

        Args:
            player_id: ID of the player placing the bet
            amount: Amount to bet

        Returns:
            True if the bet was successfully placed
        """
        try:
            await self.engine.place_bet(player_id, amount)
            return True
        except ValueError:
            return False

    async def execute_action(
        self,
        player_id: str,
        action: Union[str, Action],
        wait_for_completion: bool = True,
    ) -> bool:
        """
        Execute a player action.

        Args:
            player_id: ID of the player performing the action
            action: Action to perform (can be string or Action enum)
            wait_for_completion: Whether to wait for the action to complete

        Returns:
            True if the action was successfully executed
        """
        if isinstance(action, str):
            # Convert to Action enum if string
            try:
                action = getattr(Action, action.upper())
            except (AttributeError, KeyError):
                return False

        try:
            # Set up the completion event if we're waiting
            if wait_for_completion:
                self._action_complete_events[player_id] = asyncio.Event()

            # Execute the action
            await self.engine.execute_player_action(player_id, action.name)

            # Wait for completion if requested
            if wait_for_completion and player_id in self._action_complete_events:
                await self._action_complete_events[player_id].wait()
                del self._action_complete_events[player_id]

            return True
        except ValueError:
            # Clean up event if we failed
            if wait_for_completion and player_id in self._action_complete_events:
                del self._action_complete_events[player_id]
            return False

    async def set_auto_action(
        self,
        player_id: str,
        action_strategy: Union[Callable, List[Action], Action, str] = None,
    ) -> None:
        """
        Set an automatic action strategy for a player.

        Args:
            player_id: ID of the player
            action_strategy: Strategy for selecting actions automatically
                            - If a callable, it will be called with (player_id, valid_actions)
                            - If a list of Actions, they will be used in sequence
                            - If a single Action or string, it will always be used
                            - If None, auto-play will be disabled for this player
        """
        if action_strategy is None:
            # Disable auto-play for this player
            if player_id in self._auto_actions:
                del self._auto_actions[player_id]
            return

        if callable(action_strategy):
            # Store the callable strategy
            self._auto_actions[player_id] = action_strategy
        elif isinstance(action_strategy, list):
            # Create a sequence strategy
            actions = action_strategy.copy()

            def sequence_strategy(player_id, valid_actions):
                if not actions:
                    # Default to STAND if we run out of actions
                    return (
                        Action.STAND
                        if Action.STAND in valid_actions
                        else valid_actions[0]
                    )
                next_action = actions.pop(0)
                if next_action in valid_actions:
                    return next_action
                return valid_actions[0]

            self._auto_actions[player_id] = sequence_strategy
        else:
            # Single action strategy
            if isinstance(action_strategy, str):
                try:
                    # Convert to Action enum if string
                    action_strategy = getattr(Action, action_strategy.upper())
                except (AttributeError, KeyError):
                    # Default to STAND if invalid
                    action_strategy = Action.STAND

            # Create a constant strategy
            def constant_strategy(player_id, valid_actions):
                if action_strategy in valid_actions:
                    return action_strategy
                return valid_actions[0]

            self._auto_actions[player_id] = constant_strategy

    async def auto_play_round(self, default_bet: float = 10.0) -> Dict[str, Any]:
        """
        Automatically play a complete round of Blackjack.

        This method will:
        1. Place bets for all players (using default_bet)
        2. Wait for the round to complete
        3. Return the results

        Args:
            default_bet: Default bet amount for all players

        Returns:
            Dictionary of round results
        """
        # Reset the round completion event
        self._round_complete_event.clear()

        # Check current stage
        current_state = await self.get_state()
        if current_state.stage != GameStage.PLACING_BETS:
            # We need to wait for the current round to complete
            await self._round_complete_event.wait()
            self._round_complete_event.clear()

        # Place bets for all players
        for player_id in self._players.keys():
            # Find the player state to get current balance
            player_state = None
            for player in current_state.players:
                if player.id == player_id:
                    player_state = player
                    break

            if player_state and player_state.balance >= default_bet:
                await self.place_bet(player_id, default_bet)

        # Enable auto-play for all players that don't have custom strategies
        for player_id in self._players.keys():
            if player_id not in self._auto_actions:
                # Use basic strategy
                await self.set_auto_action(player_id, self._basic_strategy)

        # Wait for the round to complete
        await self._round_complete_event.wait()
        self._round_complete_event.clear()

        # Return the final state
        final_state = await self.get_state()
        return final_state.to_dict()

    # Synchronous API wrappers (in addition to those inherited from CardsharpGame)

    def place_bet_sync(self, player_id: str, amount: float) -> bool:
        """
        Synchronous wrapper for place_bet method.
        """
        return self._run_async(self.place_bet(player_id, amount))

    def execute_action_sync(
        self,
        player_id: str,
        action: Union[str, Action],
        wait_for_completion: bool = True,
    ) -> bool:
        """
        Synchronous wrapper for execute_action method.
        """
        return self._run_async(
            self.execute_action(player_id, action, wait_for_completion)
        )

    def set_auto_action_sync(
        self,
        player_id: str,
        action_strategy: Union[Callable, List[Action], Action, str] = None,
    ) -> None:
        """
        Synchronous wrapper for set_auto_action method.
        """
        return self._run_async(self.set_auto_action(player_id, action_strategy))

    def auto_play_round_sync(self, default_bet: float = 10.0) -> Dict[str, Any]:
        """
        Synchronous wrapper for auto_play_round method.
        """
        return self._run_async(self.auto_play_round(default_bet))

    # Event handlers for flow control

    def _on_round_ended(self, data: Dict[str, Any]) -> None:
        """
        Handle round ended events for flow control.
        """
        # Set the round complete event
        self._round_complete_event.set()

    def _on_player_action(self, data: Dict[str, Any]) -> None:
        """
        Handle player action events for flow control.
        """
        player_id = data.get("player_id")
        if player_id and player_id in self._action_complete_events:
            # Set the action complete event
            self._action_complete_events[player_id].set()

    async def _handle_auto_play(self, data: Dict[str, Any]) -> None:
        """
        Handle auto-play for players based on their strategies.
        """
        if data.get("action") != "request_player_action":
            return

        player_id = data.get("player_id")
        valid_actions = data.get("valid_actions", [])

        # Convert action strings to enum
        valid_action_enums = []
        for action_str in valid_actions:
            try:
                valid_action_enums.append(getattr(Action, action_str))
            except (AttributeError, KeyError):
                pass

        if not player_id or not valid_action_enums:
            return

        # Check if we have an auto strategy for this player
        if player_id in self._auto_actions:
            strategy = self._auto_actions[player_id]
            # Call the strategy function to get the action
            action = strategy(player_id, valid_action_enums)

            # Execute the action
            try:
                await self.engine.execute_player_action(player_id, action.name)
            except (ValueError, AttributeError):
                # If invalid, use the first valid action
                await self.engine.execute_player_action(
                    player_id, valid_action_enums[0].name
                )

    # Built-in strategies for auto-play

    @staticmethod
    def _basic_strategy(player_id: str, valid_actions: List[Action]) -> Action:
        """
        Basic Blackjack strategy for auto-play.

        This is a simple implementation of basic strategy.
        """
        # Use a simple strategy:
        # 1. Split pairs if available
        if Action.SPLIT in valid_actions:
            return Action.SPLIT

        # 2. Double on 9-11 if available
        if Action.DOUBLE in valid_actions:
            return Action.DOUBLE

        # 3. Stand on 17+
        # 4. Hit on 16 or lower
        # This requires more information about the hand, which we don't have here
        # For simplicity, just stand if it's an option, otherwise hit
        if Action.STAND in valid_actions:
            return Action.STAND

        if Action.HIT in valid_actions:
            return Action.HIT

        # Default to the first valid action
        return valid_actions[0]
