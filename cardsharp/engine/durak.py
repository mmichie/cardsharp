"""
Durak card game engine implementation.

This module provides the DurakEngine class, which implements the CardsharpEngine
interface for the game of Durak.
"""

from typing import Dict, Any, List, Optional, Union
import time

from cardsharp.adapters import PlatformAdapter
from cardsharp.engine.base import CardsharpEngine
from cardsharp.events import EngineEventType
from cardsharp.durak.state import (
    GameState,
    GameStage,
    DurakRules,
)
from cardsharp.durak.transitions import StateTransitionEngine


class DurakEngine(CardsharpEngine):
    """
    Engine implementation for the Durak card game.

    This class implements the CardsharpEngine interface for the game of Durak,
    providing methods for starting games, handling player actions, and managing
    the game state.
    """

    def __init__(self, adapter: PlatformAdapter, config: Dict[str, Any] = None):
        """
        Initialize the Durak engine.

        Args:
            adapter: Platform adapter to use for rendering and input
            config: Configuration options for the game
        """
        super().__init__(adapter, config)

        # Apply default configuration
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

        # Create the rules
        self.rules = DurakRules(
            deck_size=self.config.get("deck_size", 36),
            allow_passing=self.config.get("allow_passing", False),
            allow_throwing_in=self.config.get("allow_throwing_in", True),
            max_attack_cards=self.config.get("max_attack_cards", -1),
            attack_limit_by_hand_size=self.config.get(
                "attack_limit_by_hand_size", True
            ),
            trump_selection_method=self.config.get(
                "trump_selection_method", "bottom_card"
            ),
            lowest_card_starts=self.config.get("lowest_card_starts", True),
            refill_hands_threshold=self.config.get("refill_hands_threshold", 6),
        )

        # Initialize the state
        self.state = GameState(rules=self.rules)

    async def initialize(self) -> None:
        """
        Initialize the engine and prepare for a game.
        """
        await super().initialize()

        # Initialize the state with rules
        self.state = StateTransitionEngine.initialize_game(self.state, self.rules)

        # Emit initialization event
        self.event_bus.emit(
            EngineEventType.ENGINE_INIT,
            {
                "engine_type": "durak",
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
        Start a new game of Durak.
        """
        # Initialize the state with rules
        self.state = StateTransitionEngine.initialize_game(self.state, self.rules)

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
        Add a player to the Durak game.

        Args:
            name: Name of the player
            balance: Not used in Durak but included for API consistency

        Returns:
            ID of the added player
        """
        # Add the player to the game state
        self.state = StateTransitionEngine.add_player(self.state, name)

        # Return the player ID
        return self.state.players[-1].id

    async def place_bet(self, player_id: str, amount: float) -> None:
        """
        Place a bet for a player. Not used in Durak.

        Args:
            player_id: ID of the player placing the bet
            amount: Amount to bet
        """
        # Durak doesn't use betting, but we include this for API consistency
        pass

    async def execute_player_action(
        self, player_id: str, action: str, **kwargs
    ) -> None:
        """
        Execute a player action in Durak.

        Args:
            player_id: ID of the player
            action: Action to perform (play_card, take_cards, pass)
            **kwargs: Action-specific parameters
        """
        # Get the player's index
        player_idx = None
        for i, player in enumerate(self.state.players):
            if player.id == player_id:
                player_idx = i
                break

        if player_idx is None:
            raise ValueError(f"Player {player_id} not found")

        # Check if it's the player's turn
        if self.state.active_player_index != player_idx:
            raise ValueError("Not this player's turn")

        # Execute the appropriate action
        if action.upper() == "PLAY_CARD":
            card_index = kwargs.get("card_index", -1)
            if card_index < 0:
                raise ValueError("Invalid card index")

            # Determine if this is an attack, defense, or throw-in
            if self.state.stage == GameStage.ATTACK:
                self.state = StateTransitionEngine.play_attack_card(
                    self.state, player_id, card_index
                )
            elif self.state.stage == GameStage.DEFENSE:
                self.state = StateTransitionEngine.play_defense_card(
                    self.state, player_id, card_index
                )
            elif self.state.stage == GameStage.THROWING_IN:
                self.state = StateTransitionEngine.throw_in_card(
                    self.state, player_id, card_index
                )
            else:
                raise ValueError(f"Cannot play card in {self.state.stage.name} stage")

        elif action.upper() == "TAKE_CARDS":
            if self.state.stage != GameStage.DEFENSE:
                raise ValueError("Can only take cards during defense")
            self.state = StateTransitionEngine.take_cards(self.state, player_id)

        elif action.upper() == "PASS":
            if self.state.stage not in [GameStage.ATTACK, GameStage.THROWING_IN]:
                raise ValueError("Can only pass during attack or throwing in")
            self.state = StateTransitionEngine.pass_attack(self.state, player_id)

        elif action.upper() == "PASS_TO_PLAYER":
            target_player_id = kwargs.get("target_player_id", None)
            if not target_player_id:
                raise ValueError("Missing target player ID")
            if not self.state.rules.allow_passing:
                raise ValueError("Passing to other players is not allowed in this game")
            self.state = StateTransitionEngine.pass_attack_to_player(
                self.state, player_id, target_player_id
            )

        else:
            raise ValueError(f"Unknown action: {action}")

        # Render the new state
        await self.render_state()

    async def deal_initial_cards(self) -> None:
        """
        Deal initial cards to players and start the game.
        """
        if len(self.state.players) < 2:
            raise ValueError("At least 2 players are required to play Durak")

        # Deal cards to players
        self.state = StateTransitionEngine.deal_initial_cards(self.state)

        # Render the state
        await self.render_state()

    async def render_state(self) -> None:
        """
        Render the current game state.
        """
        # Convert the state to a format suitable for the adapter
        adapter_state = self.state.to_adapter_format()

        # Render the state
        await self.adapter.render_game_state(adapter_state)

    def get_valid_actions(self, player_id: str) -> Dict[str, List[Union[int, str]]]:
        """
        Get valid actions for a player.

        Args:
            player_id: ID of the player

        Returns:
            Dictionary mapping action types to lists of valid parameters
        """
        # Find the player
        player_idx = None
        for i, player in enumerate(self.state.players):
            if player.id == player_id:
                player_idx = i
                break

        if player_idx is None:
            return {}  # Player not found

        player = self.state.players[player_idx]

        # If it's not the player's turn, no actions are valid
        if self.state.active_player_index != player_idx:
            return {}

        valid_actions = {}

        # Determine valid actions based on game stage
        if self.state.stage == GameStage.ATTACK and player.is_attacker:
            # Valid attack cards
            valid_card_indices = []

            # First attack can be any card
            if not self.state.table.attack_cards:
                valid_card_indices = list(range(len(player.hand)))
            else:
                # Can only play cards whose ranks are already on the table
                valid_ranks = set(
                    c.rank.rank_value
                    for c in self.state.table.attack_cards
                    + self.state.table.defense_cards
                )

                for i, card in enumerate(player.hand):
                    if card.rank.rank_value in valid_ranks:
                        valid_card_indices.append(i)

            # Attack limit checks
            if (
                self.state.rules.max_attack_cards > 0
                and len(self.state.table.attack_cards)
                >= self.state.rules.max_attack_cards
            ):
                valid_card_indices = []  # Can't play any more attack cards

            if self.state.rules.attack_limit_by_hand_size:
                defender = self.state.players[self.state.defender_index]
                if len(self.state.table.attack_cards) - len(
                    self.state.table.defense_cards
                ) >= len(defender.hand):
                    valid_card_indices = []  # Can't play more cards than defender has

            if valid_card_indices:
                valid_actions["PLAY_CARD"] = valid_card_indices

            # Can always pass attack to next player
            valid_actions["PASS"] = []

        elif self.state.stage == GameStage.DEFENSE and player.is_defender:
            # Valid defense cards
            valid_card_indices = []

            # Get the undefended attack card
            undefended_card = self.state.table.get_undefended_card()
            if undefended_card:
                for i, card in enumerate(player.hand):
                    # Same suit, higher rank
                    if (
                        card.suit == undefended_card.suit
                        and card.rank.rank_value > undefended_card.rank.rank_value
                    ):
                        valid_card_indices.append(i)
                    # Trump card vs non-trump
                    elif (
                        card.suit == self.state.trump_suit
                        and undefended_card.suit != self.state.trump_suit
                    ):
                        valid_card_indices.append(i)

            if valid_card_indices:
                valid_actions["PLAY_CARD"] = valid_card_indices

            # Can always take cards
            valid_actions["TAKE_CARDS"] = []

            # Can pass to another player if rules allow
            if self.state.rules.allow_passing:
                valid_targets = []
                last_defense_card = (
                    self.state.table.defense_cards[-1]
                    if self.state.table.defense_cards
                    else None
                )

                if last_defense_card:
                    rank_value = last_defense_card.rank.rank_value
                    for i, p in enumerate(self.state.players):
                        # Skip self, current attacker, and players who are out
                        if (
                            i != player_idx
                            and i != self.state.attacker_index
                            and not p.is_out
                        ):
                            # Target must have a card of the same rank
                            if any(c.rank.rank_value == rank_value for c in p.hand):
                                valid_targets.append(p.id)

                if valid_targets:
                    valid_actions["PASS_TO_PLAYER"] = valid_targets

        elif self.state.stage == GameStage.THROWING_IN:
            # Valid throw-in cards
            valid_card_indices = []

            # Can only throw in cards whose ranks are already on the table
            valid_ranks = set(
                c.rank.rank_value
                for c in self.state.table.attack_cards + self.state.table.defense_cards
            )

            for i, card in enumerate(player.hand):
                if card.rank.rank_value in valid_ranks:
                    valid_card_indices.append(i)

            # Attack limit checks
            if (
                self.state.rules.max_attack_cards > 0
                and len(self.state.table.attack_cards)
                >= self.state.rules.max_attack_cards
            ):
                valid_card_indices = []  # Can't play any more attack cards

            if self.state.rules.attack_limit_by_hand_size:
                defender = self.state.players[self.state.defender_index]
                if len(self.state.table.attack_cards) - len(
                    self.state.table.defense_cards
                ) >= len(defender.hand):
                    valid_card_indices = []  # Can't play more cards than defender has

            if valid_card_indices:
                valid_actions["PLAY_CARD"] = valid_card_indices

            # Can always pass
            valid_actions["PASS"] = []

        return valid_actions

    def is_game_over(self) -> bool:
        """
        Check if the game is over.

        Returns:
            True if the game is over, False otherwise
        """
        return self.state.game_ended

    def get_loser(self) -> Optional[str]:
        """
        Get the ID of the player who lost the game.

        Returns:
            ID of the losing player, or None if the game is not over
        """
        if not self.is_game_over():
            return None
        return self.state.loser_id
