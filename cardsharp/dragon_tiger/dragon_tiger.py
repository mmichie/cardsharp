"""
Dragon Tiger game CLI and simulation interface.

Run simulations and analyze the house edge for different bet types.
"""

import argparse
import time
from typing import Dict

from cardsharp.dragon_tiger.game import DragonTigerGame, BetType, Outcome, DragonTigerRules


def run_simulation(num_games: int = 10000, bet_type: BetType = BetType.DRAGON, bet_amount: float = 10,
                   num_decks: int = 8, tie_push: bool = False, verbose: bool = False) -> Dict:
    """
    Run a Dragon Tiger simulation.

    Args:
        num_games: Number of games to simulate
        bet_type: Type of bet (Dragon, Tiger, or Tie)
        bet_amount: Amount to bet per game
        num_decks: Number of decks in the shoe
        tie_push: Whether Dragon/Tiger bets push on tie (vs losing)
        verbose: Print detailed results

    Returns:
        Dictionary with simulation results
    """
    rules = DragonTigerRules(num_decks=num_decks, tie_push=tie_push)
    game = DragonTigerGame(rules=rules)

    total_wagered = 0
    total_won = 0
    net_earnings = 0

    dragon_wins = 0
    tiger_wins = 0
    ties = 0

    start_time = time.time()

    for _ in range(num_games):
        result, payout = game.play_round(bet_type, bet_amount)

        total_wagered += bet_amount
        if payout > 0:
            total_won += bet_amount + payout
        net_earnings += payout

        # Track outcomes
        if result.outcome == Outcome.DRAGON_WIN:
            dragon_wins += 1
        elif result.outcome == Outcome.TIGER_WIN:
            tiger_wins += 1
        else:
            ties += 1

    duration = time.time() - start_time
    house_edge = (-net_earnings / total_wagered) * 100 if total_wagered > 0 else 0

    results = {
        "num_games": num_games,
        "bet_type": bet_type.value,
        "total_wagered": total_wagered,
        "net_earnings": net_earnings,
        "house_edge": house_edge,
        "dragon_wins": dragon_wins,
        "tiger_wins": tiger_wins,
        "ties": ties,
        "duration": duration,
        "games_per_second": num_games / duration if duration > 0 else 0,
    }

    if verbose:
        print(f"\nDragon Tiger Simulation Results ({bet_type.value} bet)")
        print("=" * 60)
        print(f"Games played: {num_games:,}")
        print(f"Total wagered: ${total_wagered:,.2f}")
        print(f"Net earnings: ${net_earnings:,.2f}")
        print(f"House edge: {house_edge:.2f}%")
        print(f"\nOutcome Distribution:")
        print(f"  Dragon wins: {dragon_wins:,} ({dragon_wins / num_games * 100:.1f}%)")
        print(f"  Tiger wins: {tiger_wins:,} ({tiger_wins / num_games * 100:.1f}%)")
        print(f"  Ties: {ties:,} ({ties / num_games * 100:.1f}%)")
        print(f"\nDuration: {duration:.2f} seconds")
        print(f"Games per second: {results['games_per_second']:,.0f}")
        print("=" * 60)

    return results


def compare_bet_types(num_games: int = 10000, bet_amount: float = 10, tie_push: bool = False):
    """
    Compare all three bet types (Dragon, Tiger, Tie) to show house edges.

    Args:
        num_games: Number of games to simulate for each bet type
        bet_amount: Amount to bet per game
        tie_push: Whether Dragon/Tiger bets push on tie (vs losing)
    """
    print("\n" + "=" * 70)
    print("DRAGON TIGER BET TYPE COMPARISON")
    print("=" * 70)
    print(f"Simulating {num_games:,} games for each bet type...")
    print(f"Tie handling: {'Push' if tie_push else 'Lose'}")
    print()

    bet_types = [BetType.DRAGON, BetType.TIGER, BetType.TIE]
    results = {}

    for bet_type in bet_types:
        results[bet_type] = run_simulation(num_games, bet_type, bet_amount, tie_push=tie_push, verbose=False)

    # Display comparison table
    print(f"{'Bet Type':<10} {'House Edge':<12} {'Net Earnings':<15} {'Expected Payout'}")
    print("-" * 70)

    for bet_type in bet_types:
        r = results[bet_type]
        expected_payout = (r["total_wagered"] + r["net_earnings"]) / r["total_wagered"] * 100 - 100
        print(f"{bet_type.value.capitalize():<10} "
              f"{r['house_edge']:>10.2f}%  "
              f"${r['net_earnings']:>12,.2f}  "
              f"{expected_payout:>6.2f}%")

    print("-" * 70)
    print("\nKey Insights:")
    if tie_push:
        print(f"  • Dragon and Tiger bets have very low house edge (~3.2%)")
        print(f"  • Ties push your bet (return stake)")
    else:
        print(f"  • Dragon and Tiger bets have moderate house edge (~3.7%)")
        print(f"  • Ties lose your entire bet")
    print(f"  • Tie bet has very high house edge (~16-17%) - AVOID!")
    print(f"  • Dragon and Tiger are statistically equivalent")
    print("=" * 70)


def main():
    """Main CLI interface for Dragon Tiger simulation."""
    parser = argparse.ArgumentParser(
        description="Dragon Tiger Game Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 10,000 games with Dragon bets
  python dragon_tiger.py --simulate --num_games 10000 --bet dragon

  # Compare all bet types
  python dragon_tiger.py --compare

  # Test with tie-push rule (more player-friendly)
  python dragon_tiger.py --compare --tie_push
        """
    )

    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run simulation mode"
    )

    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare all bet types (Dragon, Tiger, Tie)"
    )

    parser.add_argument(
        "--num_games",
        type=int,
        default=10000,
        help="Number of games to simulate (default: 10000)"
    )

    parser.add_argument(
        "--bet",
        type=str,
        choices=["dragon", "tiger", "tie"],
        default="dragon",
        help="Bet type (default: dragon)"
    )

    parser.add_argument(
        "--bet_amount",
        type=float,
        default=10.0,
        help="Bet amount per game (default: 10)"
    )

    parser.add_argument(
        "--num_decks",
        type=int,
        default=8,
        help="Number of decks in shoe (default: 8)"
    )

    parser.add_argument(
        "--tie_push",
        action="store_true",
        help="Dragon/Tiger bets push on tie (instead of losing)"
    )

    args = parser.parse_args()

    if args.compare:
        compare_bet_types(args.num_games, args.bet_amount, args.tie_push)
    elif args.simulate:
        bet_type = BetType[args.bet.upper()]
        run_simulation(args.num_games, bet_type, args.bet_amount, args.num_decks, args.tie_push, verbose=True)
    else:
        # Default: show comparison
        compare_bet_types(args.num_games, args.bet_amount, args.tie_push)


if __name__ == "__main__":
    main()
