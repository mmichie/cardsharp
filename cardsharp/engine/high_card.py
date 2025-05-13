"""
High Card engine implementation.

This module provides the HighCardEngine class, which implements the CardsharpEngine
interface for the game of High Card.
"""

from typing import Dict, Any, List, Optional, Union
import asyncio
import time
import random
from dataclasses import replace

from cardsharp.adapters import PlatformAdapter
from cardsharp.engine.base import CardsharpEngine
from cardsharp.events import EventBus, EngineEventType
from cardsharp.common.card import Card, Rank, Suit
from cardsharp.common.deck import Deck
from cardsharp.high_card.state import GameState, PlayerState, GameStage
from cardsharp.high_card.transitions import StateTransitionEngine


class HighCardEngine(CardsharpEngine):
    """
    Engine implementation for High Card.

    This class implements the CardsharpEngine interface for the game of High Card,
    providing methods for starting games, handling player actions, and managing
    the game state.
    """

    def __init__(self, adapter: PlatformAdapter, config: Dict[str, Any] = None):
        """
        Initialize the High Card engine.

        Args:
            adapter: Platform adapter to use for rendering and input
            config: Configuration options for the game
        """
        super().__init__(adapter, config)
        self.state = GameState()

        # Set up simulated shoe
        self.deck = Deck()
        self.shuffle_threshold = 5  # Reshuffle when cards remaining get below this

    async def initialize(self) -> None:
        """
        Initialize the engine and prepare for a game.
        """
        await super().initialize()

        # Initialize the deck
        self.deck.reset()
        self.deck.shuffle()

        # Emit initialization event
        self.event_bus.emit(
            EngineEventType.ENGINE_INIT,
            {
                "engine_type": "high_card",
                "config": self.config,
                "timestamp": time.time(),
            },
        )

    async def shutdown(self) -> None:
        """
        Shut down the engine and clean up resources.
        """
        # Emit shutdown event
        self.event_bus.emit(EngineEventType.ENGINE_SHUTDOWN, {"timestamp": time.time()})

        await super().shutdown()

    async def start_game(self) -> None:
        """
        Start a new game of High Card.
        """
        # Create a new game state
        self.state = GameState()

        # Shuffle the deck
        self.deck.reset()
        self.deck.shuffle()

        # Emit game created event
        self.event_bus.emit(
            EngineEventType.GAME_CREATED,
            {"game_id": self.state.id, "timestamp": time.time()},
        )

        # Transition to waiting for players stage
        self.state = StateTransitionEngine.change_stage(
            self.state, GameStage.WAITING_FOR_PLAYERS
        )

        # Emit game started event
        self.event_bus.emit(
            EngineEventType.GAME_STARTED,
            {"game_id": self.state.id, "timestamp": time.time()},
        )

    async def add_player(self, name: str, balance: float = 0.0) -> str:
        """
        Add a player to the High Card game.

        Args:
            name: Name of the player
            balance: Not used in High Card but included for API consistency

        Returns:
            ID of the added player
        """
        # Add the player to the game state
        self.state = StateTransitionEngine.add_player(self.state, name)

        # Return the player ID
        return self.state.players[-1].id

    async def place_bet(self, player_id: str, amount: float) -> None:
        """
        Place a bet for a player. Not used in High Card.

        Args:
            player_id: ID of the player placing the bet
            amount: Amount to bet
        """
        # High Card doesn't use betting, but we include this for API consistency
        pass

    async def execute_player_action(self, player_id: str, action: str) -> None:
        """
        Execute a player action. In High Card, players don't take actions.

        Args:
            player_id: ID of the player
            action: Action to perform
        """
        # High Card doesn't use player actions, but we include this for API consistency
        pass

    async def play_round(self) -> Dict[str, Any]:
        """
        Play a round of High Card.

        Returns:
            Dictionary containing round results
        """
        # Check if we have enough players
        if len(self.state.players) < 2:
            raise ValueError("At least 2 players are required to play High Card")

        # Reset the state for a new round
        self.state = StateTransitionEngine.reset_for_new_round(self.state)

        # Deal a card to each player
        player_list = list(self.state.players)
        random.shuffle(player_list)  # Randomize deal order

        for player in player_list:
            # Check if we need to reshuffle
            if self.deck.size < self.shuffle_threshold:
                self.deck.reset()
                self.deck.shuffle()

            # Deal a card to the player
            card = self.deck.deal()
            self.state = StateTransitionEngine.deal_card(self.state, card, player.id)

            # Render after each deal for visual effect
            await self.render_state()
            await asyncio.sleep(0.3)  # Short pause for effect

        # Change stage to comparing cards
        self.state = StateTransitionEngine.change_stage(
            self.state, GameStage.COMPARING_CARDS
        )

        # Determine the winner
        self.state = StateTransitionEngine.determine_winner(self.state)

        # Render the final state
        await self.render_state()

        # Return the round results
        return self.state.to_dict()

    async def render_state(self) -> None:
        """
        Render the current game state.
        """
        # Convert the state to a format suitable for the adapter
        adapter_state = self.state.to_adapter_format()

        # Render the state
        await self.adapter.render_game_state(adapter_state)

    def _deal_card(self) -> Card:
        """
        Deal a card from the deck.

        Returns:
            Card object
        """
        # Check if we need to reshuffle
        if self.deck.size < self.shuffle_threshold:
            self.deck.reset()
            self.deck.shuffle()

        # Deal a card
        return self.deck.deal()
