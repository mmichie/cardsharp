"""
Immutable state models for the War card game.

This module provides dataclasses for representing the state of a War card game
in an immutable manner. These classes are designed to be used with pure
transition functions that create new state instances rather than modifying
existing ones.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple
from enum import Enum, auto
import uuid
import time
import copy

from cardsharp.common.card import Card


class GameStage(Enum):
    """Possible stages of a War card game."""

    WAITING_FOR_PLAYERS = auto()
    DEALING = auto()
    COMPARING_CARDS = auto()
    WAR = auto()  # Special stage for "war" (tied cards)
    ROUND_ENDED = auto()


class RoundResult(Enum):
    """Possible results of a War card game round."""

    WIN = auto()
    WAR = auto()


@dataclass(frozen=True)
class WarState:
    """
    Immutable representation of a "war" state in the War card game.

    Attributes:
        cards_in_war: List of cards involved in the war
        is_active: Whether the war is currently active
    """

    cards_in_war: List[Tuple[str, Card]] = field(default_factory=list)
    is_active: bool = False


@dataclass(frozen=True)
class PlayerState:
    """
    Immutable representation of a player's state in War.

    Attributes:
        id: Unique identifier for this player
        name: Display name of the player
        card: Current card drawn by the player
        wins: Total number of wins
        current_streak: Current win streak
        max_streak: Maximum win streak achieved
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Player"
    card: Optional[Card] = None
    wins: int = 0
    current_streak: int = 0
    max_streak: int = 0


@dataclass(frozen=True)
class GameState:
    """
    Immutable representation of the War card game state.

    Attributes:
        id: Unique identifier for this game
        players: List of players in the game
        stage: Current stage of the game
        rounds_played: Number of rounds played
        winner_id: ID of the current round winner (if any)
        war_state: State of the current war (if any)
        timestamp: Time when this state was created
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    players: List[PlayerState] = field(default_factory=list)
    stage: GameStage = GameStage.WAITING_FOR_PLAYERS
    rounds_played: int = 0
    winner_id: Optional[str] = None
    war_state: WarState = field(default_factory=WarState)
    deck_cards_remaining: int = 52
    timestamp: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the game state to a dictionary suitable for serialization.

        Returns:
            Dictionary representation of the game state
        """
        return {
            "id": self.id,
            "stage": self.stage.name,
            "rounds_played": self.rounds_played,
            "winner_id": self.winner_id,
            "deck_cards_remaining": self.deck_cards_remaining,
            "war_state": {
                "is_active": self.war_state.is_active,
                "cards_in_war": [
                    {"player_id": player_id, "card": str(card)}
                    for player_id, card in self.war_state.cards_in_war
                ],
            },
            "timestamp": self.timestamp,
            "players": [
                {
                    "id": player.id,
                    "name": player.name,
                    "card": str(player.card) if player.card else None,
                    "wins": player.wins,
                    "current_streak": player.current_streak,
                    "max_streak": player.max_streak,
                }
                for player in self.players
            ],
        }

    def to_adapter_format(self) -> Dict[str, Any]:
        """
        Convert the game state to a format suitable for platform adapters.

        Returns:
            Dictionary in adapter-friendly format
        """
        return {
            "rounds_played": self.rounds_played,
            "winner": next(
                (p.name for p in self.players if p.id == self.winner_id), None
            ),
            "war_active": self.war_state.is_active,
            "war_cards": [
                {
                    "player": next(
                        (p.name for p in self.players if p.id == pid), "Unknown"
                    ),
                    "card": str(card),
                }
                for pid, card in self.war_state.cards_in_war
            ],
            "players": [
                {
                    "name": player.name,
                    "card": str(player.card) if player.card else None,
                    "wins": player.wins,
                }
                for player in self.players
            ],
        }
