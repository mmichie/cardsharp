"""
Event-emitting versions of blackjack game states.

This module enhances the state classes with event emission capabilities
for game state verification and analysis.
"""

from typing import Any, Dict, List, Optional
import uuid
import time

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.state import (
    GameState,
    WaitingForPlayersState,
    PlacingBetsState,
    DealingState,
    OfferInsuranceState,
    PlayersTurnState,
    DealersTurnState,
    EndRoundState,
)
from cardsharp.verification.events import EventType, EventEmitter, GameEvent


class EventEmittingGameState(GameState, EventEmitter):
    """
    Base class for game states that emit events.

    This class combines the GameState class with the EventEmitter class
    to create a state that can emit events.
    """

    def __init__(self):
        """Initialize the game state with event emission capabilities."""
        EventEmitter.__init__(self)
        self.game_id = None
        self.round_id = None

    def set_context(self, game, round_number: int) -> None:
        """
        Set the context for the state's events.

        Args:
            game: The game instance
            round_number: The current round number
        """
        # Generate IDs if not already set
        if not self.game_id:
            self.game_id = str(uuid.uuid4())

        self.round_id = f"{self.game_id}_{round_number}"

        # Set the context for the event emitter
        super().set_context(self.game_id, self.round_id)


class EventEmittingWaitingForPlayersState(
    WaitingForPlayersState, EventEmittingGameState
):
    """WaitingForPlayersState that emits events."""

    def handle(self, game) -> None:
        """Handle the state, emitting events along the way."""
        # Emit game start event
        self.emit(
            EventType.GAME_START,
            {
                "game_id": self.game_id,
                "rules_config": {
                    "num_decks": game.rules.num_decks,
                    "penetration": 0.75,  # Default penetration
                    "use_csm": game.rules.is_using_csm(),
                    "dealer_hit_soft_17": game.rules.dealer_hit_soft_17,
                    "blackjack_payout": game.rules.blackjack_payout,
                    "min_bet": game.rules.min_bet,
                    "max_bet": game.rules.max_bet,
                    "allow_split": game.rules.allow_split,
                    "allow_double_down": game.rules.allow_double_down,
                    "allow_insurance": game.rules.allow_insurance,
                    "allow_surrender": game.rules.allow_surrender,
                    "insurance_payout": game.rules.get_insurance_payout(),
                },
                "player_count": len(game.players),
                "timestamp": time.time(),
            },
        )

        # Call the original handle method
        super().handle(game)

    def add_player(self, game, player) -> None:
        """Add a player to the game, emitting an event."""
        super().add_player(game, player)

        # Emit player joined event (not a standard EventType, but could add one)
        self.emit(
            EventType.GAME_START,
            {
                "player_id": id(player),
                "player_name": player.name,
                "player_money": player.money,
            },
        )


class EventEmittingPlacingBetsState(PlacingBetsState, EventEmittingGameState):
    """PlacingBetsState that emits events."""

    def handle(self, game) -> None:
        # Set the context for this round
        self.set_context(game, game.stats.games_played + 1)

        # Call the original handle method
        super().handle(game)

    def place_bet(self, game, player, amount) -> None:
        """Place a bet for a player, emitting an event."""
        # Call the original place bet method
        super().place_bet(game, player, amount)

        # Emit bet placed event
        self.emit(
            EventType.BET_PLACED,
            {
                "round_id": self.round_id,
                "player_id": id(player),
                "player_name": player.name,
                "seat_position": game.players.index(player),
                "amount": amount,
                "timestamp": time.time(),
            },
        )


class EventEmittingDealingState(DealingState, EventEmittingGameState):
    """DealingState that emits events."""

    def handle(self, game) -> None:
        # Check for context
        if not self.game_id or not self.round_id:
            self.set_context(game, game.stats.games_played)

        # Emit dealing state start event
        self.emit(
            EventType.INITIAL_DEAL,
            {"round_id": self.round_id, "timestamp": time.time()},
        )

        # Call the original handle method
        super().handle(game)

    def deal(self, game) -> None:
        """Deal cards, emitting events for each card dealt."""
        # Skip output for simulation mode
        is_dummy_io = isinstance(game.io_interface, DummyIOInterface)

        # Optimize dealing loop - reduce method lookups by having players_with_dealer ready
        players_with_dealer = game.players + [game.dealer]

        # First round - deal one card to each player and dealer
        for player in players_with_dealer:
            card = game.shoe.deal()
            player.add_card(card)
            game.add_visible_card(card)

            # Emit card dealt event
            self.emit(
                EventType.CARD_DEALT,
                {
                    "round_id": self.round_id,
                    "player_id": id(player) if player != game.dealer else "dealer",
                    "player_name": player.name,
                    "card": str(card),
                    "is_dealer": player == game.dealer,
                    "hand_id": id(player.current_hand),
                    "hand_value_before": player.current_hand.value()
                    - card.rank.rank_value,
                    "hand_value_after": player.current_hand.value(),
                    "timestamp": time.time(),
                },
            )

            if not is_dummy_io and player != game.dealer:
                game.io_interface.output(f"Dealt {card} to {player.name}.")

        # Second round - deal second card to each player and dealer
        for player in players_with_dealer:
            card = game.shoe.deal()
            player.add_card(card)
            game.add_visible_card(card)

            # Emit card dealt event
            self.emit(
                EventType.CARD_DEALT,
                {
                    "round_id": self.round_id,
                    "player_id": id(player) if player != game.dealer else "dealer",
                    "player_name": player.name,
                    "card": str(card),
                    "is_dealer": player == game.dealer,
                    "hand_id": id(player.current_hand),
                    "hand_value_before": player.current_hand.value()
                    - card.rank.rank_value,
                    "hand_value_after": player.current_hand.value(),
                    "timestamp": time.time(),
                },
            )

            if not is_dummy_io and player != game.dealer:
                game.io_interface.output(f"Dealt {card} to {player.name}.")

    def check_blackjack(self, game) -> None:
        """Check for blackjack, emitting events."""
        dealer_has_blackjack = game.dealer.current_hand.is_blackjack

        # First, check if the dealer has blackjack
        if dealer_has_blackjack:
            # Emit dealer blackjack event
            self.emit(
                EventType.HAND_RESULT,
                {
                    "round_id": self.round_id,
                    "player_id": "dealer",
                    "hand_id": id(game.dealer.current_hand),
                    "is_blackjack": True,
                    "timestamp": time.time(),
                },
            )

            # Rest of the original method...
            game.io_interface.output("Dealer got a blackjack!")

            # Handle insurance bets
            # (insurance handling here)

            # Now, handle players' hands
            for player in game.players:
                if player.current_hand.is_blackjack:
                    result = "push"
                    # Emit player blackjack event
                    self.emit(
                        EventType.HAND_RESULT,
                        {
                            "round_id": self.round_id,
                            "player_id": id(player),
                            "player_name": player.name,
                            "hand_id": id(player.current_hand),
                            "result": result,
                            "is_blackjack": True,
                            "timestamp": time.time(),
                        },
                    )
                else:
                    result = "lose"
                    # Emit player lose event
                    self.emit(
                        EventType.HAND_RESULT,
                        {
                            "round_id": self.round_id,
                            "player_id": id(player),
                            "player_name": player.name,
                            "hand_id": id(player.current_hand),
                            "result": result,
                            "is_blackjack": False,
                            "timestamp": time.time(),
                        },
                    )

            # Call the original method to handle the rest of the logic
            super().check_blackjack(game)
        else:
            # Dealer does not have blackjack
            # Check for player blackjacks
            for player in game.players:
                if player.current_hand.is_blackjack:
                    # Emit player blackjack event
                    self.emit(
                        EventType.HAND_RESULT,
                        {
                            "round_id": self.round_id,
                            "player_id": id(player),
                            "player_name": player.name,
                            "hand_id": id(player.current_hand),
                            "result": "win",
                            "is_blackjack": True,
                            "timestamp": time.time(),
                        },
                    )

            # Call the original method to handle the rest of the logic
            super().check_blackjack(game)


class EventEmittingOfferInsuranceState(OfferInsuranceState, EventEmittingGameState):
    """OfferInsuranceState that emits events."""

    def handle(self, game) -> None:
        # Check for context
        if not self.game_id or not self.round_id:
            self.set_context(game, game.stats.games_played)

        dealer_up_card = game.dealer.current_hand.cards[0]
        game.io_interface.output(f"Dealer shows {dealer_up_card}.")

        # Emit dealer up card event
        self.emit(
            EventType.CARD_DEALT,
            {
                "round_id": self.round_id,
                "player_id": "dealer",
                "player_name": "Dealer",
                "card": str(dealer_up_card),
                "is_dealer": True,
                "is_up_card": True,
                "hand_id": id(game.dealer.current_hand),
                "timestamp": time.time(),
            },
        )

        # Offer insurance if dealer's upcard is an Ace
        if dealer_up_card.rank == Rank.ACE and game.rules.allow_insurance:
            # Emit insurance offered event
            self.emit(
                EventType.INSURANCE_OFFERED,
                {"round_id": self.round_id, "timestamp": time.time()},
            )

            for player in game.players:
                self.offer_insurance(game, player)

        # Call the original handle method to continue
        super().handle(game)

    def offer_insurance(self, game, player) -> None:
        """Offer insurance to a player, emitting an event."""
        wants_insurance = player.strategy.decide_insurance(player)

        # Emit insurance decision event
        self.emit(
            EventType.INSURANCE_DECISION,
            {
                "round_id": self.round_id,
                "player_id": id(player),
                "player_name": player.name,
                "wants_insurance": wants_insurance,
                "timestamp": time.time(),
            },
        )

        # Call the original method
        super().offer_insurance(game, player)


class EventEmittingPlayersTurnState(PlayersTurnState, EventEmittingGameState):
    """PlayersTurnState that emits events."""

    def handle(self, game) -> None:
        # Check for context
        if not self.game_id or not self.round_id:
            self.set_context(game, game.stats.games_played)

        # Call the original handle method
        super().handle(game)

    def get_valid_actions(self, game, player, hand_index) -> List[Action]:
        """Get valid actions for a player, emitting an event."""
        valid_actions = super().get_valid_actions(game, player, hand_index)

        # Emit player decision point event
        self.emit(
            EventType.PLAYER_DECISION_POINT,
            {
                "round_id": self.round_id,
                "player_id": id(player),
                "player_name": player.name,
                "hand_id": id(player.hands[hand_index]),
                "available_actions": [action.name for action in valid_actions],
                "hand_value": player.hands[hand_index].value(),
                "timestamp": time.time(),
            },
        )

        return valid_actions

    def player_action(self, game, player, action) -> None:
        """Handle a player action, emitting an event."""
        hand_id = id(player.current_hand)
        hand_value_before = player.current_hand.value()

        # Emit player action event
        self.emit(
            EventType.PLAYER_ACTION,
            {
                "round_id": self.round_id,
                "player_id": id(player),
                "player_name": player.name,
                "hand_id": hand_id,
                "action_type": action.name,
                "hand_value_before": hand_value_before,
                "timestamp": time.time(),
            },
        )

        # Call the original method
        super().player_action(game, player, action)

        # Emit any card received or state changes
        if action == Action.HIT:
            # A card was received - find it by checking the current hand's last card
            card = player.current_hand.cards[-1]
            self.emit(
                EventType.CARD_DEALT,
                {
                    "round_id": self.round_id,
                    "player_id": id(player),
                    "player_name": player.name,
                    "hand_id": hand_id,
                    "card": str(card),
                    "is_dealer": False,
                    "hand_value_before": hand_value_before,
                    "hand_value_after": player.current_hand.value(),
                    "timestamp": time.time(),
                },
            )

            # Check for bust
            if player.is_busted():
                self.emit(
                    EventType.HAND_RESULT,
                    {
                        "round_id": self.round_id,
                        "player_id": id(player),
                        "player_name": player.name,
                        "hand_id": hand_id,
                        "result": "lose",
                        "is_busted": True,
                        "timestamp": time.time(),
                    },
                )

        elif action == Action.DOUBLE:
            # A card was received - find it by checking the current hand's last card
            card = player.current_hand.cards[-1]
            self.emit(
                EventType.CARD_DEALT,
                {
                    "round_id": self.round_id,
                    "player_id": id(player),
                    "player_name": player.name,
                    "hand_id": hand_id,
                    "card": str(card),
                    "is_dealer": False,
                    "hand_value_before": hand_value_before,
                    "hand_value_after": player.current_hand.value(),
                    "timestamp": time.time(),
                },
            )

            # Check for bust
            if player.is_busted():
                self.emit(
                    EventType.HAND_RESULT,
                    {
                        "round_id": self.round_id,
                        "player_id": id(player),
                        "player_name": player.name,
                        "hand_id": hand_id,
                        "result": "lose",
                        "is_busted": True,
                        "timestamp": time.time(),
                    },
                )

        elif action == Action.SPLIT:
            # A split occurred - emit an event for each new hand
            curr_index = player.current_hand_index
            for i in range(curr_index, curr_index + 2):
                self.emit(
                    EventType.PLAYER_ACTION,
                    {
                        "round_id": self.round_id,
                        "player_id": id(player),
                        "player_name": player.name,
                        "hand_id": id(player.hands[i]),
                        "action_type": "split_result",
                        "hand_value": player.hands[i].value(),
                        "timestamp": time.time(),
                    },
                )

        elif action == Action.SURRENDER:
            # Surrender occurred
            self.emit(
                EventType.HAND_RESULT,
                {
                    "round_id": self.round_id,
                    "player_id": id(player),
                    "player_name": player.name,
                    "hand_id": hand_id,
                    "result": "surrender",
                    "timestamp": time.time(),
                },
            )


class EventEmittingDealersTurnState(DealersTurnState, EventEmittingGameState):
    """DealersTurnState that emits events."""

    def handle(self, game) -> None:
        # Check for context
        if not self.game_id or not self.round_id:
            self.set_context(game, game.stats.games_played)

        # Emit dealer's turn event
        self.emit(
            EventType.DEALER_DECISION_POINT,
            {"round_id": self.round_id, "timestamp": time.time()},
        )

        # Call the original handle method
        super().handle(game)

    def dealer_action(self, game) -> None:
        """Handle a dealer action, emitting an event."""
        hand_value_before = game.dealer.current_hand.value()

        # Emit dealer action event for hitting
        self.emit(
            EventType.DEALER_ACTION,
            {
                "round_id": self.round_id,
                "action_type": "hit",
                "hand_value_before": hand_value_before,
                "timestamp": time.time(),
            },
        )

        # Call the original method
        card = game.shoe.deal()
        game.dealer.add_card(card)
        game.add_visible_card(card)

        # Emit card dealt event
        self.emit(
            EventType.CARD_DEALT,
            {
                "round_id": self.round_id,
                "player_id": "dealer",
                "player_name": "Dealer",
                "card": str(card),
                "is_dealer": True,
                "hand_id": id(game.dealer.current_hand),
                "hand_value_before": hand_value_before,
                "hand_value_after": game.dealer.current_hand.value(),
                "timestamp": time.time(),
            },
        )

        game.io_interface.output(f"Dealer hits and gets {card}.")


class EventEmittingEndRoundState(EndRoundState, EventEmittingGameState):
    """EndRoundState that emits events."""

    def handle(self, game) -> None:
        # Check for context
        if not self.game_id or not self.round_id:
            self.set_context(game, game.stats.games_played)

        # Call the original handle method
        super().handle(game)

        # Emit game end event
        self.emit(
            EventType.GAME_END, {"round_id": self.round_id, "timestamp": time.time()}
        )

    def calculate_winner(self, game) -> None:
        """Calculate the winner, emitting events."""
        # Call the original method
        super().calculate_winner(game)

        # Emit events for the results
        dealer_hand_value = game.dealer.current_hand.value()
        dealer_busted = dealer_hand_value > 21

        # Emit dealer final hand event
        self.emit(
            EventType.HAND_RESULT,
            {
                "round_id": self.round_id,
                "player_id": "dealer",
                "hand_id": id(game.dealer.current_hand),
                "final_value": dealer_hand_value,
                "is_busted": dealer_busted,
                "timestamp": time.time(),
            },
        )

        for player in game.players:
            for hand_index, hand in enumerate(player.hands):
                player_hand_value = hand.value()
                result = player.winner[hand_index]

                # Emit player final hand result event
                self.emit(
                    EventType.HAND_RESULT,
                    {
                        "round_id": self.round_id,
                        "player_id": id(player),
                        "player_name": player.name,
                        "hand_id": id(hand),
                        "hand_index": hand_index,
                        "final_value": player_hand_value,
                        "is_busted": player_hand_value > 21,
                        "result": result,
                        "timestamp": time.time(),
                    },
                )

    def handle_payouts(self, game) -> None:
        """Handle payouts, emitting events."""
        # Call the original method
        super().handle_payouts(game)

        # Emit payout events
        for player in game.players:
            for hand_index, hand in enumerate(player.hands):
                bet_for_hand = player.bets[hand_index]
                if bet_for_hand == 0:
                    continue  # Skip hands with no bet

                result = player.winner[hand_index]

                # Determine payout amount
                payout = 0
                if result == "player":
                    if player.blackjack and not hand.is_split:
                        payout_multiplier = game.get_blackjack_payout()
                        payout = bet_for_hand + (bet_for_hand * payout_multiplier)
                    else:
                        payout = bet_for_hand * 2  # Regular win pays 1:1
                elif result == "draw":
                    payout = bet_for_hand
                # Lose or surrender pays nothing

                # Emit payout event
                self.emit(
                    EventType.PAYOUT,
                    {
                        "round_id": self.round_id,
                        "player_id": id(player),
                        "player_name": player.name,
                        "hand_id": id(hand),
                        "hand_index": hand_index,
                        "bet": bet_for_hand,
                        "payout": payout,
                        "result": result,
                        "timestamp": time.time(),
                    },
                )


# Replace the original state classes with the event-emitting versions
def patch_game_states():
    """
    Patch the game states with event-emitting versions.

    This function should be called before creating any game instances.
    """
    from cardsharp.blackjack import state

    state.WaitingForPlayersState = EventEmittingWaitingForPlayersState
    state.PlacingBetsState = EventEmittingPlacingBetsState
    state.DealingState = EventEmittingDealingState
    state.OfferInsuranceState = EventEmittingOfferInsuranceState
    state.PlayersTurnState = EventEmittingPlayersTurnState
    state.DealersTurnState = EventEmittingDealersTurnState
    state.EndRoundState = EventEmittingEndRoundState
