"""
State transition functions for the Durak card game.

This module provides pure functions for transitioning between game states,
without modifying the original state objects.
"""

from typing import Optional
from dataclasses import replace
import random

from cardsharp.common.card import Suit, Rank
from cardsharp.common.deck import Deck
from cardsharp.events import EventBus, EngineEventType
from cardsharp.durak.state import (
    GameState,
    PlayerState,
    TableState,
    GameStage,
    DurakRules,
)
from cardsharp.durak.constants import get_durak_value


class StateTransitionEngine:
    """
    Pure functions for state transitions in Durak.

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
    def initialize_game(
        state: GameState, rules: Optional[DurakRules] = None
    ) -> GameState:
        """
        Initialize a new game with the given rules.

        Args:
            state: Current game state
            rules: Rules for the new game (or use state's rules if None)

        Returns:
            New game state initialized for play
        """
        # Use provided rules or current rules
        game_rules = rules or state.rules

        # Create a deck based on rule specifications
        deck = Deck()

        # For 36-card Durak, remove cards below 6
        if game_rules.deck_size == 36:
            deck.cards = [
                card
                for card in deck.cards
                if card.rank not in [Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE]
            ]
        # For 20-card Durak, keep only 10, J, Q, K, A
        elif game_rules.deck_size == 20:
            deck.cards = [
                card
                for card in deck.cards
                if card.rank in [Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING, Rank.ACE]
            ]

        # Shuffle the deck
        deck.shuffle()

        # Determine trump suit based on rules
        trump_card = None
        trump_suit = None

        if game_rules.trump_selection_method == "bottom_card":
            # Bottom card of the deck is the trump
            trump_card = deck.cards[-1]
            trump_suit = trump_card.suit
        elif game_rules.trump_selection_method == "random":
            # Randomly select a suit
            trump_suit = random.choice(list(Suit))

        # Create and return a new game state
        new_state = replace(
            state,
            deck=deck.cards,
            trump_suit=trump_suit,
            trump_card=trump_card,
            rules=game_rules,
            stage=GameStage.WAITING_FOR_PLAYERS,
            current_round=0,
            loser_id=None,
            table=TableState(),
            discard_pile=[],
        )

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.GAME_CREATED,
            {
                "game_id": new_state.id,
                "timestamp": new_state.timestamp,
                "rules": {
                    "deck_size": game_rules.deck_size,
                    "allow_passing": game_rules.allow_passing,
                    "allow_throwing_in": game_rules.allow_throwing_in,
                    "trump_selection_method": game_rules.trump_selection_method,
                },
                "trump_suit": str(trump_suit) if trump_suit else None,
            },
        )

        return new_state

    @staticmethod
    def deal_initial_cards(state: GameState) -> GameState:
        """
        Deal initial cards to all players.

        Args:
            state: Current game state

        Returns:
            New game state with cards dealt
        """
        if state.stage != GameStage.WAITING_FOR_PLAYERS or len(state.players) < 2:
            return state  # Can't deal cards yet

        # Create a new deck list we can modify
        new_deck = list(state.deck)

        # Deal cards to each player
        new_players = []
        for player in state.players:
            # Deal 6 cards to each player
            player_hand = []
            for _ in range(min(6, len(new_deck))):
                player_hand.append(new_deck.pop(0))

            # Create a new player with these cards
            new_player = replace(player, hand=player_hand)
            new_players.append(new_player)

        # Determine the first attacker based on rules
        first_attacker_idx = 0
        if state.rules.lowest_card_starts:
            lowest_card_value = float("inf")
            lowest_trump_value = float("inf")

            # Find the player with the lowest trump or lowest card
            for i, player in enumerate(new_players):
                for card in player.hand:
                    # Check for trump card
                    if card.suit == state.trump_suit:
                        if get_durak_value(card.rank) < lowest_trump_value:
                            lowest_trump_value = get_durak_value(card.rank)
                            first_attacker_idx = i
                    elif (
                        lowest_trump_value == float("inf")
                        and get_durak_value(card.rank) < lowest_card_value
                    ):
                        lowest_card_value = get_durak_value(card.rank)
                        first_attacker_idx = i

        # Determine the defender (next player after attacker)
        defender_idx = (first_attacker_idx + 1) % len(new_players)

        # Mark attacker and defender
        for i in range(len(new_players)):
            is_attacker = i == first_attacker_idx
            is_defender = i == defender_idx
            new_players[i] = replace(
                new_players[i], is_attacker=is_attacker, is_defender=is_defender
            )

        # Create and return a new game state
        new_state = replace(
            state,
            players=new_players,
            deck=new_deck,
            attacker_index=first_attacker_idx,
            defender_index=defender_idx,
            active_player_index=first_attacker_idx,  # Attacker moves first
            stage=GameStage.ATTACK,
        )

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.ROUND_STARTED,
            {
                "game_id": new_state.id,
                "round_number": new_state.current_round + 1,
                "attacker": new_players[first_attacker_idx].name,
                "defender": new_players[defender_idx].name,
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def play_attack_card(
        state: GameState, player_id: str, card_index: int
    ) -> GameState:
        """
        Play an attack card.

        Args:
            state: Current game state
            player_id: ID of the player making the attack
            card_index: Index of the card in the player's hand to play

        Returns:
            New game state with the attack card played
        """
        if state.stage != GameStage.ATTACK:
            return state  # Not in attack stage

        # Find the player
        player_idx = None
        for i, player in enumerate(state.players):
            if player.id == player_id:
                player_idx = i
                break

        if player_idx is None or not state.players[player_idx].is_attacker:
            return state  # Not a valid attacker

        player = state.players[player_idx]

        # Check if the card index is valid
        if card_index < 0 or card_index >= len(player.hand):
            return state  # Invalid card index

        card = player.hand[card_index]

        # Validate that this is a valid attack card
        if state.table.attack_cards:
            # Can only play cards of ranks already on the table
            valid_ranks = set(
                get_durak_value(c.rank)
                for c in state.table.attack_cards + state.table.defense_cards
            )
            if get_durak_value(card.rank) not in valid_ranks:
                return state  # Invalid card rank

        # Check attack limits
        if (
            state.rules.max_attack_cards > 0
            and len(state.table.attack_cards) >= state.rules.max_attack_cards
        ):
            return state  # Reached attack limit

        if state.rules.attack_limit_by_hand_size:
            defender = state.players[state.defender_index]
            if len(state.table.attack_cards) - len(state.table.defense_cards) >= len(
                defender.hand
            ):
                return state  # Can't attack with more cards than defender has

        # Create a new player with the card removed from hand
        new_hand = list(player.hand)
        new_hand.pop(card_index)
        new_player = replace(player, hand=new_hand)

        # Create a new list of players with the updated player
        new_players = list(state.players)
        new_players[player_idx] = new_player

        # Add the card to the table
        new_attack_cards = list(state.table.attack_cards)
        new_attack_cards.append(card)
        new_table = replace(state.table, attack_cards=new_attack_cards)

        # Move to defense stage
        new_state = replace(
            state,
            players=new_players,
            table=new_table,
            stage=GameStage.DEFENSE,
            active_player_index=state.defender_index,  # Defender's turn now
        )

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.CUSTOM_EVENT,
            {
                "event_name": "ATTACK_CARD_PLAYED",
                "game_id": state.id,
                "player_id": player_id,
                "player_name": player.name,
                "card": str(card),
                "remaining_hand_size": len(new_hand),
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def play_defense_card(
        state: GameState, player_id: str, card_index: int
    ) -> GameState:
        """
        Play a defense card.

        Args:
            state: Current game state
            player_id: ID of the player defending
            card_index: Index of the card in the player's hand to play

        Returns:
            New game state with the defense card played
        """
        if state.stage != GameStage.DEFENSE:
            return state  # Not in defense stage

        # Find the player
        player_idx = None
        for i, player in enumerate(state.players):
            if player.id == player_id:
                player_idx = i
                break

        if player_idx is None or not state.players[player_idx].is_defender:
            return state  # Not a valid defender

        player = state.players[player_idx]

        # Check if the card index is valid
        if card_index < 0 or card_index >= len(player.hand):
            return state  # Invalid card index

        card = player.hand[card_index]

        # Get the undefended attack card
        undefended_card = state.table.get_undefended_card()
        if not undefended_card:
            return state  # No card to defend against

        # Validate that this is a valid defense card
        is_valid_defense = False

        # Same suit, higher rank
        if card.suit == undefended_card.suit and get_durak_value(
            card.rank
        ) > get_durak_value(undefended_card.rank):
            is_valid_defense = True
        # Trump card vs non-trump
        elif card.suit == state.trump_suit and undefended_card.suit != state.trump_suit:
            is_valid_defense = True

        if not is_valid_defense:
            return state  # Invalid defense

        # Create a new player with the card removed from hand
        new_hand = list(player.hand)
        new_hand.pop(card_index)
        new_player = replace(player, hand=new_hand)

        # Create a new list of players with the updated player
        new_players = list(state.players)
        new_players[player_idx] = new_player

        # Add the card to the table
        new_defense_cards = list(state.table.defense_cards)
        new_defense_cards.append(card)
        new_table = replace(state.table, defense_cards=new_defense_cards)

        # If all attacks are defended, move to throwing in or round end
        new_stage = state.stage
        new_active_index = state.active_player_index

        if len(new_defense_cards) == len(state.table.attack_cards):
            if state.rules.allow_throwing_in:
                new_stage = GameStage.THROWING_IN
                new_active_index = state.attacker_index  # Attacker can throw in
            else:
                new_state = StateTransitionEngine.end_round(
                    replace(state, players=new_players, table=new_table),
                    defender_won=True,
                )
                return new_state

        # Create and return the new state
        new_state = replace(
            state,
            players=new_players,
            table=new_table,
            stage=new_stage,
            active_player_index=new_active_index,
        )

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.CUSTOM_EVENT,
            {
                "event_name": "DEFENSE_CARD_PLAYED",
                "game_id": state.id,
                "player_id": player_id,
                "player_name": player.name,
                "card": str(card),
                "against_card": str(undefended_card),
                "remaining_hand_size": len(new_hand),
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def throw_in_card(state: GameState, player_id: str, card_index: int) -> GameState:
        """
        Throw in a card (additional attack card).

        Args:
            state: Current game state
            player_id: ID of the player throwing in
            card_index: Index of the card in the player's hand to throw in

        Returns:
            New game state with the card thrown in
        """
        if state.stage != GameStage.THROWING_IN:
            return state  # Not in throwing in stage

        # Find the player
        player_idx = None
        for i, player in enumerate(state.players):
            if player.id == player_id:
                player_idx = i
                break

        if player_idx is None:
            return state  # Player not found

        player = state.players[player_idx]

        # Check if the card index is valid
        if card_index < 0 or card_index >= len(player.hand):
            return state  # Invalid card index

        card = player.hand[card_index]

        # Validate that this is a valid throw-in card (must match existing ranks)
        valid_ranks = set(
            get_durak_value(c.rank)
            for c in state.table.attack_cards + state.table.defense_cards
        )
        if get_durak_value(card.rank) not in valid_ranks:
            return state  # Invalid card rank

        # Check attack limits
        if (
            state.rules.max_attack_cards > 0
            and len(state.table.attack_cards) >= state.rules.max_attack_cards
        ):
            return state  # Reached attack limit

        if state.rules.attack_limit_by_hand_size:
            defender = state.players[state.defender_index]
            if len(state.table.attack_cards) - len(state.table.defense_cards) >= len(
                defender.hand
            ):
                return state  # Can't attack with more cards than defender has

        # Create a new player with the card removed from hand
        new_hand = list(player.hand)
        new_hand.pop(card_index)
        new_player = replace(player, hand=new_hand)

        # Create a new list of players with the updated player
        new_players = list(state.players)
        new_players[player_idx] = new_player

        # Add the card to the table
        new_attack_cards = list(state.table.attack_cards)
        new_attack_cards.append(card)
        new_table = replace(state.table, attack_cards=new_attack_cards)

        # Move to defense stage for the new card
        new_state = replace(
            state,
            players=new_players,
            table=new_table,
            stage=GameStage.DEFENSE,
            active_player_index=state.defender_index,  # Defender's turn now
        )

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.CUSTOM_EVENT,
            {
                "event_name": "CARD_THROWN_IN",
                "game_id": state.id,
                "player_id": player_id,
                "player_name": player.name,
                "card": str(card),
                "remaining_hand_size": len(new_hand),
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def pass_attack(state: GameState, player_id: str) -> GameState:
        """
        Pass on attacking or throwing in.

        Args:
            state: Current game state
            player_id: ID of the player passing

        Returns:
            New game state after passing
        """
        if state.stage not in [GameStage.ATTACK, GameStage.THROWING_IN]:
            return state  # Not in a stage where passing is applicable

        # Find the player
        player_idx = None
        for i, player in enumerate(state.players):
            if player.id == player_id:
                player_idx = i
                break

        if player_idx is None:
            return state  # Player not found

        # If in ATTACK stage, and it's the main attacker passing with no cards played,
        # move to the next attacker
        if state.stage == GameStage.ATTACK and len(state.table.attack_cards) == 0:
            # Find the next eligible player to be attacker
            # Skip the current defender
            player_count = len(state.players)
            next_attacker_idx = (state.attacker_index + 1) % player_count
            while (
                next_attacker_idx == state.defender_index
                or state.players[next_attacker_idx].is_out
            ):
                next_attacker_idx = (next_attacker_idx + 1) % player_count

            # Update player roles
            new_players = []
            new_defender_idx = (next_attacker_idx + 1) % player_count
            while state.players[new_defender_idx].is_out:
                new_defender_idx = (new_defender_idx + 1) % player_count

            for i, player in enumerate(state.players):
                is_attacker = i == next_attacker_idx
                is_defender = i == new_defender_idx
                pass_count = player.pass_count + (1 if i == player_idx else 0)
                new_players.append(
                    replace(
                        player,
                        is_attacker=is_attacker,
                        is_defender=is_defender,
                        pass_count=pass_count,
                    )
                )

            # Create new state
            new_state = replace(
                state,
                players=new_players,
                attacker_index=next_attacker_idx,
                defender_index=new_defender_idx,
                active_player_index=next_attacker_idx,
            )

            # Emit an event
            event_bus = EventBus.get_instance()
            event_bus.emit(
                EngineEventType.CUSTOM_EVENT,
                {
                    "event_name": "ATTACK_PASSED",
                    "game_id": state.id,
                    "player_id": player_id,
                    "player_name": state.players[player_idx].name,
                    "next_attacker": new_players[next_attacker_idx].name,
                    "next_defender": new_players[new_defender_idx].name,
                    "timestamp": new_state.timestamp,
                },
            )

            return new_state

        # If in THROWING_IN stage, and all eligible attackers pass, end the round
        if state.stage == GameStage.THROWING_IN:
            player = state.players[player_idx]

            # Update pass count for this player
            new_players = list(state.players)
            new_players[player_idx] = replace(player, pass_count=player.pass_count + 1)

            # Create a temporary state with updated player
            temp_state = replace(state, players=new_players)

            # Check if all eligible attackers have passed
            all_passed = True
            for i, p in enumerate(new_players):
                if i != temp_state.defender_index and not p.is_out:
                    # This player could attack
                    if p.pass_count == 0:
                        all_passed = False
                        break

            # If all have passed, end the round
            if all_passed:
                new_state = StateTransitionEngine.end_round(
                    temp_state, defender_won=True
                )
                return new_state

            # Otherwise, just update state and move to next player
            next_player_idx = (player_idx + 1) % len(new_players)
            # Skip defender and players who are out
            while (
                next_player_idx == temp_state.defender_index
                or new_players[next_player_idx].is_out
            ):
                next_player_idx = (next_player_idx + 1) % len(new_players)

            # Create new state
            new_state = replace(
                temp_state,
                active_player_index=next_player_idx,
            )

            # Emit an event
            event_bus = EventBus.get_instance()
            event_bus.emit(
                EngineEventType.CUSTOM_EVENT,
                {
                    "event_name": "THROW_IN_PASSED",
                    "game_id": state.id,
                    "player_id": player_id,
                    "player_name": player.name,
                    "next_player": new_players[next_player_idx].name,
                    "timestamp": new_state.timestamp,
                },
            )

            return new_state

        # Default behavior if nothing specific happened
        return state

    @staticmethod
    def take_cards(state: GameState, player_id: str) -> GameState:
        """
        Defender takes all cards on the table.

        Args:
            state: Current game state
            player_id: ID of the player taking cards (should be defender)

        Returns:
            New game state after taking cards
        """
        if state.stage != GameStage.DEFENSE:
            return state  # Not in defense stage

        # Find the player
        player_idx = None
        for i, player in enumerate(state.players):
            if player.id == player_id:
                player_idx = i
                break

        if player_idx is None or not state.players[player_idx].is_defender:
            return state  # Not a valid defender

        player = state.players[player_idx]

        # Add all cards on the table to the player's hand
        new_hand = list(player.hand)
        for card in state.table.attack_cards + state.table.defense_cards:
            new_hand.append(card)

        # Create a new player with the updated hand
        new_player = replace(player, hand=new_hand)

        # Create a new list of players with the updated player
        new_players = list(state.players)
        new_players[player_idx] = new_player

        # Clear the table
        new_table = TableState()

        # End the round with the defender losing
        new_state = StateTransitionEngine.end_round(
            replace(state, players=new_players, table=new_table), defender_won=False
        )

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.CUSTOM_EVENT,
            {
                "event_name": "DEFENDER_TOOK_CARDS",
                "game_id": state.id,
                "player_id": player_id,
                "player_name": player.name,
                "card_count": len(state.table.attack_cards)
                + len(state.table.defense_cards),
                "new_hand_size": len(new_hand),
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def pass_attack_to_player(
        state: GameState, player_id: str, target_player_id: str
    ) -> GameState:
        """
        Pass the attack to another player (Perevodnoy variant).

        Args:
            state: Current game state
            player_id: ID of the current defender
            target_player_id: ID of the player to pass the attack to

        Returns:
            New game state after passing the attack
        """
        if not state.rules.allow_passing or state.stage != GameStage.DEFENSE:
            return state  # Passing not allowed or not in defense stage

        # Find the players
        defender_idx = None
        target_idx = None

        for i, player in enumerate(state.players):
            if player.id == player_id:
                defender_idx = i
            elif player.id == target_player_id:
                target_idx = i

        if defender_idx is None or not state.players[defender_idx].is_defender:
            return state  # Not a valid defender

        if (
            target_idx is None
            or target_idx == defender_idx
            or state.players[target_idx].is_out
        ):
            return state  # Invalid target player

        # The last defense card must match at least one card in target's hand
        if not state.table.defense_cards:
            return state  # No defense cards played yet

        target_player = state.players[target_idx]

        # Check if the target player has a card of the same rank
        has_matching_rank = any(
            get_durak_value(card.rank)
            == get_durak_value(state.table.defense_cards[-1].rank)
            for card in target_player.hand
        )

        if not has_matching_rank:
            return state  # Target player doesn't have a matching card

        # Update player roles
        new_players = []
        for i, player in enumerate(state.players):
            # Current defender is no longer defending
            if i == defender_idx:
                new_players.append(replace(player, is_defender=False))
            # Target player becomes the new defender
            elif i == target_idx:
                new_players.append(replace(player, is_defender=True))
            # Other players maintain their roles
            else:
                new_players.append(player)

        # Create a new state with updated roles and stage
        new_state = replace(
            state,
            players=new_players,
            defender_index=target_idx,
            active_player_index=target_idx,  # New defender's turn
            stage=GameStage.DEFENSE,  # Stay in defense stage
        )

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.CUSTOM_EVENT,
            {
                "event_name": "ATTACK_PASSED_TO_PLAYER",
                "game_id": state.id,
                "from_player_id": player_id,
                "from_player_name": state.players[defender_idx].name,
                "to_player_id": target_player_id,
                "to_player_name": target_player.name,
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def end_round(state: GameState, defender_won: bool) -> GameState:
        """
        End the current round.

        Args:
            state: Current game state
            defender_won: Whether the defender successfully defended

        Returns:
            New game state after ending the round
        """
        # Calculate the next attacker and defender
        next_attacker_idx = None
        next_defender_idx = None

        if defender_won:
            # Defender becomes the next attacker
            next_attacker_idx = state.defender_index
            next_defender_idx = (state.defender_index + 1) % len(state.players)
            # Skip players who are out
            while state.players[next_defender_idx].is_out:
                next_defender_idx = (next_defender_idx + 1) % len(state.players)
        else:
            # Current attacker stays as attacker, defender gets skipped
            next_attacker_idx = state.attacker_index
            next_defender_idx = (state.defender_index + 1) % len(state.players)
            # Skip players who are out
            while state.players[next_defender_idx].is_out:
                next_defender_idx = (next_defender_idx + 1) % len(state.players)

        # Move all cards from table to discard pile
        new_discard_pile = list(state.discard_pile)
        for card in state.table.attack_cards + state.table.defense_cards:
            new_discard_pile.append(card)

        # Refill player hands
        new_deck = list(state.deck)
        new_players = []

        for i, player in enumerate(state.players):
            # Skip refill for players who are out
            if player.is_out:
                new_player = replace(
                    player,
                    is_attacker=(i == next_attacker_idx),
                    is_defender=(i == next_defender_idx),
                    pass_count=0,
                )  # Reset pass count
                new_players.append(new_player)
                continue

            # Refill hand to 6 cards
            new_hand = list(player.hand)
            while len(new_hand) < state.rules.refill_hands_threshold and new_deck:
                new_hand.append(new_deck.pop(0))

            # Check if player is out of the game
            is_out = len(new_hand) == 0 and not new_deck

            # Create a new player with the updated hand
            new_player = replace(
                player,
                hand=new_hand,
                is_attacker=(i == next_attacker_idx),
                is_defender=(i == next_defender_idx),
                is_out=is_out,
                pass_count=0,
            )  # Reset pass count

            new_players.append(new_player)

        # Check if the game is over
        active_players = [p for p in new_players if not p.is_out]

        if len(active_players) <= 1:
            # Game ended
            loser_id = active_players[0].id if active_players else None

            # Create and return the final game state
            final_state = replace(
                state,
                players=new_players,
                deck=new_deck,
                discard_pile=new_discard_pile,
                table=TableState(),  # Clear the table
                stage=GameStage.GAME_END,
                loser_id=loser_id,
                current_round=state.current_round + 1,
            )

            # Emit game ended event
            event_bus = EventBus.get_instance()
            event_bus.emit(
                EngineEventType.GAME_ENDED,
                {
                    "game_id": state.id,
                    "loser_id": loser_id,
                    "loser_name": next(
                        (p.name for p in new_players if p.id == loser_id), None
                    ),
                    "round_count": final_state.current_round,
                    "timestamp": final_state.timestamp,
                },
            )

            return final_state

        # Game continues
        new_state = replace(
            state,
            players=new_players,
            deck=new_deck,
            discard_pile=new_discard_pile,
            table=TableState(),  # Clear the table
            attacker_index=next_attacker_idx,
            defender_index=next_defender_idx,
            active_player_index=next_attacker_idx,  # Attacker moves first
            stage=GameStage.ATTACK,
            current_round=state.current_round + 1,
        )

        # Emit round ended event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.ROUND_ENDED,
            {
                "game_id": state.id,
                "round_number": new_state.current_round,
                "defender_won": defender_won,
                "next_attacker": new_players[next_attacker_idx].name,
                "next_defender": new_players[next_defender_idx].name,
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
        event_bus.emit(
            EngineEventType.CUSTOM_EVENT,
            {
                "event_name": "STAGE_CHANGED",
                "game_id": state.id,
                "old_stage": state.stage.name,
                "new_stage": new_stage.name,
                "timestamp": new_state.timestamp,
            },
        )

        return new_state
