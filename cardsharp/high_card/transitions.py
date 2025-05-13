"""
State transition functions for the High Card game.

This module provides pure functions for transitioning between game states,
without modifying the original state objects.
"""

from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import replace

from cardsharp.common.card import Card
from cardsharp.events import EventBus, EngineEventType
from cardsharp.high_card.state import GameState, PlayerState, GameStage


class StateTransitionEngine:
    """
    Pure functions for state transitions in High Card.

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
    def determine_winner(state: GameState) -> GameState:
        """
        Determine the winner of the current round.

        Args:
            state: Current game state

        Returns:
            New game state with the winner determined
        """
        # Find the player with the highest card
        winner = None
        highest_card = None

        for player in state.players:
            if player.card and (
                not highest_card
                or player.card.rank.rank_value > highest_card.rank.rank_value
            ):
                highest_card = player.card
                winner = player

        if not winner:
            # No winner, return the original state
            return state

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
            stage=GameStage.DEALING,
            deck_cards_remaining=52,  # Reset deck
        )

        return new_state
