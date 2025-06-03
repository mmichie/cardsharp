#!/usr/bin/env python3
"""Profile blackjack simulation to identify performance bottlenecks."""

import cProfile
import pstats
import io
from cardsharp.blackjack.blackjack import play_game, play_game_batch
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.common.io_interface import DummyIOInterface
from cardsharp.common.shoe import Shoe


def profile_single_game():
    """Profile a single game execution."""
    rules = Rules(
        blackjack_payout=1.5,
        dealer_hit_soft_17=False,
        dealer_peek=True,
        allow_split=True,
        allow_double_down=True,
        allow_double_after_split=True,
        allow_insurance=True,
        allow_surrender=True,
        num_decks=6,
        min_bet=10,
        max_bet=1000,
        insurance_payout=2.0,
        allow_resplitting=False,
        allow_late_surrender=False,
        allow_early_surrender=False,
        use_csm=False,
        time_limit=0,
        max_splits=3,
        bonus_payouts={},
    )

    io_interface = DummyIOInterface()
    strategy = BasicStrategy()
    shoe = Shoe(num_decks=6, penetration=0.75, use_csm=False)

    # Profile single game
    profiler = cProfile.Profile()
    profiler.enable()

    for _ in range(1000):  # Run 1000 games to get meaningful data
        net_earnings, total_bets, stats, shoe = play_game(
            rules, io_interface, ["Player1"], strategy, shoe
        )

    profiler.disable()

    # Print statistics
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
    ps.print_stats(50)  # Top 50 functions
    print(s.getvalue())

    # Also print by total time
    print("\n\n=== BY TOTAL TIME ===\n")
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats("tottime")
    ps.print_stats(30)  # Top 30 functions
    print(s.getvalue())


def profile_batch_games():
    """Profile batch game execution."""
    rules = Rules(
        blackjack_payout=1.5,
        dealer_hit_soft_17=False,
        dealer_peek=True,
        allow_split=True,
        allow_double_down=True,
        allow_double_after_split=True,
        allow_insurance=True,
        allow_surrender=True,
        num_decks=6,
        min_bet=10,
        max_bet=1000,
        insurance_payout=2.0,
        allow_resplitting=False,
        allow_late_surrender=False,
        allow_early_surrender=False,
        use_csm=False,
        time_limit=0,
        max_splits=3,
        bonus_payouts={},
    )

    io_interface = DummyIOInterface()
    strategy = BasicStrategy()

    # Profile batch execution
    profiler = cProfile.Profile()
    profiler.enable()

    results, earnings, total_bets = play_game_batch(
        rules, io_interface, ["Player1"], 1000, strategy
    )

    profiler.disable()

    # Print statistics
    print("\n\n=== BATCH GAME PROFILING ===\n")
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
    ps.print_stats(50)  # Top 50 functions
    print(s.getvalue())


if __name__ == "__main__":
    print("Profiling single game execution...")
    profile_single_game()

    print("\n\n" + "=" * 80 + "\n\n")

    print("Profiling batch game execution...")
    profile_batch_games()
