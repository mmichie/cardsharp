"""
Blackjack engine implementation.

This module provides the BlackjackEngine class, which implements the CardsharpEngine
interface for the game of blackjack.
"""

from typing import Dict, Any, List, Optional, Union
import asyncio
import time
from dataclasses import replace

from cardsharp.adapters import PlatformAdapter
from cardsharp.engine.base import CardsharpEngine
from cardsharp.events import EventBus, EngineEventType
from cardsharp.state import (
    GameState,
    PlayerState,
    DealerState,
    HandState,
    GameStage,
    StateTransitionEngine,
)


class BlackjackEngine(CardsharpEngine):
    """
    Engine implementation for Blackjack.

    This class implements the CardsharpEngine interface for the game of blackjack,
    providing methods for starting games, handling player actions, and managing
    the game state.
    """

    def __init__(self, adapter: PlatformAdapter, config: Dict[str, Any] = None):
        """
        Initialize the blackjack engine.

        Args:
            adapter: Platform adapter to use for rendering and input
            config: Configuration options for the game
        """
        super().__init__(adapter, config)
        self.state = GameState()
        self.dealer_rules = self.config.get("dealer_rules", {"stand_on_soft_17": True})

        # Set up simulated shoe
        self.deck_count = self.config.get("deck_count", 6)
        self.shoe = []
        self.shoe_index = 0

        # Set up rules
        self.rules = self.config.get(
            "rules",
            {
                "blackjack_pays": 1.5,
                "deck_count": self.deck_count,
                "dealer_hit_soft_17": not self.dealer_rules.get(
                    "stand_on_soft_17", True
                ),
                "allow_double_after_split": True,
                "allow_surrender": True,
                "allow_late_surrender": False,
            },
        )

        # Update state with rules
        self.state = GameState(rules=self.rules)

    async def initialize(self) -> None:
        """
        Initialize the engine and prepare for a game.
        """
        await super().initialize()

        # Initialize the shoe
        self._init_shoe()

        # Emit initialization event
        self.event_bus.emit(
            EngineEventType.ENGINE_INIT,
            {
                "engine_type": "blackjack",
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
        Start a new game of blackjack.
        """
        # Create a new game state
        self.state = GameState(rules=self.rules)

        # Shuffle the shoe
        self._shuffle_shoe()

        # Emit game created event
        self.event_bus.emit(
            EngineEventType.GAME_CREATED,
            {"game_id": self.state.id, "rules": self.rules, "timestamp": time.time()},
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

    async def add_player(self, name: str, balance: float = 1000.0) -> str:
        """
        Add a player to the blackjack game.

        Args:
            name: Name of the player
            balance: Starting balance for the player

        Returns:
            ID of the added player
        """
        # Add the player to the game state
        self.state = StateTransitionEngine.add_player(
            self.state, name=name, balance=balance
        )

        # If this is the first player, transition to betting stage
        if len(self.state.players) == 1:
            self.state = StateTransitionEngine.change_stage(
                self.state, GameStage.PLACING_BETS
            )

        # Return the player ID
        return self.state.players[-1].id

    async def place_bet(self, player_id: str, amount: float) -> None:
        """
        Place a bet for a player.

        Args:
            player_id: ID of the player placing the bet
            amount: Amount to bet
        """
        if self.state.stage != GameStage.PLACING_BETS:
            raise ValueError("Cannot place bet at this stage")

        # Place the bet
        self.state = StateTransitionEngine.place_bet(
            self.state, player_id=player_id, amount=amount
        )

        # Check if all players have placed bets
        all_bets_placed = True
        for player in self.state.players:
            if not player.hands:
                all_bets_placed = False
                break

        # If all players have placed bets, deal the cards
        if all_bets_placed:
            await self._deal_initial_cards()

    async def execute_player_action(self, player_id: str, action: str) -> None:
        """
        Execute a player action.

        Args:
            player_id: ID of the player
            action: Action to perform (hit, stand, double, split, surrender)
        """
        if self.state.stage != GameStage.PLAYER_TURN:
            raise ValueError("Not player's turn")

        # Get the player
        player = None
        for p in self.state.players:
            if p.id == player_id:
                player = p
                break

        if not player:
            raise ValueError(f"Player {player_id} not found")

        # Execute the action
        if action.upper() == "HIT":
            # Deal a card
            card = self._deal_card()
            self.state = StateTransitionEngine.player_action(
                self.state, player_id=player_id, action=action, additional_card=card
            )

        elif action.upper() == "STAND":
            # Stand - move to next hand/player
            self.state = StateTransitionEngine.player_action(
                self.state, player_id=player_id, action=action
            )

        elif action.upper() == "DOUBLE":
            # Double - double bet and deal one more card
            card = self._deal_card()
            self.state = StateTransitionEngine.player_action(
                self.state, player_id=player_id, action=action, additional_card=card
            )

        elif action.upper() == "SPLIT":
            # Split - create two hands from one
            self.state = StateTransitionEngine.player_action(
                self.state, player_id=player_id, action=action
            )

            # Deal a card to each of the new hands
            # The split was successful - deal cards to both new hands
            player_idx = -1
            for i, p in enumerate(self.state.players):
                if p.id == player_id:
                    player_idx = i
                    break

            if player_idx >= 0:
                player = self.state.players[player_idx]
                # Deal to first hand
                card1 = self._deal_card()
                self.state = StateTransitionEngine.deal_card(
                    self.state,
                    card=card1,
                    to_dealer=False,
                    player_id=player_id,
                    hand_index=player.current_hand_index,
                )

                # Deal to second hand
                card2 = self._deal_card()
                self.state = StateTransitionEngine.deal_card(
                    self.state,
                    card=card2,
                    to_dealer=False,
                    player_id=player_id,
                    hand_index=player.current_hand_index + 1,
                )

        elif action.upper() == "SURRENDER":
            # Surrender - forfeit half the bet
            self.state = StateTransitionEngine.player_action(
                self.state, player_id=player_id, action=action
            )

        # Check if we've moved to dealer's turn
        if self.state.stage == GameStage.DEALER_TURN:
            await self._play_dealer_turn()

        # Render the new state
        await self.render_state()

    async def render_state(self) -> None:
        """
        Render the current game state.
        """
        # Convert the state to a format suitable for the adapter
        adapter_state = self.state.to_adapter_format()

        # Render the state
        await self.adapter.render_game_state(adapter_state)

    async def _deal_initial_cards(self) -> None:
        """
        Deal the initial cards to all players and the dealer.
        """
        # Transition to dealing stage
        self.state = StateTransitionEngine.change_stage(self.state, GameStage.DEALING)

        # Deal first card to each player
        for player in self.state.players:
            card = self._deal_card()
            self.state = StateTransitionEngine.deal_card(
                self.state,
                card=card,
                to_dealer=False,
                player_id=player.id,
                hand_index=0,
            )

        # Deal first card to dealer (visible)
        dealer_card1 = self._deal_card()
        self.state = StateTransitionEngine.deal_card(
            self.state, card=dealer_card1, to_dealer=True, is_visible=True
        )

        # Deal second card to each player
        for player in self.state.players:
            card = self._deal_card()
            self.state = StateTransitionEngine.deal_card(
                self.state,
                card=card,
                to_dealer=False,
                player_id=player.id,
                hand_index=0,
            )

        # Deal second card to dealer (hidden)
        dealer_card2 = self._deal_card()
        self.state = StateTransitionEngine.deal_card(
            self.state, card=dealer_card2, to_dealer=True, is_visible=False
        )

        # Render the state
        await self.render_state()

        # Check for dealer blackjack with an Ace showing
        if (
            hasattr(dealer_card1, "rank")
            and dealer_card1.rank == "A"
            and self.dealer_rules.get("peek_for_blackjack", True)
        ):
            dealer_hand = self.state.dealer.hand
            if dealer_hand.is_blackjack:
                # Dealer has blackjack - reveal hole card
                dealer_state = replace(self.state.dealer, visible_card_count=2)
                self.state = replace(self.state, dealer=dealer_state)

                # Resolve hands
                self.state = StateTransitionEngine.change_stage(
                    self.state, GameStage.END_ROUND
                )
                self.state = StateTransitionEngine.resolve_hands(self.state)

                # Render the state
                await self.render_state()

                # Prepare for next round
                self.state = StateTransitionEngine.prepare_new_round(self.state)
                return

        # Check for dealer blackjack with a ten-value card showing
        if (
            hasattr(dealer_card1, "value")
            and dealer_card1.value == 10
            and self.dealer_rules.get("peek_for_blackjack", True)
        ):
            dealer_hand = self.state.dealer.hand
            if dealer_hand.is_blackjack:
                # Dealer has blackjack - reveal hole card
                dealer_state = replace(self.state.dealer, visible_card_count=2)
                self.state = replace(self.state, dealer=dealer_state)

                # Resolve hands
                self.state = StateTransitionEngine.change_stage(
                    self.state, GameStage.END_ROUND
                )
                self.state = StateTransitionEngine.resolve_hands(self.state)

                # Render the state
                await self.render_state()

                # Prepare for next round
                self.state = StateTransitionEngine.prepare_new_round(self.state)
                return

        # If insurance is offered, handle it here
        if (
            hasattr(dealer_card1, "rank")
            and dealer_card1.rank == "A"
            and self.rules.get("offer_insurance", True)
        ):
            # Offer insurance to players
            self.state = StateTransitionEngine.change_stage(
                self.state, GameStage.INSURANCE
            )

            # Insurance logic would go here...

            # For now, just move to player turn
            self.state = StateTransitionEngine.change_stage(
                self.state, GameStage.PLAYER_TURN
            )
        else:
            # Move directly to player turn
            self.state = StateTransitionEngine.change_stage(
                self.state, GameStage.PLAYER_TURN
            )

        # Render the state
        await self.render_state()

        # Start player turns
        await self._handle_player_turns()

    async def _handle_player_turns(self) -> None:
        """
        Handle player turns.
        """
        # Check for player blackjacks
        player_blackjacks = []
        for i, player in enumerate(self.state.players):
            for j, hand in enumerate(player.hands):
                if hand.is_blackjack:
                    player_blackjacks.append((i, j))

        # Handle player blackjacks
        for player_idx, hand_idx in player_blackjacks:
            player = self.state.players[player_idx]

            # Only handle if this is the current hand
            if (
                player_idx == self.state.current_player_index
                and hand_idx == player.current_hand_index
            ):
                # Stand on blackjack
                self.state = StateTransitionEngine.player_action(
                    self.state, player_id=player.id, action="STAND"
                )

        # Process player turns until we move to dealer turn
        while self.state.stage == GameStage.PLAYER_TURN:
            # Get the current player and hand
            player = self.state.current_player

            # Use the adapter to request an action
            try:
                valid_actions = self._get_valid_actions()

                # Request action from the adapter
                action = await self.adapter.request_player_action(
                    player_id=player.id,
                    player_name=player.name,
                    valid_actions=valid_actions,
                    timeout_seconds=30.0,
                )

                # Execute the action
                await self.execute_player_action(player.id, action.name)

            except asyncio.TimeoutError:
                # Handle timeout
                action = await self.adapter.handle_timeout(
                    player_id=player.id, player_name=player.name
                )

                # Execute the default action
                await self.execute_player_action(player.id, action.name)

    async def _play_dealer_turn(self) -> None:
        """
        Play the dealer's turn.
        """
        # Make dealer's hole card visible
        dealer_state = replace(
            self.state.dealer, visible_card_count=len(self.state.dealer.hand.cards)
        )
        self.state = replace(self.state, dealer=dealer_state)

        # Render the state
        await self.render_state()

        # Play dealer's turn according to rules
        while not self.state.dealer.is_done:
            dealer_value = self.state.dealer.hand.value
            dealer_is_soft = self.state.dealer.hand.is_soft

            # Dealer hits until 17 or higher
            if dealer_value < 17 or (
                dealer_value == 17
                and dealer_is_soft
                and not self.dealer_rules.get("stand_on_soft_17", True)
            ):
                # Hit
                card = self._deal_card()
                self.state = StateTransitionEngine.dealer_action(
                    self.state, action="HIT", additional_card=card
                )

                # Render the state
                await self.render_state()

                # Short delay for animation
                await asyncio.sleep(0.5)
            else:
                # Stand
                self.state = StateTransitionEngine.dealer_action(
                    self.state, action="STAND"
                )

        # Resolve hands
        self.state = StateTransitionEngine.resolve_hands(self.state)

        # Render the state
        await self.render_state()

        # Prepare for next round
        self.state = StateTransitionEngine.prepare_new_round(self.state)

    def _get_valid_actions(self) -> List[str]:
        """
        Get the valid actions for the current player and hand.

        Returns:
            List of valid actions
        """
        # Import locally to avoid circular imports
        from cardsharp.blackjack.action import Action

        player = self.state.current_player
        if not player or not player.current_hand:
            return []

        hand = player.current_hand

        # Basic actions
        valid_actions = [Action.HIT, Action.STAND]

        # Double is allowed with two cards
        if len(hand.cards) == 2 and player.balance >= hand.bet:
            valid_actions.append(Action.DOUBLE)

        # Split is allowed with two cards of the same rank
        if (
            len(hand.cards) == 2
            and hand.cards[0].rank == hand.cards[1].rank
            and player.balance >= hand.bet
        ):
            valid_actions.append(Action.SPLIT)

        # Surrender is allowed as first action with two cards
        if (
            len(hand.cards) == 2
            and player.current_hand_index == 0
            and self.rules.get("allow_surrender", True)
        ):
            valid_actions.append(Action.SURRENDER)

        return valid_actions

    def _init_shoe(self) -> None:
        """
        Initialize the shoe with cards.
        """
        # Create a simple representation of a card deck
        ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        suits = ["♠", "♥", "♦", "♣"]

        # Simple card class for simulation
        class Card:
            def __init__(self, rank, suit):
                self.rank = rank
                self.suit = suit

                # Set card value
                if rank in ["J", "Q", "K"]:
                    self.value = 10
                elif rank == "A":
                    self.value = (
                        11  # Ace is handled specially in hand value calculation
                    )
                else:
                    self.value = int(rank)

            def __str__(self):
                return f"{self.rank}{self.suit}"

        # Create the shoe
        self.shoe = []
        for _ in range(self.deck_count):
            for rank in ranks:
                for suit in suits:
                    self.shoe.append(Card(rank, suit))

        # Shuffle the shoe
        self._shuffle_shoe()

    def _shuffle_shoe(self) -> None:
        """
        Shuffle the shoe.
        """
        import random

        random.shuffle(self.shoe)
        self.shoe_index = 0

        # Update the state with the new shoe size
        self.state = replace(self.state, shoe_cards_remaining=len(self.shoe))

        # Emit shuffle event
        self.event_bus.emit(
            EngineEventType.SHUFFLE,
            {
                "game_id": self.state.id,
                "deck_count": self.deck_count,
                "cards_remaining": len(self.shoe) - self.shoe_index,
                "timestamp": time.time(),
            },
        )

    def _deal_card(self) -> Any:
        """
        Deal a card from the shoe.

        Returns:
            Card object
        """
        # Check if we need to shuffle
        if self.shoe_index >= len(self.shoe) * 0.75:  # Reshuffle at 75% penetration
            self._shuffle_shoe()

        # Deal a card
        card = self.shoe[self.shoe_index]
        self.shoe_index += 1

        # Update the state with the new shoe size
        self.state = replace(
            self.state, shoe_cards_remaining=len(self.shoe) - self.shoe_index
        )

        return card
