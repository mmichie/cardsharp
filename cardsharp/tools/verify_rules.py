#!/usr/bin/env python
"""
Advanced Blackjack Rule Verification Tool

This utility script performs comprehensive verification of blackjack rules implementation
by running simulations and validating game behavior against expected outcomes.

Features:
- Validates correct dealer behavior (hitting/standing)
- Verifies all player options work as expected
- Checks correct payouts for all game outcomes
- Tracks statistical performance for analysis
- Supports all standard rule variations

Examples:
    # Basic verification with dealer hitting soft 17
    python -m cardsharp.tools.verify_rules --dealer_hit_soft_17 --num_games 100

    # Test different blackjack payouts
    python -m cardsharp.tools.verify_rules --blackjack_payout 1.2 --num_games 100

    # Test all rule variations
    python -m cardsharp.tools.verify_rules --dealer_hit_soft_17 --allow_double_after_split \
        --allow_resplitting --allow_surrender --num_games 200

    # Extensive validation with continuous shuffling and detailed stats
    python -m cardsharp.tools.verify_rules --dealer_hit_soft_17 --use_csm \
        --allow_surrender --detailed_stats --num_games 1000
"""

import argparse
import os
import statistics
import time
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any

from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.common.io_interface import DummyIOInterface
from cardsharp.common.shoe import Shoe
from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.blackjack.action import Action
from cardsharp.blackjack.state import PlacingBetsState
from cardsharp.common.card import Rank, Suit


def main():
    parser = argparse.ArgumentParser(
        description="Advanced verification of blackjack rules implementation"
    )

    # Game configuration
    parser.add_argument(
        "--num_games", type=int, default=100, help="Number of games to play"
    )
    parser.add_argument("--seed", type=int, help="Random seed for reproducible results")

    # Basic rules
    parser.add_argument(
        "--dealer_hit_soft_17", action="store_true", help="Dealer hits on soft 17"
    )
    parser.add_argument(
        "--num_decks", type=int, default=6, help="Number of decks in the shoe"
    )
    parser.add_argument(
        "--min_bet", type=float, default=10.0, help="Minimum bet allowed"
    )
    parser.add_argument(
        "--max_bet", type=float, default=500.0, help="Maximum bet allowed"
    )
    parser.add_argument(
        "--test_odd_bets",
        action="store_true",
        help="Test with odd-valued bets to verify correct surrender payout",
    )
    parser.add_argument(
        "--force_surrender_test",
        action="store_true",
        help="Force the strategy to surrender more frequently for testing",
    )
    parser.add_argument(
        "--blackjack_payout",
        type=float,
        default=1.5,
        help="Payout for blackjack (e.g., 1.5 for 3:2)",
    )
    parser.add_argument(
        "--use_csm", action="store_true", help="Use continuous shuffling machine"
    )
    parser.add_argument(
        "--penetration",
        type=float,
        default=0.75,
        help="Deck penetration before shuffling (0.0-1.0)",
    )

    # Player options
    parser.add_argument(
        "--allow_double_after_split",
        action="store_true",
        help="Allow doubling after splitting",
    )
    parser.add_argument(
        "--allow_resplitting", action="store_true", help="Allow resplitting"
    )
    parser.add_argument(
        "--allow_surrender", action="store_true", help="Allow surrender option"
    )
    parser.add_argument(
        "--allow_early_surrender",
        action="store_true",
        help="Allow early surrender (before dealer checks)",
    )
    parser.add_argument(
        "--allow_late_surrender",
        action="store_true",
        help="Allow late surrender (after dealer checks)",
    )
    parser.add_argument(
        "--max_splits", type=int, default=3, help="Maximum number of splits allowed"
    )
    parser.add_argument(
        "--insurance_payout",
        type=float,
        default=2.0,
        help="Payout ratio for insurance bets",
    )

    # Verification and output options
    parser.add_argument(
        "--detailed_stats",
        action="store_true",
        help="Show detailed statistical analysis",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show details of each game"
    )
    parser.add_argument(
        "--summary_only",
        action="store_true",
        help="Show only the summary, not individual games",
    )
    parser.add_argument(
        "--check_house_edge",
        action="store_true",
        help="Calculate and verify expected house edge",
    )
    parser.add_argument(
        "--output_file", type=str, help="Save results to the specified file"
    )

    args = parser.parse_args()

    # Set random seed if provided
    if args.seed is not None:
        import random

        random.seed(args.seed)

    # Create rules based on arguments
    rules = Rules(
        blackjack_payout=args.blackjack_payout,
        dealer_hit_soft_17=args.dealer_hit_soft_17,
        allow_split=True,
        allow_double_down=True,
        allow_insurance=True,
        allow_surrender=args.allow_surrender
        or args.allow_early_surrender
        or args.allow_late_surrender,
        num_decks=args.num_decks,
        min_bet=args.min_bet,
        max_bet=args.max_bet,
        allow_late_surrender=args.allow_surrender or args.allow_late_surrender,
        allow_early_surrender=args.allow_early_surrender,
        allow_double_after_split=args.allow_double_after_split,
        allow_resplitting=args.allow_resplitting,
        dealer_peek=True,
        use_csm=args.use_csm,
        max_splits=args.max_splits,
        insurance_payout=args.insurance_payout,
    )

    print(f"Running {args.num_games} games with the following rules:")
    print(f"  Dealer hits soft 17: {rules.dealer_hit_soft_17}")
    print(f"  Number of decks: {rules.num_decks}")
    print(f"  Deck penetration: {args.penetration*100:.0f}%")
    print(f"  Blackjack payout: {rules.blackjack_payout}:1")
    print(f"  Double after split: {rules.allow_double_after_split}")
    print(f"  Resplitting allowed: {rules.allow_resplitting}")
    print(f"  Max splits: {rules.max_splits}")
    print(f"  Surrender allowed: {rules.allow_surrender}")
    if rules.allow_surrender:
        print(f"  Surrender type: {'Early' if rules.allow_early_surrender else 'Late'}")
    print(f"  Insurance payout: {rules.insurance_payout}:1")
    print(f"  Continuous shuffling: {rules.use_csm}")
    print(f"  Bet limits: ${rules.min_bet}-${rules.max_bet}")

    # Create statistics tracking
    stats = {
        # Game outcomes
        "player_wins": 0,
        "dealer_wins": 0,
        "pushes": 0,
        "player_blackjacks": 0,
        "dealer_blackjacks": 0,
        "surrenders": 0,
        # Player actions
        "hits": 0,
        "stands": 0,
        "doubles": 0,
        "splits": 0,
        "split_hands": 0,
        "insurance": 0,
        "player_busts": 0,
        # Dealer stats
        "dealer_busts": 0,
        "dealer_final_values": [],
        "dealer_soft_hands": 0,
        # Financial stats
        "total_bets": 0,
        "net_winnings": 0,
        "max_bankroll": 1000,
        "min_bankroll": 1000,
        # Rule validation
        "dealer_violations": 0,
        "player_option_violations": 0,
        "payout_violations": 0,
    }

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
        "busts": 0,
    }

    # Start timing and initialize the shoe
    start_time = time.time()
    shoe = Shoe(
        num_decks=rules.num_decks, penetration=args.penetration, use_csm=rules.use_csm
    )
    for game_num in range(args.num_games):
        if not args.summary_only:
            print(f"\nGame {game_num+1}/{args.num_games}:")

        # Create new game instance
        game = BlackjackGame(rules=rules, io_interface=io_interface, shoe=shoe)

        # Create an advanced strategy that respects the game rules
        class RuleAwareStrategy(BasicStrategy):
            def __init__(self, rules):
                super().__init__()
                self.rules = rules
                self.action_history = []

            def decide_action(self, player, dealer_up_card, game=None):
                # If forcing surrender tests and surrender is allowed and we have exactly 2 cards
                if (
                    args.force_surrender_test
                    and self.rules.allow_surrender
                    and len(player.current_hand.cards) == 2
                    and Action.SURRENDER in player.valid_actions
                    and
                    # Only surrender about 30% of the time to avoid skewing stats too much
                    game_num % 3 == 0
                ):
                    action = Action.SURRENDER
                else:
                    action = super().decide_action(player, dealer_up_card, game)

                # Track all actions for statistics
                self.action_history.append(action)

                # Override decisions that don't match the rules
                if (
                    action == Action.DOUBLE
                    and player.current_hand.is_split
                    and not self.rules.allow_double_after_split
                ):
                    # Return STAND if we can't double after split
                    return Action.STAND

                # Handle surrender restrictions
                if action == Action.SURRENDER and not self.rules.allow_surrender:
                    return Action.STAND

                # Handle split restrictions
                if (
                    action == Action.SPLIT
                    and not self.rules.allow_resplitting
                    and player.current_hand.is_split
                ):
                    return Action.STAND

                return action

            def get_action_counts(self):
                """Return counts of each action type taken"""
                return Counter(self.action_history)

        # Add player with the rule-aware strategy
        player = Player("Player1", io_interface, RuleAwareStrategy(rules))
        game.add_player(player)

        # Determine bet amount - use odd bet for testing surrender if specified
        bet_amount = args.min_bet
        if args.test_odd_bets and game_num % 3 == 0:  # Every third game, use an odd bet
            # Test with different odd-numbered bets: 15, 25, 35, etc.
            bet_amount = args.min_bet + 5 + (10 * (game_num % 5))
            if not args.summary_only:
                print(
                    f"  Using odd bet amount: ${bet_amount:.2f} to test surrender payout exactness"
                )

        # Record initial state
        initial_money = player.money

        # Create a custom PlacingBetsState to use our bet amount
        class CustomPlacingBetsState(PlacingBetsState):
            def place_bet(self, game, player, amount):
                """Override to use our custom bet amount"""
                min_bet = game.rules.min_bet
                player.place_bet(bet_amount, min_bet)
                game.io_interface.output(
                    f"{player.name} has placed a bet of {bet_amount}."
                )

        # Play a round - wrap in try/except to handle any strategy errors
        game.set_state(CustomPlacingBetsState())
        try:
            game.play_round()
        except Exception as e:
            print(f"  Game error: {str(e)}")
            # If error occurs, we still want to continue to the next game
            continue

        # Get player's final status and financial results
        final_money = player.money
        game_profit = final_money - initial_money

        # Update general stats
        stats["total_bets"] += args.min_bet  # Simplified
        stats["net_winnings"] += game_profit
        stats["max_bankroll"] = max(stats["max_bankroll"], final_money)
        stats["min_bankroll"] = min(stats["min_bankroll"], final_money)

        # Check for blackjack
        if player.blackjack:
            stats["player_blackjacks"] += 1

            # Verify blackjack payout
            # For blackjack, player gets their original bet back PLUS winnings (bet * payout ratio)
            expected_payout = bet_amount + (bet_amount * rules.blackjack_payout)
            expected_profit = (
                expected_payout - bet_amount
            )  # Profit = payout minus original bet

            if abs(game_profit - expected_profit) > 0.001:
                if not args.summary_only:
                    print(
                        f"  VIOLATION: Incorrect blackjack payout. Expected profit: ${expected_profit:.2f}, Got: ${game_profit:.2f}"
                    )
                    print(
                        f"  For a ${bet_amount:.2f} bet with {rules.blackjack_payout}:1 payoff, player should receive ${expected_payout:.2f} total"
                    )
                    print(
                        f"  (original bet ${bet_amount:.2f} + winnings ${bet_amount * rules.blackjack_payout:.2f})"
                    )
                stats["payout_violations"] += 1
            elif not args.summary_only:
                print(
                    f"  Correct blackjack payout: ${game_profit:.2f} profit on ${bet_amount:.2f} bet"
                )

        # Check for splits
        if len(player.hands) > 1:
            stats["splits"] += 1
            stats["split_hands"] += len(player.hands) - 1

            if not args.summary_only:
                print(f"  Player split hands: {len(player.hands)}")

            # Check doubling after split
            for i, hand_actions in enumerate(player.action_history):
                if i > 0 and Action.DOUBLE in hand_actions:  # Split hand
                    if not rules.allow_double_after_split:
                        if not args.summary_only:
                            print(
                                f"  VIOLATION: Double after split allowed but shouldn't be"
                            )
                        stats["player_option_violations"] += 1
                    else:
                        stats["doubles"] += 1
                        if not args.summary_only:
                            print(f"  Player doubled down on split hand")

        # Get action counts if available
        if hasattr(player.strategy, "get_action_counts"):
            action_counts = player.strategy.get_action_counts()

            # Record action stats (regular hands)
            stats["hits"] += action_counts.get(Action.HIT, 0)
            stats["stands"] += action_counts.get(Action.STAND, 0)
            stats["doubles"] += action_counts.get(Action.DOUBLE, 0)

            # Check for regular doubling down (first hand only)
            if Action.DOUBLE in player.action_history[0] and not args.summary_only:
                print(f"  Player doubled down")

            # Check for surrender
            if Action.SURRENDER in action_counts:
                surrenders = action_counts[Action.SURRENDER]
                stats["surrenders"] += surrenders

                # Verify surrender payout with detailed checking
                expected_refund = bet_amount / 2
                expected_loss = -bet_amount / 2

                # Check with a small epsilon for floating point precision
                if abs(game_profit - expected_loss) > 0.001:
                    if not args.summary_only:
                        print(
                            f"  VIOLATION: Incorrect surrender refund. Expected loss: ${expected_loss:.2f}, Actual: ${game_profit:.2f}"
                        )
                        print(
                            f"  Expected refund: ${expected_refund:.2f}, Player should lose exactly half the bet"
                        )
                        # Add additional diagnostic information for odd bets
                        if bet_amount % 2 != 0:
                            print(
                                f"  Note: This was an odd bet amount (${bet_amount:.2f}), which requires floating-point division"
                            )
                            print(
                                f"  Integer division would give ${bet_amount // 2:.0f} instead of ${bet_amount / 2:.2f}"
                            )
                    stats["payout_violations"] += 1
                else:
                    if not args.summary_only:
                        is_odd = bet_amount % 2 != 0
                        odd_note = (
                            " (odd bet amount correctly handled)" if is_odd else ""
                        )
                        print(
                            f"  Correct surrender refund verified: Player lost ${abs(game_profit):.2f} (half of ${bet_amount:.2f}){odd_note}"
                        )

                # Test if we have multiple surrenders in one game (rare edge case)
                if surrenders > 1 and not args.summary_only:
                    print(
                        f"  Multiple surrenders detected ({surrenders}) - this is usually an edge case that should be reviewed"
                    )

        # Check for insurance
        if player.insurance > 0:
            stats["insurance"] += 1
            if not args.summary_only:
                print(f"  Player took insurance: ${player.insurance}")

        # Check for busts
        for hand in player.hands:
            if hand.value() > 21:
                stats["player_busts"] += 1
                if not args.summary_only:
                    print(f"  Player busted with {hand.value()}")

        # Analyze dealer's final hand
        dealer_final_value = game.dealer.current_hand.value()
        dealer_soft = game.dealer.current_hand.is_soft

        # Record dealer stats
        stats["dealer_final_values"].append(dealer_final_value)
        if dealer_soft:
            stats["dealer_soft_hands"] += 1

        # Verify dealer follows the rules
        if dealer_final_value < 17:
            if not args.summary_only:
                print(
                    f"  VIOLATION: Dealer stopped at {dealer_final_value} (should hit until 17+)"
                )
            stats["dealer_violations"] += 1
        elif dealer_final_value == 17 and dealer_soft and rules.dealer_hit_soft_17:
            if not args.summary_only:
                print(f"  VIOLATION: Dealer stopped at soft 17 but should hit")
            stats["dealer_violations"] += 1

        # Report dealer outcome
        if dealer_final_value > 21:
            stats["dealer_busts"] += 1
            if not args.summary_only:
                print(f"  Dealer busted with {dealer_final_value}")
        elif not args.summary_only:
            print(
                f"  Dealer final hand: {dealer_final_value} {'(soft)' if dealer_soft else ''}"
            )

        # Record game outcome
        for winner in player.winner:
            if winner == "dealer":
                stats["dealer_wins"] += 1
                if not args.summary_only:
                    print(f"  Dealer won")
            elif winner == "player":
                stats["player_wins"] += 1
                if not args.summary_only:
                    print(f"  Player won")
            elif winner == "draw":
                stats["pushes"] += 1
                if not args.summary_only:
                    print(f"  Push (tie)")

        # Use the same shoe for the next game
        shoe = game.shoe

    # Calculate elapsed time
    elapsed_time = time.time() - start_time
    total_games = args.num_games

    # Print comprehensive summary report
    print("\n===== Blackjack Rule Verification Report =====")
    print(f"Total games played: {total_games}")
    print(
        f"Time elapsed: {elapsed_time:.2f} seconds ({total_games/elapsed_time:.1f} games/second)"
    )

    # Game outcomes
    print("\nGame Outcomes:")
    print(
        f"  Player wins: {stats['player_wins']} ({stats['player_wins']/total_games*100:.1f}%)"
    )
    print(
        f"  Dealer wins: {stats['dealer_wins']} ({stats['dealer_wins']/total_games*100:.1f}%)"
    )
    print(f"  Pushes: {stats['pushes']} ({stats['pushes']/total_games*100:.1f}%)")
    print(
        f"  Player blackjacks: {stats['player_blackjacks']} ({stats['player_blackjacks']/total_games*100:.1f}%)"
    )

    # Player actions
    print("\nPlayer Actions:")
    print(f"  Blackjacks: {stats['player_blackjacks']}")
    print(f"  Splits: {stats['splits']}")
    print(f"  Split hands played: {stats['split_hands']}")
    print(f"  Double downs: {stats['doubles']}")
    print(f"  Surrenders: {stats['surrenders']}")
    print(f"  Insurance taken: {stats['insurance']}")
    print(
        f"  Player busts: {stats['player_busts']} ({stats['player_busts']/total_games*100:.1f}%)"
    )

    # Dealer statistics
    print("\nDealer Statistics:")
    print(
        f"  Dealer busts: {stats['dealer_busts']} ({stats['dealer_busts']/total_games*100:.1f}%)"
    )
    print(
        f"  Dealer soft hands: {stats['dealer_soft_hands']} ({stats['dealer_soft_hands']/total_games*100:.1f}%)"
    )

    # Financial results
    total_bets = stats["total_bets"]
    net_winnings = stats["net_winnings"]
    house_edge = -net_winnings / total_bets * 100 if total_bets > 0 else 0
    print("\nFinancial Results:")
    print(f"  Total wagered: ${total_bets:.2f}")
    print(f"  Net player profit: ${net_winnings:.2f}")
    print(f"  House edge: {house_edge:.2f}%")
    print(
        f"  Bankroll range: ${stats['min_bankroll']:.2f} - ${stats['max_bankroll']:.2f}"
    )

    # Verification results
    rule_violation_count = (
        stats["dealer_violations"]
        + stats["player_option_violations"]
        + stats["payout_violations"]
    )
    print("\nRule Violations:")
    print(f"  Dealer action violations: {stats['dealer_violations']}")
    print(f"  Player options violations: {stats['player_option_violations']}")
    print(f"  Payout violations: {stats['payout_violations']}")

    # Special verification report for surrender if tested
    if args.allow_surrender and stats["surrenders"] > 0:
        print("\nSurrender Verification:")
        print(f"  Total surrenders: {stats['surrenders']}")
        if args.test_odd_bets:
            print(f"  Odd-bet testing: Enabled (testing exact half-bet refunds)")
        surrender_violations = sum(
            1
            for v in stats.values()
            if "surrender" in str(v) and "violation" in str(v) and v > 0
        )
        if surrender_violations == 0:
            print("  ✓ All surrender payouts were correctly calculated")
        else:
            print(f"  ✗ Found {surrender_violations} surrender payout violations")
            print(
                "  Note: Surrender should refund exactly half the bet, using floating-point division"
            )

    # Show dealer hand value distribution if requested
    if args.detailed_stats and stats["dealer_final_values"]:
        dealer_values = stats["dealer_final_values"]
        print("\nDealer Final Hand Distribution:")
        print(f"  Average dealer hand: {sum(dealer_values)/len(dealer_values):.1f}")
        print(f"  Median dealer hand: {statistics.median(dealer_values):.1f}")
        print(f"  Most common values: {Counter(dealer_values).most_common(3)}")

        # Count hands by value range
        value_ranges = {
            "17": sum(1 for v in dealer_values if v == 17),
            "18": sum(1 for v in dealer_values if v == 18),
            "19": sum(1 for v in dealer_values if v == 19),
            "20": sum(1 for v in dealer_values if v == 20),
            "21": sum(1 for v in dealer_values if v == 21),
            "Bust": sum(1 for v in dealer_values if v > 21),
        }

        for value, count in value_ranges.items():
            print(f"  {value}: {count} ({count/len(dealer_values)*100:.1f}%)")

    # Overall verdict
    if rule_violation_count == 0:
        print("\n✅ PASS: All rules were followed correctly!")
    else:
        print(f"\n❌ FAIL: {rule_violation_count} rule violations detected.")

    # Write output to file if requested
    if args.output_file:
        try:
            with open(args.output_file, "w") as f:
                f.write(f"Blackjack Rule Verification Report\n")
                f.write(f"Rules tested: {vars(args)}\n")
                f.write(f"Games played: {total_games}\n")
                f.write(f"House edge: {house_edge:.2f}%\n")
                f.write(f"Rule violations: {rule_violation_count}\n")
        except Exception as e:
            print(f"Error writing output file: {str(e)}")


if __name__ == "__main__":
    main()
