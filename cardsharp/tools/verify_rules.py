#!/usr/bin/env python
"""
Simple script to check that blackjack rules are being followed correctly.

This utility script tests the game's adherence to specified blackjack rules
by running a series of games and checking for any rule violations.

Examples:
    # Basic verification with dealer hitting soft 17
    python -m cardsharp.tools.verify_rules --dealer_hit_soft_17 --num_games 5

    # Test different blackjack payouts
    python -m cardsharp.tools.verify_rules --blackjack_payout 1.2 --num_games 10

    # Test all rule variations
    python -m cardsharp.tools.verify_rules --dealer_hit_soft_17 --allow_double_after_split \
        --allow_resplitting --allow_surrender --num_games 20
"""

from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.common.io_interface import DummyIOInterface
from cardsharp.common.shoe import Shoe
from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.blackjack.action import Action
from cardsharp.blackjack.state import PlacingBetsState

import argparse

def main():
    parser = argparse.ArgumentParser(description="Verify blackjack rules are being followed")
    parser.add_argument("--num_games", type=int, default=10, help="Number of games to play")
    parser.add_argument("--dealer_hit_soft_17", action="store_true", help="Dealer hits on soft 17")
    parser.add_argument("--num_decks", type=int, default=6, help="Number of decks in the shoe")
    parser.add_argument("--min_bet", type=float, default=10.0, help="Minimum bet allowed")
    parser.add_argument("--max_bet", type=float, default=500.0, help="Maximum bet allowed")
    parser.add_argument("--allow_double_after_split", action="store_true", help="Allow doubling after splitting")
    parser.add_argument("--allow_resplitting", action="store_true", help="Allow resplitting")
    parser.add_argument("--allow_surrender", action="store_true", help="Allow surrender option")
    parser.add_argument("--blackjack_payout", type=float, default=1.5, help="Payout for blackjack (e.g., 1.5 for 3:2)")
    parser.add_argument("--use_csm", action="store_true", help="Use continuous shuffling machine")
    args = parser.parse_args()
    
    # Create rules based on arguments
    rules = Rules(
        blackjack_payout=args.blackjack_payout,
        dealer_hit_soft_17=args.dealer_hit_soft_17,
        allow_split=True,
        allow_double_down=True,
        allow_insurance=True,
        allow_surrender=args.allow_surrender,
        num_decks=args.num_decks,
        min_bet=args.min_bet,
        max_bet=args.max_bet,
        allow_late_surrender=args.allow_surrender,
        allow_double_after_split=args.allow_double_after_split,
        allow_resplitting=args.allow_resplitting,
        dealer_peek=True,
        use_csm=args.use_csm
    )
    
    print(f"Running {args.num_games} games with the following rules:")
    print(f"  Dealer hits soft 17: {rules.dealer_hit_soft_17}")
    print(f"  Number of decks: {rules.num_decks}")
    print(f"  Blackjack payout: {rules.blackjack_payout}:1")
    print(f"  Double after split: {rules.allow_double_after_split}")
    print(f"  Resplitting allowed: {rules.allow_resplitting}")
    print(f"  Surrender allowed: {rules.allow_surrender}")
    print(f"  Continuous shuffling: {rules.use_csm}")
    print(f"  Bet limits: ${rules.min_bet}-${rules.max_bet}")
    
    # Create a dummy IO interface
    io_interface = DummyIOInterface()
    
    # Track rule violation stats
    rule_violations = {
        "dealer_actions": 0,
        "player_options": 0,
        "payouts": 0,
        "total_games": 0,
        "blackjacks": 0,
        "splits": 0,
        "doubles": 0,
        "surrenders": 0,
        "insurance": 0,
        "busts": 0
    }
    
    # Run the specified number of games
    shoe = Shoe(num_decks=rules.num_decks, penetration=0.75, use_csm=rules.use_csm)
    for game_num in range(args.num_games):
        print(f"\nGame {game_num+1}/{args.num_games}:")
        
        # Create new game instance
        game = BlackjackGame(rules=rules, io_interface=io_interface, shoe=shoe)
        
        # Add player with basic strategy
        player = Player("Player1", io_interface, BasicStrategy())
        game.add_player(player)
        
        # Record initial state
        initial_money = player.money
        
        # Play a round
        game.set_state(PlacingBetsState())
        game.play_round()
        
        # Check what happened in the game
        rule_violations["total_games"] += 1
        
        if player.blackjack:
            rule_violations["blackjacks"] += 1
            
            # Verify blackjack payout
            expected_winnings = args.min_bet * rules.blackjack_payout
            actual_winnings = player.money - initial_money
            
            if abs(actual_winnings - expected_winnings) > 0.001:
                print(f"  VIOLATION: Incorrect blackjack payout. Expected: ${expected_winnings}, Got: ${actual_winnings}")
                rule_violations["payouts"] += 1
            else:
                print(f"  Correct blackjack payout: ${actual_winnings}")
        
        # Check for splits (would see multiple hands)
        if len(player.hands) > 1:
            rule_violations["splits"] += 1
            print(f"  Player split hands: {len(player.hands)}")
            
            # Check if doubling after split worked correctly if applicable
            for i, hand_actions in enumerate(player.action_history):
                if Action.DOUBLE in hand_actions:
                    if not rules.allow_double_after_split and i > 0:  # Split hand
                        print(f"  VIOLATION: Double after split allowed but shouldn't be")
                        rule_violations["player_options"] += 1
        
        # Check for doubling down
        for actions in player.action_history:
            if Action.DOUBLE in actions:
                rule_violations["doubles"] += 1
                print(f"  Player doubled down")
        
        # Check for surrender
        for actions in player.action_history:
            if Action.SURRENDER in actions:
                rule_violations["surrenders"] += 1
                
                # Verify surrender payout
                if player.money - initial_money != -args.min_bet / 2:
                    print(f"  VIOLATION: Incorrect surrender refund")
                    rule_violations["payouts"] += 1
        
        # Check for insurance
        if player.insurance > 0:
            rule_violations["insurance"] += 1
            print(f"  Player took insurance: ${player.insurance}")
        
        # Check for busts
        for hand in player.hands:
            if hand.value() > 21:
                rule_violations["busts"] += 1
                print(f"  Player busted with {hand.value()}")
        
        # Check dealer final action
        dealer_final_value = game.dealer.current_hand.value()
        dealer_soft = game.dealer.current_hand.is_soft
        
        # Verify dealer follows the rules
        if dealer_final_value < 17:
            print(f"  VIOLATION: Dealer stopped at {dealer_final_value} (should hit until 17+)")
            rule_violations["dealer_actions"] += 1
        elif dealer_final_value == 17 and dealer_soft and rules.dealer_hit_soft_17:
            print(f"  VIOLATION: Dealer stopped at soft 17 but should hit")
            rule_violations["dealer_actions"] += 1
        elif dealer_final_value > 21:
            print(f"  Dealer busted with {dealer_final_value}")
        else:
            print(f"  Dealer final hand: {dealer_final_value} {'(soft)' if dealer_soft else ''}")
        
        # Summarize game result
        if "dealer" in player.winner:
            print(f"  Dealer won")
        elif "player" in player.winner:
            print(f"  Player won")
        elif "draw" in player.winner:
            print(f"  Push (tie)")
        
        # Use the same shoe for the next game
        shoe = game.shoe
    
    # Print summary of rule verification
    print("\n===== Rule Verification Summary =====")
    print(f"Total games played: {rule_violations['total_games']}")
    print(f"Player blackjacks: {rule_violations['blackjacks']}")
    print(f"Player splits: {rule_violations['splits']}")
    print(f"Player doubles: {rule_violations['doubles']}")
    print(f"Player surrenders: {rule_violations['surrenders']}")
    print(f"Player insurance: {rule_violations['insurance']}")
    print(f"Player busts: {rule_violations['busts']}")
    print(f"\nRule violations:")
    print(f"  Dealer action violations: {rule_violations['dealer_actions']}")
    print(f"  Player options violations: {rule_violations['player_options']}")
    print(f"  Payout violations: {rule_violations['payouts']}")
    
    if (rule_violations['dealer_actions'] + rule_violations['player_options'] + rule_violations['payouts']) == 0:
        print("\nAll rules were followed correctly!")
    else:
        print("\nSome rules were violated. See details above.")

if __name__ == "__main__":
    main()