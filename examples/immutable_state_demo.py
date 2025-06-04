#!/usr/bin/env python3
"""
Example demonstrating the use of immutable state and state transitions.

This script shows how to use the immutable state classes and transition functions
to model a game of blackjack without modifying any state objects.
"""

import asyncio

# Check if cardsharp is installed properly
try:
    from cardsharp.state import (
        GameState,
        PlayerState,
        DealerState,
        HandState,
        GameStage,
        StateTransitionEngine,
    )
except ImportError:
    print("ERROR: CardSharp package not found or incompletely installed.")
    print("Please ensure CardSharp is installed properly with: poetry install")
    import sys

    sys.exit(1)


async def main():
    # Create a new game state
    print("Creating initial game state...")
    game_state = GameState(
        rules={"blackjack_pays": 1.5, "deck_count": 6, "dealer_hit_soft_17": False}
    )
    print(f"Initial game state created with ID: {game_state.id}")
    print(f"Current stage: {game_state.stage.name}")
    print()

    # Add players
    print("Adding players...")
    game_state = StateTransitionEngine.add_player(game_state, "Alice", 1000.0)
    game_state = StateTransitionEngine.add_player(game_state, "Bob", 500.0)

    # Print player details
    for player in game_state.players:
        print(f"Added player: {player.name} with balance: ${player.balance}")
    print()

    # Change the stage to placing bets
    print("Changing stage to PLACING_BETS...")
    game_state = StateTransitionEngine.change_stage(game_state, GameStage.PLACING_BETS)
    print(f"Current stage: {game_state.stage.name}")
    print()

    # Place bets
    print("Placing bets...")
    alice_id = game_state.players[0].id
    bob_id = game_state.players[1].id

    game_state = StateTransitionEngine.place_bet(game_state, alice_id, 50.0)
    game_state = StateTransitionEngine.place_bet(game_state, bob_id, 25.0)

    # Print bet details
    for player in game_state.players:
        for hand in player.hands:
            print(f"{player.name}'s bet: ${hand.bet}")
    print()

    # Change the stage to dealing
    print("Changing stage to DEALING...")
    game_state = StateTransitionEngine.change_stage(game_state, GameStage.DEALING)
    print(f"Current stage: {game_state.stage.name}")
    print()

    # Create a simple card class for demonstration
    class Card:
        def __init__(self, rank, suit):
            self.rank = rank
            self.suit = suit

        def __str__(self):
            return f"{self.rank}{self.suit}"

    # Deal initial cards
    print("Dealing initial cards...")

    # Deal first card to each player
    game_state = StateTransitionEngine.deal_card(
        game_state, Card("10", "♠"), to_dealer=False, player_id=alice_id, hand_index=0
    )
    game_state = StateTransitionEngine.deal_card(
        game_state, Card("J", "♥"), to_dealer=False, player_id=bob_id, hand_index=0
    )

    # Deal first card to dealer (visible)
    game_state = StateTransitionEngine.deal_card(
        game_state, Card("A", "♦"), to_dealer=True, is_visible=True
    )

    # Deal second card to each player
    game_state = StateTransitionEngine.deal_card(
        game_state, Card("Q", "♦"), to_dealer=False, player_id=alice_id, hand_index=0
    )
    game_state = StateTransitionEngine.deal_card(
        game_state, Card("9", "♣"), to_dealer=False, player_id=bob_id, hand_index=0
    )

    # Deal second card to dealer (hidden)
    game_state = StateTransitionEngine.deal_card(
        game_state, Card("K", "♣"), to_dealer=True, is_visible=False
    )

    # Print the dealt cards
    for player in game_state.players:
        card_str = ", ".join(str(card) for card in player.hands[0].cards)
        print(f"{player.name}'s cards: {card_str}")
        print(f"{player.name}'s hand value: {player.hands[0].value}")

    dealer_visible = ", ".join(str(card) for card in game_state.dealer.visible_cards)
    dealer_all = ", ".join(str(card) for card in game_state.dealer.hand.cards)
    print(f"Dealer's visible cards: {dealer_visible}")
    print(f"Dealer's all cards (hidden from players): {dealer_all}")
    print()

    # Change the stage to player turn
    print("Changing stage to PLAYER_TURN...")
    game_state = StateTransitionEngine.change_stage(game_state, GameStage.PLAYER_TURN)
    print(f"Current stage: {game_state.stage.name}")
    print(f"Current player: {game_state.current_player.name}")
    print()

    # Player actions
    print("Executing player actions...")

    # Alice has 20, stands
    print(
        f"{game_state.current_player.name} stands with {game_state.current_player.hands[0].value}"
    )
    game_state = StateTransitionEngine.player_action(game_state, alice_id, "STAND")

    print(f"Current player after Alice's action: {game_state.current_player.name}")

    # Bob has 19, stands
    print(
        f"{game_state.current_player.name} stands with {game_state.current_player.hands[0].value}"
    )
    game_state = StateTransitionEngine.player_action(game_state, bob_id, "STAND")

    print(f"Current stage after player actions: {game_state.stage.name}")
    print()

    # Dealer turn
    print("Dealer's turn...")

    # Make dealer's hole card visible
    dealer_state = DealerState(
        hand=game_state.dealer.hand,
        is_done=game_state.dealer.is_done,
        visible_card_count=len(game_state.dealer.hand.cards),
    )
    game_state = GameState(
        id=game_state.id,
        players=game_state.players,
        dealer=dealer_state,
        current_player_index=game_state.current_player_index,
        stage=game_state.stage,
        shoe_cards_remaining=game_state.shoe_cards_remaining,
        rules=game_state.rules,
        round_number=game_state.round_number,
    )

    dealer_visible = ", ".join(str(card) for card in game_state.dealer.visible_cards)
    print(f"Dealer's cards now visible: {dealer_visible}")
    print(f"Dealer's hand value: {game_state.dealer.hand.value}")
    print()

    # Dealer has 21 (blackjack), stands
    game_state = StateTransitionEngine.dealer_action(game_state, "STAND")

    print(f"Current stage after dealer action: {game_state.stage.name}")
    print()

    # Resolve hands
    print("Resolving hands...")
    game_state = StateTransitionEngine.resolve_hands(game_state)

    # Print results
    for player in game_state.players:
        for hand in player.hands:
            print(f"{player.name}'s result: {hand.result}")
            print(f"{player.name}'s payout: ${hand.payout}")
            print(f"{player.name}'s new balance: ${player.balance}")

    print()

    # Prepare for next round
    print("Preparing for next round...")
    game_state = StateTransitionEngine.prepare_new_round(game_state)

    print(f"Round number: {game_state.round_number}")
    print(f"Current stage: {game_state.stage.name}")

    # Verify that hands were cleared
    for player in game_state.players:
        print(f"{player.name} has {len(player.hands)} hands")

    print("\nDemo completed!")


if __name__ == "__main__":
    asyncio.run(main())
