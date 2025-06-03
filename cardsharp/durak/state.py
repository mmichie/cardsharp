"""
Immutable state models for the Durak card game.

This module provides dataclasses for representing the state of a Durak card game
in an immutable manner. These classes are designed to be used with pure
transition functions that create new state instances rather than modifying
existing ones.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum, auto
import uuid
import time

from cardsharp.common.card import Card, Suit
from cardsharp.durak.constants import get_durak_value


class GameStage(Enum):
    """Possible stages of a Durak card game."""

    WAITING_FOR_PLAYERS = auto()
    DEALING = auto()
    ATTACK = auto()
    DEFENSE = auto()
    PASSING = auto()  # For "Perevodnoy" variant
    THROWING_IN = auto()  # For "Podkidnoy" variant
    ROUND_END = auto()
    GAME_END = auto()


@dataclass(frozen=True)
class TableState:
    """
    Immutable representation of the cards on the table in Durak.

    Attributes:
        attack_cards: List of cards played by attackers
        defense_cards: List of cards played by defender to counter attacks
    """

    attack_cards: List[Card] = field(default_factory=list)
    defense_cards: List[Card] = field(default_factory=list)

    def is_attack_position_open(self, position: int) -> bool:
        """Check if a position is open for attack."""
        return position < len(self.attack_cards) and position >= len(self.defense_cards)

    def get_undefended_card(self) -> Optional[Card]:
        """Get the first undefended attack card if any."""
        if len(self.attack_cards) > len(self.defense_cards):
            return self.attack_cards[len(self.defense_cards)]
        return None

    @property
    def attack_defense_pairs(self) -> List[Tuple[Card, Optional[Card]]]:
        """Return a list of attack and defense card pairs."""
        pairs = []
        for i in range(len(self.attack_cards)):
            defense = self.defense_cards[i] if i < len(self.defense_cards) else None
            pairs.append((self.attack_cards[i], defense))
        return pairs


@dataclass(frozen=True)
class PlayerState:
    """
    Immutable representation of a player's state in Durak.

    Attributes:
        id: Unique identifier for this player
        name: Display name of the player
        hand: Cards in the player's hand
        is_attacker: Whether this player is currently attacking
        is_defender: Whether this player is currently defending
        is_out: Whether this player is out of the game (has no cards left)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Player"
    hand: List[Card] = field(default_factory=list)
    is_attacker: bool = False
    is_defender: bool = False
    is_out: bool = False
    pass_count: int = 0  # Track how many times a player has passed

    @property
    def card_count(self) -> int:
        """Get the number of cards in the player's hand."""
        return len(self.hand)

    def has_card(self, card_rank: int) -> bool:
        """Check if player has a card of specific rank."""
        return any(get_durak_value(card.rank) == card_rank for card in self.hand)


@dataclass(frozen=True)
class DurakRules:
    """
    Immutable representation of the rules for a Durak game.

    Attributes:
        deck_size: Size of the deck (20, 36, or 52)
        allow_passing: Whether to allow the defender to pass the attack
        allow_throwing_in: Whether to allow other players to throw in cards
        max_attack_cards: Maximum number of cards for attack (-1 for unlimited)
        attack_limit_by_hand_size: Whether attack is limited by defender's hand size
    """

    deck_size: int = 36  # 20, 36, or 52
    allow_passing: bool = False  # "Perevodnoy" variant
    allow_throwing_in: bool = True  # "Podkidnoy" variant
    max_attack_cards: int = -1  # -1 means unlimited
    attack_limit_by_hand_size: bool = True
    trump_selection_method: str = "bottom_card"  # or "random"
    lowest_card_starts: bool = True  # Lowest trump or lowest card starts
    refill_hands_threshold: int = 6  # Refill hands when below this number


@dataclass(frozen=True)
class GameState:
    """
    Immutable representation of the Durak card game state.

    Attributes:
        id: Unique identifier for this game
        players: List of players in the game
        stage: Current stage of the game
        trump_suit: The trump suit for this game
        attacker_index: Index of the current attacker
        defender_index: Index of the current defender
        table: Current state of the cards on the table
        deck: Cards remaining in the deck
        discard_pile: Cards that have been discarded
        rules: Rules for this game
        timestamp: Time when this state was created
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    players: List[PlayerState] = field(default_factory=list)
    stage: GameStage = GameStage.WAITING_FOR_PLAYERS
    trump_suit: Optional[Suit] = None
    trump_card: Optional[Card] = None
    attacker_index: Optional[int] = None
    defender_index: Optional[int] = None
    active_player_index: Optional[int] = None  # Index of player who should take action
    table: TableState = field(default_factory=TableState)
    deck: List[Card] = field(default_factory=list)
    discard_pile: List[Card] = field(default_factory=list)
    rules: DurakRules = field(default_factory=DurakRules)
    current_round: int = 0
    loser_id: Optional[str] = None  # ID of the player who lost the game
    timestamp: float = field(default_factory=lambda: time.time())

    @property
    def deck_size(self) -> int:
        """Get the number of cards left in the deck."""
        return len(self.deck)

    @property
    def active_player(self) -> Optional[PlayerState]:
        """Get the player who should take action now."""
        if (
            self.active_player_index is not None
            and 0 <= self.active_player_index < len(self.players)
        ):
            return self.players[self.active_player_index]
        return None

    @property
    def current_attacker(self) -> Optional[PlayerState]:
        """Get the current attacker if any."""
        if self.attacker_index is not None and 0 <= self.attacker_index < len(
            self.players
        ):
            return self.players[self.attacker_index]
        return None

    @property
    def current_defender(self) -> Optional[PlayerState]:
        """Get the current defender if any."""
        if self.defender_index is not None and 0 <= self.defender_index < len(
            self.players
        ):
            return self.players[self.defender_index]
        return None

    @property
    def players_in_game(self) -> List[PlayerState]:
        """Get the list of players still in the game."""
        return [p for p in self.players if not p.is_out]

    @property
    def game_ended(self) -> bool:
        """Check if the game has ended (only one player left with cards)."""
        return len(self.players_in_game) <= 1 or self.stage == GameStage.GAME_END

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the game state to a dictionary suitable for serialization.

        Returns:
            Dictionary representation of the game state
        """
        return {
            "id": self.id,
            "stage": self.stage.name,
            "trump_suit": self.trump_suit.name if self.trump_suit else None,
            "trump_card": str(self.trump_card) if self.trump_card else None,
            "attacker_index": self.attacker_index,
            "defender_index": self.defender_index,
            "active_player_index": self.active_player_index,
            "deck_remaining": len(self.deck),
            "discard_pile_size": len(self.discard_pile),
            "current_round": self.current_round,
            "loser_id": self.loser_id,
            "timestamp": self.timestamp,
            "table": {
                "attack_cards": [str(card) for card in self.table.attack_cards],
                "defense_cards": [str(card) for card in self.table.defense_cards],
            },
            "players": [
                {
                    "id": player.id,
                    "name": player.name,
                    "hand_size": len(player.hand),
                    "is_attacker": player.is_attacker,
                    "is_defender": player.is_defender,
                    "is_out": player.is_out,
                    "pass_count": player.pass_count,
                }
                for player in self.players
            ],
            "rules": {
                "deck_size": self.rules.deck_size,
                "allow_passing": self.rules.allow_passing,
                "allow_throwing_in": self.rules.allow_throwing_in,
                "max_attack_cards": self.rules.max_attack_cards,
                "attack_limit_by_hand_size": self.rules.attack_limit_by_hand_size,
                "trump_selection_method": self.rules.trump_selection_method,
                "lowest_card_starts": self.rules.lowest_card_starts,
                "refill_hands_threshold": self.rules.refill_hands_threshold,
            },
        }

    def to_adapter_format(self) -> Dict[str, Any]:
        """
        Convert the game state to a format suitable for platform adapters.

        Returns:
            Dictionary in adapter-friendly format
        """
        return {
            "game_id": self.id,
            "stage": self.stage.name,
            "trump_suit": str(self.trump_suit) if self.trump_suit else None,
            "trump_card": str(self.trump_card) if self.trump_card else None,
            "deck_remaining": len(self.deck),
            "current_round": self.current_round,
            "active_player": self.active_player.name if self.active_player else None,
            "attacker": self.current_attacker.name if self.current_attacker else None,
            "defender": self.current_defender.name if self.current_defender else None,
            "table": {
                "attack_cards": [str(card) for card in self.table.attack_cards],
                "defense_cards": [str(card) for card in self.table.defense_cards],
            },
            "players": [
                {
                    "name": player.name,
                    "id": player.id,
                    "hand_size": len(player.hand),
                    "is_attacker": player.is_attacker,
                    "is_defender": player.is_defender,
                    "is_out": player.is_out,
                    "cards": [str(card) for card in player.hand],
                }
                for player in self.players
            ],
        }
