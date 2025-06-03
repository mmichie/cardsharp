"""
Immutable state models for the Cardsharp engine.

This module provides dataclasses for representing the state of a card game
in an immutable manner. These classes are designed to be used with pure
transition functions that create new state instances rather than modifying
existing ones.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum, auto
import uuid


class GameStage(Enum):
    """
    Possible stages of a blackjack game.
    """

    WAITING_FOR_PLAYERS = auto()
    PLACING_BETS = auto()
    DEALING = auto()
    INSURANCE = auto()
    PLAYER_TURN = auto()
    DEALER_TURN = auto()
    END_ROUND = auto()


@dataclass(frozen=True)
class HandState:
    """
    Immutable representation of a card hand.

    Attributes:
        id: Unique identifier for this hand
        cards: List of cards in the hand
        bet: Current bet amount on this hand
        is_doubled: Whether the bet has been doubled
        is_split: Whether this hand was created via a split
        original_hand_id: ID of the hand this was split from (if any)
        insurance_bet: Size of insurance bet (if any)
        is_surrendered: Whether the hand has been surrendered
        is_resolved: Whether the hand has been resolved (win/loss determined)
        result: The result of the hand (win, lose, push, etc.)
        payout: The payout amount for this hand
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cards: List[Any] = field(default_factory=list)
    bet: float = 0.0
    is_doubled: bool = False
    is_split: bool = False
    original_hand_id: Optional[str] = None
    insurance_bet: float = 0.0
    is_surrendered: bool = False
    is_resolved: bool = False
    result: Optional[str] = None
    payout: float = 0.0

    @property
    def is_blackjack(self) -> bool:
        """Check if the hand is a blackjack."""
        # This is a simplified implementation - in reality, you'd check the cards
        return len(self.cards) == 2 and self.value == 21 and not self.is_split

    @property
    def is_bust(self) -> bool:
        """Check if the hand is bust."""
        return self.value > 21

    @property
    def is_soft(self) -> bool:
        """Check if the hand has a soft value (uses Ace as 11)."""
        # This is a simplified implementation - in reality, you'd check the cards
        for card in self.cards:
            # Handle card objects with rank attribute
            if hasattr(card, "rank"):
                if (
                    hasattr(card.rank, "name")
                    and card.rank.name == "ACE"
                    and self.value <= 21
                ):
                    return True
                elif (
                    isinstance(card.rank, str) and card.rank == "A" and self.value <= 21
                ):
                    return True
            # Handle string cards
            elif isinstance(card, str) and card[0] == "A" and self.value <= 21:
                return True
        return False

    @property
    def value(self) -> int:
        """Calculate the value of the hand."""
        # This is a simplified implementation - the actual implementation would
        # depend on the card representation and game rules
        total = 0
        aces = 0

        for card in self.cards:
            # Handle cards that are direct string representations (most common in our engine)
            if isinstance(card, str):
                # Try to parse string representation of cards (e.g., "A♠", "10♥")
                if card[0] in ("J", "Q", "K"):
                    total += 10
                elif card[0] == "A":
                    aces += 1
                    total += 1  # Count aces as 1 initially
                else:
                    # Try to parse the card value
                    try:
                        # Strip suits and other characters
                        value_str = "".join(c for c in card if c.isdigit())
                        if value_str:
                            value = int(value_str)
                            total += value
                        else:
                            # If we can't extract a number, assume it's a 10
                            total += 10
                    except ValueError:
                        # If all else fails, assume it's a 10
                        total += 10

            # Handle card objects with value attribute
            elif hasattr(card, "value"):
                total += card.value

            # Handle card objects with rank attribute
            elif hasattr(card, "rank"):
                # Check if rank is an object with a name attribute
                if hasattr(card.rank, "name"):
                    rank = card.rank.name
                    if rank in ("JACK", "QUEEN", "KING"):
                        total += 10
                    elif rank == "ACE":
                        aces += 1
                        total += 1  # Count aces as 1 initially
                    else:
                        # Assuming numeric ranks like 2-10
                        try:
                            total += int(rank)
                        except ValueError:
                            # If not a number, use the rank_value attribute if available
                            if hasattr(card.rank, "rank_value"):
                                total += card.rank.rank_value
                            else:
                                # Fallback to string representation
                                try:
                                    value = int(str(card.rank))
                                    total += value
                                except ValueError:
                                    # If all else fails, assume it's a 10
                                    total += 10
                # If rank is a string
                elif isinstance(card.rank, str):
                    if card.rank in ("J", "Q", "K"):
                        total += 10
                    elif card.rank == "A":
                        aces += 1
                        total += 1
                    else:
                        try:
                            total += int(card.rank)
                        except ValueError:
                            total += 10

            # Handle integer cards
            elif isinstance(card, int):
                total += card

        # Convert aces from 1 to 11 where it won't bust
        for _ in range(aces):
            if total + 10 <= 21:
                total += 10

        return total


@dataclass(frozen=True)
class PlayerState:
    """
    Immutable representation of a player's state.

    Attributes:
        id: Unique identifier for this player
        name: Display name of the player
        balance: Current money balance
        hands: List of hands the player currently holds
        current_hand_index: Index of the current active hand
        is_done: Whether the player has completed their turn
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Player"
    balance: float = 1000.0
    hands: List[HandState] = field(default_factory=list)
    current_hand_index: int = 0
    is_done: bool = False

    @property
    def current_hand(self) -> Optional[HandState]:
        """Get the player's current hand."""
        if not self.hands or self.current_hand_index >= len(self.hands):
            return None
        return self.hands[self.current_hand_index]


@dataclass(frozen=True)
class DealerState:
    """
    Immutable representation of the dealer's state.

    Attributes:
        hand: The dealer's current hand
        is_done: Whether the dealer has completed their turn
        visible_card_count: Number of cards that are visible to players
    """

    hand: HandState = field(default_factory=HandState)
    is_done: bool = False
    visible_card_count: int = 0  # How many cards are visible to players

    @property
    def visible_cards(self) -> List[Any]:
        """Get the dealer's visible cards."""
        if not self.hand.cards:
            return []
        return self.hand.cards[: self.visible_card_count]

    @property
    def visible_value(self) -> int:
        """Calculate the value of the visible cards."""
        # Create a temporary hand with just the visible cards

        visible_hand = HandState(cards=self.visible_cards)
        return visible_hand.value


@dataclass(frozen=True)
class GameState:
    """
    Immutable representation of the game state.

    Attributes:
        id: Unique identifier for this game
        players: List of all players in the game
        dealer: The dealer's state
        current_player_index: Index of the current active player
        stage: Current stage of the game (betting, dealing, etc.)
        shoe_cards_remaining: Number of cards remaining in the shoe
        rules: Rules configuration for the game
        round_number: Current round number
        timestamp: Time when this state was created
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    players: List[PlayerState] = field(default_factory=list)
    dealer: DealerState = field(default_factory=DealerState)
    current_player_index: int = 0
    stage: GameStage = GameStage.WAITING_FOR_PLAYERS
    shoe_cards_remaining: int = 312  # Default 6 decks
    rules: Dict[str, Any] = field(default_factory=dict)
    round_number: int = 0
    timestamp: float = field(default_factory=lambda: __import__("time").time())

    @property
    def current_player(self) -> Optional[PlayerState]:
        """Get the current active player."""
        if not self.players or self.current_player_index >= len(self.players):
            return None
        return self.players[self.current_player_index]

    @property
    def current_player_hand(self) -> Optional[HandState]:
        """Get the current player's active hand."""
        player = self.current_player
        if not player:
            return None
        return player.current_hand

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the game state to a dictionary suitable for serialization.

        Returns:
            Dictionary representation of the game state
        """
        # Create a basic dictionary with simple properties
        result = {
            "id": self.id,
            "stage": self.stage.name,
            "round_number": self.round_number,
            "current_player_index": self.current_player_index,
            "shoe_cards_remaining": self.shoe_cards_remaining,
            "timestamp": self.timestamp,
        }

        # Add rules
        result["rules"] = self.rules.copy() if self.rules else {}

        # Add dealer info
        result["dealer"] = {
            "hand": [str(card) for card in self.dealer.hand.cards],
            "value": self.dealer.hand.value,
            "visible_cards": [str(card) for card in self.dealer.visible_cards],
            "visible_value": self.dealer.visible_value,
            "is_done": self.dealer.is_done,
        }

        # Add players info
        result["players"] = []
        for player in self.players:
            player_dict = {
                "id": player.id,
                "name": player.name,
                "balance": player.balance,
                "is_done": player.is_done,
                "current_hand_index": player.current_hand_index,
                "hands": [],
            }

            for hand in player.hands:
                hand_dict = {
                    "id": hand.id,
                    "cards": [str(card) for card in hand.cards],
                    "value": hand.value,
                    "is_soft": hand.is_soft,
                    "is_blackjack": hand.is_blackjack,
                    "is_bust": hand.is_bust,
                    "bet": hand.bet,
                    "is_doubled": hand.is_doubled,
                    "is_split": hand.is_split,
                    "is_surrendered": hand.is_surrendered,
                    "is_resolved": hand.is_resolved,
                    "result": hand.result,
                    "payout": hand.payout,
                }
                player_dict["hands"].append(hand_dict)

            result["players"].append(player_dict)

        return result

    def to_adapter_format(self) -> Dict[str, Any]:
        """
        Convert the game state to a format suitable for platform adapters.

        Returns:
            Dictionary in adapter-friendly format
        """
        state_dict = {
            "dealer": {
                "hand": [str(card) for card in self.dealer.hand.cards],
                "value": self.dealer.hand.value,
                "hide_second_card": len(self.dealer.hand.cards)
                > self.dealer.visible_card_count,
            },
            "players": [],
        }

        for player in self.players:
            player_dict = {"name": player.name, "balance": player.balance, "hands": []}

            for hand in player.hands:
                hand_dict = {
                    "cards": [str(card) for card in hand.cards],
                    "value": hand.value,
                    "bet": hand.bet,
                }
                player_dict["hands"].append(hand_dict)

            state_dict["players"].append(player_dict)

        return state_dict
