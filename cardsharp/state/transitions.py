"""
State transition functions for the Cardsharp engine.

This module provides pure functions for transitioning between game states,
without modifying the original state objects.
"""

from typing import Any, Optional
from dataclasses import replace

from cardsharp.state.models import (
    GameState,
    PlayerState,
    DealerState,
    HandState,
    GameStage,
)
from cardsharp.events import EventBus, EngineEventType


class StateTransitionEngine:
    """
    Pure functions for state transitions.

    This class contains static methods that implement game state transitions.
    Each method takes a state and returns a new state, without modifying the
    original.
    """

    @staticmethod
    def add_player(state: GameState, name: str, balance: float = 1000.0) -> GameState:
        """
        Add a player to the game.

        Args:
            state: Current game state
            name: Name of the player to add
            balance: Starting balance for the player

        Returns:
            New game state with the player added
        """
        # Create a new player
        new_player = PlayerState(name=name, balance=balance)

        # Create a new list of players with the new player added
        new_players = list(state.players)
        new_players.append(new_player)

        # Create and return a new game state
        new_state = replace(state, players=new_players)

        # Emit an event (if desired)
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.PLAYER_JOINED,
            {
                "game_id": state.id,
                "player_id": new_player.id,
                "player_name": new_player.name,
                "balance": new_player.balance,
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

        # Adjust the current player index if necessary
        new_current_player_index = state.current_player_index
        if player_index <= state.current_player_index:
            if len(new_players) == 0:
                # No players left
                new_current_player_index = 0
            elif state.current_player_index >= len(new_players):
                # Current player was removed and was the last player
                new_current_player_index = len(new_players) - 1
            else:
                # Current player index needs to be decreased
                new_current_player_index -= 1

        # Create and return a new game state
        new_state = replace(
            state, players=new_players, current_player_index=new_current_player_index
        )

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
    def place_bet(state: GameState, player_id: str, amount: float) -> GameState:
        """
        Place a bet for a player.

        Args:
            state: Current game state
            player_id: ID of the player placing the bet
            amount: Amount to bet

        Returns:
            New game state with the bet placed
        """
        if state.stage != GameStage.PLACING_BETS:
            # Only allowed during the betting stage
            return state

        # Find the player
        player_index = None
        for i, player in enumerate(state.players):
            if player.id == player_id:
                player_index = i
                break

        if player_index is None:
            # Player not found
            return state

        player = state.players[player_index]

        # Check if the player has enough money
        if player.balance < amount:
            # Not enough money
            return state

        # Create a new hand with the bet
        new_hand = HandState(bet=amount)

        # Create a new player with updated balance and the new hand
        new_player = replace(player, balance=player.balance - amount, hands=[new_hand])

        # Create a new list of players with the updated player
        new_players = list(state.players)
        new_players[player_index] = new_player

        # Create and return a new game state
        new_state = replace(state, players=new_players)

        # Emit an event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.PLAYER_BET,
            {
                "game_id": state.id,
                "player_id": player.id,
                "player_name": player.name,
                "amount": amount,
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def deal_card(
        state: GameState,
        card: Any,
        to_dealer: bool = False,
        player_id: Optional[str] = None,
        hand_index: int = 0,
        is_visible: bool = True,
    ) -> GameState:
        """
        Deal a card to a player or the dealer.

        Args:
            state: Current game state
            card: Card to deal
            to_dealer: Whether to deal to the dealer
            player_id: ID of the player to deal to (if not dealing to dealer)
            hand_index: Index of the hand to deal to
            is_visible: Whether the card is visible to players

        Returns:
            New game state with the card dealt
        """
        if to_dealer:
            # Deal to dealer
            dealer_hand = state.dealer.hand
            new_cards = list(dealer_hand.cards)
            new_cards.append(card)

            new_hand = replace(dealer_hand, cards=new_cards)

            # Update visibility if this is a visible card
            new_visible_count = state.dealer.visible_card_count
            if is_visible:
                new_visible_count += 1

            new_dealer = replace(
                state.dealer, hand=new_hand, visible_card_count=new_visible_count
            )

            # Create and return a new game state
            new_state = replace(
                state,
                dealer=new_dealer,
                shoe_cards_remaining=state.shoe_cards_remaining - 1,
            )

            # Emit an event
            event_bus = EventBus.get_instance()
            event_bus.emit(
                EngineEventType.CARD_DEALT,
                {
                    "game_id": state.id,
                    "is_dealer": True,
                    "card": str(card),
                    "is_hole_card": not is_visible,
                    "hand_value_before": dealer_hand.value,
                    "hand_value_after": new_hand.value,
                    "timestamp": new_state.timestamp,
                },
            )

            return new_state
        else:
            # Deal to a player
            # Find the player
            player_index = None
            for i, player in enumerate(state.players):
                if player.id == player_id:
                    player_index = i
                    break

            if player_index is None:
                # Player not found
                return state

            player = state.players[player_index]

            # Check if the hand index is valid
            if hand_index >= len(player.hands):
                # Invalid hand index
                return state

            # Create a new list of cards with the new card added
            hand = player.hands[hand_index]
            new_cards = list(hand.cards)
            new_cards.append(card)

            # Create a new hand with the updated cards
            new_hand = replace(hand, cards=new_cards)

            # Create a new list of hands with the updated hand
            new_hands = list(player.hands)
            new_hands[hand_index] = new_hand

            # Create a new player with the updated hands
            new_player = replace(player, hands=new_hands)

            # Create a new list of players with the updated player
            new_players = list(state.players)
            new_players[player_index] = new_player

            # Create and return a new game state
            new_state = replace(
                state,
                players=new_players,
                shoe_cards_remaining=state.shoe_cards_remaining - 1,
            )

            # Emit an event
            event_bus = EventBus.get_instance()
            event_bus.emit(
                EngineEventType.CARD_DEALT,
                {
                    "game_id": state.id,
                    "player_id": player.id,
                    "player_name": player.name,
                    "card": str(card),
                    "is_dealer": False,
                    "hand_id": hand.id,
                    "hand_value_before": hand.value,
                    "hand_value_after": new_hand.value,
                    "timestamp": new_state.timestamp,
                },
            )

            return new_state

    @staticmethod
    def player_action(
        state: GameState,
        player_id: str,
        action: str,
        additional_card: Optional[Any] = None,
    ) -> GameState:
        """
        Perform a player action.

        Args:
            state: Current game state
            player_id: ID of the player performing the action
            action: The action to perform (hit, stand, double, split, surrender)
            additional_card: Card to deal if the action requires it

        Returns:
            New game state after the action
        """
        if state.stage != GameStage.PLAYER_TURN:
            # Only allowed during player turn
            return state

        # Find the player
        player_index = None
        for i, player in enumerate(state.players):
            if player.id == player_id:
                player_index = i
                break

        if player_index is None or player_index != state.current_player_index:
            # Not the current player's turn
            return state

        player = state.players[player_index]

        # Check if the player has an active hand
        if not player.hands or player.current_hand_index >= len(player.hands):
            # No active hand
            return state

        hand_index = player.current_hand_index
        hand = player.hands[hand_index]

        # Process the action
        new_state = state

        if action.upper() == "HIT":
            # Hit - add a card to the hand
            if additional_card:
                new_state = StateTransitionEngine.deal_card(
                    state,
                    additional_card,
                    to_dealer=False,
                    player_id=player_id,
                    hand_index=hand_index,
                )

                # Check if the player busted
                new_player = new_state.players[player_index]
                new_hand = new_player.hands[hand_index]

                if new_hand.is_bust:
                    # Player busted - move to the next hand or player
                    new_state = StateTransitionEngine._advance_to_next_hand(new_state)

                    # Emit bust event
                    event_bus = EventBus.get_instance()
                    event_bus.emit(
                        EngineEventType.HAND_BUSTED,
                        {
                            "game_id": state.id,
                            "player_id": player.id,
                            "player_name": player.name,
                            "hand_id": new_hand.id,
                            "timestamp": new_state.timestamp,
                        },
                    )

        elif action.upper() == "STAND":
            # Stand - move to the next hand or player
            new_state = StateTransitionEngine._advance_to_next_hand(state)

        elif action.upper() == "DOUBLE":
            # Double - double the bet and add one card
            if additional_card and hand.bet <= player.balance and len(hand.cards) == 2:
                # Create a new hand with doubled bet
                new_hand = replace(hand, bet=hand.bet * 2, is_doubled=True)

                # Create a new player with the updated hand and balance
                new_hands = list(player.hands)
                new_hands[hand_index] = new_hand
                new_player = replace(
                    player, hands=new_hands, balance=player.balance - hand.bet
                )

                # Create a new list of players with the updated player
                new_players = list(state.players)
                new_players[player_index] = new_player

                # Create a new game state with the updated players
                new_state = replace(state, players=new_players)

                # Deal a card to the hand
                new_state = StateTransitionEngine.deal_card(
                    new_state,
                    additional_card,
                    to_dealer=False,
                    player_id=player_id,
                    hand_index=hand_index,
                )

                # After doubling, the hand is done - move to next hand/player
                new_state = StateTransitionEngine._advance_to_next_hand(new_state)

        elif action.upper() == "SPLIT":
            # Split - create two hands from one
            if len(hand.cards) == 2 and hand.bet <= player.balance:
                # Check if the cards can be split (same value)
                if hand.cards[0].rank == hand.cards[1].rank:
                    # Create two new hands, each with one card from the original
                    new_hand1 = HandState(
                        cards=[hand.cards[0]],
                        bet=hand.bet,
                        is_split=True,
                        original_hand_id=hand.id,
                    )

                    new_hand2 = HandState(
                        cards=[hand.cards[1]],
                        bet=hand.bet,
                        is_split=True,
                        original_hand_id=hand.id,
                    )

                    # Create a new list of hands with the two new hands replacing the original
                    new_hands = list(player.hands)
                    new_hands.pop(hand_index)
                    new_hands.insert(hand_index, new_hand1)
                    new_hands.insert(hand_index + 1, new_hand2)

                    # Create a new player with the updated hands and balance
                    new_player = replace(
                        player, hands=new_hands, balance=player.balance - hand.bet
                    )

                    # Create a new list of players with the updated player
                    new_players = list(state.players)
                    new_players[player_index] = new_player

                    # Create a new game state
                    new_state = replace(state, players=new_players)

                    # Emit split event
                    event_bus = EventBus.get_instance()
                    event_bus.emit(
                        EngineEventType.HAND_SPLIT,
                        {
                            "game_id": state.id,
                            "player_id": player.id,
                            "player_name": player.name,
                            "original_hand_id": hand.id,
                            "new_hand1_id": new_hand1.id,
                            "new_hand2_id": new_hand2.id,
                            "timestamp": new_state.timestamp,
                        },
                    )

        elif action.upper() == "SURRENDER":
            # Surrender - forfeit half the bet
            if len(hand.cards) == 2:
                # Create a new hand marked as surrendered
                new_hand = replace(
                    hand,
                    is_surrendered=True,
                    is_resolved=True,
                    result="surrender",
                    payout=hand.bet / 2,
                )

                # Create a new player with the updated hand and balance
                new_hands = list(player.hands)
                new_hands[hand_index] = new_hand
                new_player = replace(
                    player, hands=new_hands, balance=player.balance + hand.bet / 2
                )

                # Create a new list of players with the updated player
                new_players = list(state.players)
                new_players[player_index] = new_player

                # Create a new game state
                new_state = replace(state, players=new_players)

                # Move to the next hand/player
                new_state = StateTransitionEngine._advance_to_next_hand(new_state)

        # Emit player action event
        event_bus = EventBus.get_instance()
        event_bus.emit(
            EngineEventType.PLAYER_ACTION,
            {
                "game_id": state.id,
                "player_id": player.id,
                "player_name": player.name,
                "action": action.upper(),
                "hand_id": hand.id,
                "timestamp": new_state.timestamp,
            },
        )

        return new_state

    @staticmethod
    def dealer_action(
        state: GameState, action: str, additional_card: Optional[Any] = None
    ) -> GameState:
        """
        Perform a dealer action.

        Args:
            state: Current game state
            action: The action to perform (hit, stand)
            additional_card: Card to deal if the action requires it

        Returns:
            New game state after the action
        """
        if state.stage != GameStage.DEALER_TURN:
            # Only allowed during dealer turn
            return state

        if action.upper() == "HIT":
            # Hit - add a card to the dealer's hand
            if additional_card:
                new_state = StateTransitionEngine.deal_card(
                    state, additional_card, to_dealer=True, is_visible=True
                )

                # Emit dealer action event
                event_bus = EventBus.get_instance()
                event_bus.emit(
                    EngineEventType.DEALER_ACTION,
                    {
                        "game_id": state.id,
                        "action": "HIT",
                        "timestamp": new_state.timestamp,
                    },
                )

                return new_state

        elif action.upper() == "STAND":
            # Stand - dealer is done
            new_dealer = replace(state.dealer, is_done=True)
            new_state = replace(state, dealer=new_dealer)

            # Transition to end round stage
            new_state = replace(new_state, stage=GameStage.END_ROUND)

            # Emit dealer action event
            event_bus = EventBus.get_instance()
            event_bus.emit(
                EngineEventType.DEALER_ACTION,
                {
                    "game_id": state.id,
                    "action": "STAND",
                    "timestamp": new_state.timestamp,
                },
            )

            return new_state

        # If no valid action, return the original state
        return state

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
        if new_stage == GameStage.PLACING_BETS:
            event_bus.emit(
                EngineEventType.ROUND_STARTED,
                {
                    "game_id": state.id,
                    "round_number": state.round_number + 1,
                    "timestamp": new_state.timestamp,
                },
            )
        elif new_stage == GameStage.END_ROUND:
            event_bus.emit(
                EngineEventType.ROUND_ENDED,
                {
                    "game_id": state.id,
                    "round_number": state.round_number,
                    "timestamp": new_state.timestamp,
                },
            )

        return new_state

    @staticmethod
    def resolve_hands(state: GameState) -> GameState:
        """
        Resolve all hands in the game and distribute payouts.

        Args:
            state: Current game state

        Returns:
            New game state with resolved hands
        """
        if state.stage != GameStage.END_ROUND:
            # Only allowed at the end of a round
            return state

        dealer_value = state.dealer.hand.value
        dealer_has_blackjack = state.dealer.hand.is_blackjack
        dealer_is_bust = state.dealer.hand.is_bust

        # Make a copy of the players list to modify
        new_players = []

        for player in state.players:
            # Make a copy of the player's hands to modify
            new_hands = []
            new_balance = player.balance

            for hand in player.hands:
                # Skip already resolved hands
                if hand.is_resolved:
                    new_hands.append(hand)
                    continue

                # Determine the result
                result = None
                payout = 0.0

                if hand.is_surrendered:
                    # Already handled during surrender action
                    new_hands.append(hand)
                    continue

                elif hand.is_bust:
                    result = "lose"
                    payout = 0.0

                elif dealer_is_bust:
                    result = "win"
                    if hand.is_blackjack:
                        payout = hand.bet * 2.5  # Blackjack pays 3:2
                    else:
                        payout = hand.bet * 2  # Regular win pays 1:1

                elif hand.is_blackjack and not dealer_has_blackjack:
                    result = "win"
                    payout = hand.bet * 2.5  # Blackjack pays 3:2

                elif dealer_has_blackjack and not hand.is_blackjack:
                    result = "lose"
                    payout = 0.0

                elif hand.is_blackjack and dealer_has_blackjack:
                    result = "push"
                    payout = hand.bet  # Push returns the bet

                elif hand.value > dealer_value:
                    result = "win"
                    payout = hand.bet * 2  # Regular win pays 1:1

                elif hand.value < dealer_value:
                    result = "lose"
                    payout = 0.0

                else:  # hand.value == dealer_value
                    result = "push"
                    payout = hand.bet  # Push returns the bet

                # Update the player's balance
                new_balance += payout

                # Create a new hand with the result
                new_hand = replace(hand, is_resolved=True, result=result, payout=payout)

                new_hands.append(new_hand)

                # Emit hand result event
                event_bus = EventBus.get_instance()
                event_bus.emit(
                    EngineEventType.HAND_RESULT,
                    {
                        "game_id": state.id,
                        "player_id": player.id,
                        "player_name": player.name,
                        "hand_id": hand.id,
                        "result": result,
                        "payout": payout,
                        "timestamp": state.timestamp,
                    },
                )

            # Create a new player with updated hands and balance
            new_player = replace(
                player, hands=new_hands, balance=new_balance, is_done=True
            )

            new_players.append(new_player)

            # Emit bankroll updated event
            event_bus = EventBus.get_instance()
            event_bus.emit(
                EngineEventType.BANKROLL_UPDATED,
                {
                    "game_id": state.id,
                    "player_id": player.id,
                    "player_name": player.name,
                    "balance": new_balance,
                    "timestamp": state.timestamp,
                },
            )

        # Create a new game state with updated players
        new_state = replace(state, players=new_players)

        return new_state

    @staticmethod
    def prepare_new_round(state: GameState) -> GameState:
        """
        Prepare for a new round by clearing hands and incrementing the round number.

        Args:
            state: Current game state

        Returns:
            New game state ready for a new round
        """
        # Increment the round number
        new_round_number = state.round_number + 1

        # Clear hands and reset player state
        new_players = []
        for player in state.players:
            new_player = replace(player, hands=[], current_hand_index=0, is_done=False)
            new_players.append(new_player)

        # Reset dealer
        new_dealer = DealerState()

        # Create a new game state
        new_state = replace(
            state,
            players=new_players,
            dealer=new_dealer,
            current_player_index=0,
            stage=GameStage.PLACING_BETS,
            round_number=new_round_number,
        )

        return new_state

    @staticmethod
    def _advance_to_next_hand(state: GameState) -> GameState:
        """
        Advance to the next hand or player.

        Args:
            state: Current game state

        Returns:
            New game state advanced to the next hand or player
        """
        current_player_index = state.current_player_index
        current_player = state.players[current_player_index]
        current_hand_index = current_player.current_hand_index

        # Check if there are more hands for the current player
        if current_hand_index < len(current_player.hands) - 1:
            # Move to the next hand
            new_player = replace(
                current_player, current_hand_index=current_hand_index + 1
            )

            # Update the player in the list
            new_players = list(state.players)
            new_players[current_player_index] = new_player

            # Create a new game state
            new_state = replace(state, players=new_players)

            return new_state

        else:
            # Mark the current player as done
            new_player = replace(current_player, is_done=True)

            # Update the player in the list
            new_players = list(state.players)
            new_players[current_player_index] = new_player

            # Check if there are more players
            if current_player_index < len(state.players) - 1:
                # Move to the next player
                new_state = replace(
                    state,
                    players=new_players,
                    current_player_index=current_player_index + 1,
                )

                return new_state

            else:
                # All players are done - move to dealer turn
                new_state = replace(
                    state, players=new_players, stage=GameStage.DEALER_TURN
                )

                return new_state
