#!/usr/bin/env python
"""
Demonstration of dealer error implementation in Cardsharp.

This script demonstrates how dealer errors are implemented and how they affect gameplay,
including card exposure, miscounting, payout errors, and procedural errors.
"""

import random
import time
from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.blackjack.rules import Rules
from cardsharp.common.io_interface import ConsoleIOInterface
from cardsharp.common.shoe import Shoe
from cardsharp.blackjack.actor import Player, Dealer
from cardsharp.blackjack.strategy import BasicStrategy, CountingStrategy
from cardsharp.blackjack.state import PlacingBetsState
from cardsharp.blackjack.casino import DealerProfile


def simulate_dealer_error(game, error_type, **kwargs):
    """
    Simulate a specific dealer error and observe its effects.

    Args:
        game: BlackjackGame instance
        error_type: Type of error to simulate
        **kwargs: Additional parameters specific to the error type
    """
    print(f"\n=== Simulating {error_type.upper()} Error ===")

    # Apply the error
    result = game.apply_dealer_error(error_type, **kwargs)

    if result:
        print(f"✓ Successfully applied {error_type} error")
    else:
        print(f"✗ Failed to apply {error_type} error")

    # Display relevant state
    if error_type == "card_exposure":
        # In a real game, the player's strategy would be informed
        if hasattr(game.players[0].strategy, "exposed_cards"):
            print(
                f"Player strategy now knows about {len(game.players[0].strategy.exposed_cards)} exposed cards"
            )

    elif error_type == "miscount":
        # Show the miscount effect
        print(f"Dealer's hand actual value: {game.dealer.current_hand.value()}")
        # The miscount is temporary and would affect dealer decisions

    elif error_type == "payout":
        # Show the payout effect
        player = game.players[0]
        print(f"Player's money after payout error: {player.money}")

    elif error_type == "procedure":
        # Show the procedure error effect
        print(
            f"Dealer's cards after procedural error: {[str(c) for c in game.dealer.current_hand.cards]}"
        )
        print(f"Dealer's hand value: {game.dealer.current_hand.value()}")


def run_demo():
    """Run a demonstration of dealer errors in blackjack."""
    print("\n====== CARDSHARP DEALER ERRORS DEMONSTRATION ======\n")

    # Create a game with console output
    rules = Rules()
    io = ConsoleIOInterface()
    shoe = Shoe(num_decks=1)
    game = BlackjackGame(rules=rules, io_interface=io, shoe=shoe)

    # Add a player using CountingStrategy which can benefit from errors
    strategy = CountingStrategy()
    player = Player("Demo Player", io, strategy, initial_money=1000)
    game.add_player(player)

    # Set up a simple game state
    player.place_bet(20, 10)

    # Deal cards to player and dealer
    print("\nDealing cards...")
    player.add_card(shoe.deal())
    dealer_card = shoe.deal()
    game.dealer.add_card(dealer_card)
    player.add_card(shoe.deal())
    hole_card = shoe.deal()
    game.dealer.add_card(hole_card)

    print(f"Player's hand: {[str(c) for c in player.current_hand.cards]}")
    print(f"Player's hand value: {player.current_hand.value()}")
    print(f"Dealer's up card: {dealer_card}")
    print(f"(Hidden) Dealer's hole card: {hole_card}")

    # Simulate each type of dealer error
    print("\nNow we'll demonstrate each type of dealer error...")
    time.sleep(2)

    # Card Exposure Error
    simulate_dealer_error(game, "card_exposure", player=player)
    time.sleep(1)

    # Miscount Error
    simulate_dealer_error(
        game, "miscount", error_direction=1, error_amount=2  # Count too high
    )  # By 2 points
    time.sleep(1)

    # Payout Error
    simulate_dealer_error(
        game, "payout", player=player, is_overpay=True, error_amount=5
    )
    time.sleep(1)

    # Procedure Error
    simulate_dealer_error(game, "procedure", procedure_type="hit_when_should_stand")

    print("\n====== DEALER ERROR DEMONSTRATION COMPLETE ======")
    print(
        """
    This demonstration shows how dealer errors are implemented in Cardsharp:
    
    1. Card Exposure - Dealer accidentally reveals cards that should be hidden
    2. Miscount - Dealer incorrectly counts hand values
    3. Payout - Dealer pays incorrect amounts
    4. Procedure - Dealer makes mistakes in game procedure
    
    These errors make the simulation more realistic and can be exploited by
    advanced strategies like card counting.
    """
    )


if __name__ == "__main__":
    run_demo()
