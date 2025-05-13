"""
State transition functions for the War card game.

This module provides pure functions for transitioning between game states,
without modifying the original state objects.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import replace

from cardsharp.common.card import Card
from cardsharp.events import EventBus, EngineEventType
from cardsharp.war.state import GameState, PlayerState, WarState, GameStage, RoundResult


class StateTransitionEngine:
    """
    Pure functions for state transitions in War.

    This class contains static methods that implement game state transitions.
    Each method takes a state and returns a new state, without modifying the
    original.
    """

    @staticmethod
    def add_player(state: GameState, name: str) -> GameState:
        """
        Add a player to the game.

        Args:
            state: Current game state
            name: Name of the player to add

        Returns:
            New game state with the player added
        """
        # Create a new player
        new_player = PlayerState(name=name)

        # Create a new list of players with the new player added
        new_players = list(state.players)
        new_players.append(new_player)

        # Create and return a new game state
        new_state = replace(state, players=new_players)

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.PLAYER_JOINED,
            {
                "game_id": state.id,
                "player_id": new_player.id,
                "player_name": new_player.name,
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def remove_player(state: GameState, player_id: str) -> GameState:
        """
        Remove a player from the game.

        Args:
            state: Current game state
            player_id: ID of the player to remove

        Returns:
            New game state with the player removed
        """
        # Find the player's index
        player_index = None
        for i, player in enumerate(state.players):
            if player.id == player_id:
                player_index = i
                break

        if player_index is None:
            # Player not found, return the original state
            return state

        # Create a new list of players without the target player
        new_players = list(state.players)
        removed_player = new_players.pop(player_index)

        # Create and return a new game state
        new_state = replace(state, players=new_players)

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.PLAYER_LEFT,
            {
                "game_id": state.id,
                "player_id": removed_player.id,
                "player_name": removed_player.name,
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def deal_card(state: GameState, card: Card, player_id: str) -> GameState:
        """
        Deal a card to a player.

        Args:
            state: Current game state
            card: Card to deal
            player_id: ID of the player to deal to

        Returns:
            New game state with the card dealt
        """
        # Find the player
        player_index = None
        for i, player in enumerate(state.players):
            if player.id == player_id:
                player_index = i
                break

        if player_index is None:
            # Player not found, return the original state
            return state

        # Create a new player with the card
        old_player = state.players[player_index]
        new_player = replace(old_player, card=card)

        # Create a new list of players with the updated player
        new_players = list(state.players)
        new_players[player_index] = new_player

        # Create and return a new game state
        new_state = replace(
            state,
            players=new_players,
            deck_cards_remaining=state.deck_cards_remaining - 1,
        )

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.CARD_DEALT,
            {
                "game_id": state.id,
                "player_id": player_id,
                "player_name": new_player.name,
                "card": str(card),
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def compare_cards(state: GameState) -> Tuple[GameState, RoundResult]:
        """
        Compare cards and determine the winner or a war.

        Args:
            state: Current game state

        Returns:
            Tuple of (new game state, round result)
        """
        # Need at least 2 players with cards
        if len(state.players) < 2 or any(p.card is None for p in state.players):
            return state, RoundResult.WIN

        # Find the highest card
        highest_card_value = -1
        highest_card_players = []

        for player in state.players:
            if player.card is None:
                continue

            card_value = player.card.rank.rank_value

            if card_value > highest_card_value:
                highest_card_value = card_value
                highest_card_players = [player]
            elif card_value == highest_card_value:
                highest_card_players.append(player)

        # Check if we have a tie (war)
        if len(highest_card_players) > 1:
            # Create war state
            war_cards = []
            for player in state.players:
                if player.card:
                    war_cards.append((player.id, player.card))

            war_state = WarState(cards_in_war=war_cards, is_active=True)

            # Create and return a new game state
            new_state = replace(
                state,
                war_state=war_state,
                stage=GameStage.WAR,
            )

            # Emit war event
            event_bus = EventBus.get_instance()
            event_bus.emit(
                EngineEventType.CUSTOM_EVENT,
                {
                    "event_name": "WAR_STARTED",
                    "game_id": state.id,
                    "players": [p.name for p in highest_card_players],
                    "card_value": highest_card_value,
                    "timestamp": new_state.timestamp,
                },
            )

            return new_state, RoundResult.WAR

        # We have a winner
        winner = highest_card_players[0]

        # Update stats for all players
        new_players = []
        for player in state.players:
            if player.id == winner.id:
                # Update winner stats
                new_current_streak = player.current_streak + 1
                new_max_streak = max(player.max_streak, new_current_streak)
                new_player = replace(
                    player,
                    wins=player.wins + 1,
                    current_streak=new_current_streak,
                    max_streak=new_max_streak,
                )
            else:
                # Reset streak for losers
                new_player = replace(player, current_streak=0)

            new_players.append(new_player)

        # Create and return a new game state
        new_state = replace(
            state,
            players=new_players,
            winner_id=winner.id,
            rounds_played=state.rounds_played + 1,
            stage=GameStage.ROUND_ENDED,
        )

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.ROUND_ENDED,
            {
                "game_id": state.id,
                "round_number": new_state.rounds_played,
                "winner_id": winner.id,
                "winner_name": winner.name,
                "timestamp": new_state.timestamp,
            },
        )

        return new_state, RoundResult.WIN

    @staticmethod
    def resolve_war(state: GameState) -> GameState:
        """
        Resolve a war (tied cards) by determining the winner.

        Args:
            state: Current game state

        Returns:
            New game state with the war resolved
        """
        if not state.war_state.is_active:
            return state

        # In a real War game, players would draw additional cards,
        # but for this simple implementation, we'll just pick the first player
        # involved in the war as the winner
        if not state.war_state.cards_in_war:
            return state

        winner_id, _ = state.war_state.cards_in_war[0]

        # Update stats for all players
        new_players = []
        for player in state.players:
            if player.id == winner_id:
                # Update winner stats
                new_current_streak = player.current_streak + 1
                new_max_streak = max(player.max_streak, new_current_streak)
                new_player = replace(
                    player,
                    wins=player.wins + 1,
                    current_streak=new_current_streak,
                    max_streak=new_max_streak,
                )
            else:
                # Reset streak for losers
                new_player = replace(player, current_streak=0)

            new_players.append(new_player)

        # Reset war state
        war_state = WarState()

        # Create and return a new game state
        new_state = replace(
            state,
            players=new_players,
            winner_id=winner_id,
            war_state=war_state,
            rounds_played=state.rounds_played + 1,
            stage=GameStage.ROUND_ENDED,
        )

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.ROUND_ENDED,
            {
                "game_id": state.id,
                "round_number": new_state.rounds_played,
                "winner_id": winner_id,
                "winner_name": next(
                    (p.name for p in new_players if p.id == winner_id), "Unknown"
                ),
                "is_war_resolution": True,
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def change_stage(state: GameState, new_stage: GameStage) -> GameState:
        """
        Change the game stage.

        Args:
            state: Current game state
            new_stage: New game stage

        Returns:
            New game state with updated stage
        """
        # Create and return a new game state with the updated stage
        new_state = replace(state, stage=new_stage)

        # Emit stage change event
        event_bus = EventBus.get_instance()
        if new_stage == GameStage.DEALING:
            event_bus.emit(
                EngineEventType.ROUND_STARTED,
                {
                    "game_id": state.id,
                    "round_number": state.rounds_played + 1,
                    "timestamp": new_state.timestamp,
                },
            )

        return new_state

    @staticmethod
    def reset_for_new_round(state: GameState) -> GameState:
        """
        Reset the state for a new round.

        Args:
            state: Current game state

        Returns:
            New game state ready for a new round
        """
        # Reset cards for all players
        new_players = []
        for player in state.players:
            new_player = replace(player, card=None)
            new_players.append(new_player)

        # Create and return a new game state
        new_state = replace(
            state,
            players=new_players,
            winner_id=None,
            war_state=WarState(),
            stage=GameStage.DEALING,
        )

        return new_state
