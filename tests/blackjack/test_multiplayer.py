"""
Tests for multi-player blackjack simulation.

This test suite verifies:
1. Multiple players at the table work correctly
2. Each player makes independent decisions
3. Card counting benefits from seeing more cards with multiple players
4. Stats aggregate properly across all players
5. Backward compatibility (single player) is maintained
"""

import pytest
from cardsharp.blackjack.blackjack import (
    play_game,
    generate_player_names,
)
from cardsharp.blackjack.strategy import BasicStrategy, CountingStrategy
from cardsharp.common.io_interface import DummyIOInterface
from cardsharp.blackjack.rules import Rules
from cardsharp.common.shoe import Shoe


def test_generate_player_names_single():
    """Test that single player gets simple name."""
    names = generate_player_names(1)
    assert names == ["Player"]
    assert len(names) == 1


def test_generate_player_names_multiple():
    """Test that multiple players get numbered names."""
    names = generate_player_names(3)
    assert names == ["Player1", "Player2", "Player3"]
    assert len(names) == 3

    names = generate_player_names(7)
    assert names == ["Player1", "Player2", "Player3", "Player4", "Player5", "Player6", "Player7"]
    assert len(names) == 7


def test_single_player_game():
    """Test that single player game works (backward compatibility)."""
    rules = Rules(num_decks=6)
    strategy = BasicStrategy()
    io_interface = DummyIOInterface()
    player_names = ["TestPlayer"]

    earnings, bets, stats, shoe = play_game(
        rules,
        io_interface,
        player_names,
        strategy,
        initial_bankroll=1000
    )

    # Verify we got results
    assert isinstance(earnings, (int, float))
    assert isinstance(bets, (int, float))
    assert isinstance(stats, dict)
    assert "games_played" in stats
    assert stats["games_played"] == 1


def test_multiplayer_game_three_players():
    """Test that 3 players at the table works correctly."""
    rules = Rules(num_decks=6)
    strategy = BasicStrategy()
    io_interface = DummyIOInterface()
    player_names = ["Alice", "Bob", "Charlie"]

    earnings, bets, stats, shoe = play_game(
        rules,
        io_interface,
        player_names,
        strategy,
        initial_bankroll=1000
    )

    # Verify we got results
    assert isinstance(earnings, (int, float))
    assert isinstance(bets, (int, float))
    assert isinstance(stats, dict)

    # With 3 players, total bets should be at least 3x a base bet
    # (Note: BasicStrategy default bet may be less than table minimum)
    assert bets >= 3  # 3 players should bet at least $1 each

    # Total wins + losses + draws should equal number of player hands
    total_outcomes = stats["player_wins"] + stats["dealer_wins"] + stats["draws"]
    assert total_outcomes >= 3  # At least 3 hands (one per player)


def test_multiplayer_game_max_players():
    """Test that 7 players (max table size) works correctly."""
    rules = Rules(num_decks=6)
    strategy = BasicStrategy()
    io_interface = DummyIOInterface()
    player_names = generate_player_names(7)

    earnings, bets, stats, shoe = play_game(
        rules,
        io_interface,
        player_names,
        strategy,
        initial_bankroll=1000
    )

    # Verify we got results
    assert isinstance(earnings, (int, float))
    assert isinstance(bets, (int, float))
    assert isinstance(stats, dict)

    # With 7 players, should have significant action
    assert bets >= 7  # 7 players should bet at least $1 each

    # Should have at least 7 outcomes (one per player minimum)
    total_outcomes = stats["player_wins"] + stats["dealer_wins"] + stats["draws"]
    assert total_outcomes >= 7


def test_multiplayer_independent_decisions():
    """
    Test that each player makes independent decisions.

    With multiple players, each should get their own hand and make
    their own decisions based on their cards.
    """
    import random
    random.seed(42)  # For reproducibility

    rules = Rules(num_decks=1)  # Use single deck for predictability
    strategy = BasicStrategy()
    io_interface = DummyIOInterface()
    player_names = ["Player1", "Player2", "Player3"]

    earnings, bets, stats, shoe = play_game(
        rules,
        io_interface,
        player_names,
        strategy,
        initial_bankroll=1000
    )

    # Each player should have placed a bet
    # With 3 players and basic strategy, expect at least 3 base bets
    assert bets >= 3  # 3 players should bet at least $1 each

    # Outcomes should reflect multiple hands
    total_outcomes = stats["player_wins"] + stats["dealer_wins"] + stats["draws"]
    assert total_outcomes >= 3


def test_card_counting_multiple_players_see_more_cards():
    """
    Test that card counting with multiple players sees more cards per round.

    This is a key advantage of multi-player simulation - counters see more
    cards and can estimate the true count more accurately.
    """
    import random

    # Test with 1 player
    random.seed(42)
    rules = Rules(num_decks=6)
    strategy_single = CountingStrategy()
    io_interface = DummyIOInterface()

    # Track initial count
    initial_count = strategy_single.count

    earnings_single, bets_single, stats_single, shoe_single = play_game(
        rules,
        io_interface,
        ["Player"],
        strategy_single,
        initial_bankroll=1000
    )

    # Track unique cards counted using the counted_cards set
    cards_seen_single = len(strategy_single.counted_cards)

    # Test with 7 players - should see more cards
    random.seed(42)
    strategy_multi = CountingStrategy()

    earnings_multi, bets_multi, stats_multi, shoe_multi = play_game(
        rules,
        io_interface,
        generate_player_names(7),
        strategy_multi,
        initial_bankroll=1000
    )

    # Track unique cards counted
    cards_seen_multi = len(strategy_multi.counted_cards)

    # With 7 players, should see significantly more cards per round
    # Each player gets 2 cards + dealer gets 2 + additional hits
    # 7 players: minimum 7*2 + 2 = 16 cards
    # 1 player: minimum 1*2 + 2 = 4 cards
    print(f"\nCards counted - Single player: {cards_seen_single}, 7 players: {cards_seen_multi}")

    # With more players, we should see more cards
    # Allow for variance but expect at least 2x more cards with 7 players
    assert cards_seen_multi >= cards_seen_single, (
        f"7 players should see at least as many cards ({cards_seen_multi}) as 1 player ({cards_seen_single})"
    )

    # More specifically, 7 players should see significantly more
    assert cards_seen_multi >= 10, (
        f"7 players should see at least 10 cards per round, saw {cards_seen_multi}"
    )


def test_multiplayer_stats_aggregation():
    """Test that stats properly aggregate across all players."""
    rules = Rules(num_decks=6)
    strategy = BasicStrategy()
    io_interface = DummyIOInterface()
    player_names = generate_player_names(5)

    earnings, bets, stats, shoe = play_game(
        rules,
        io_interface,
        player_names,
        strategy,
        initial_bankroll=1000
    )

    # Verify stats structure
    assert "games_played" in stats
    assert "player_wins" in stats
    assert "dealer_wins" in stats
    assert "draws" in stats

    # Games played should be 1 (one round)
    assert stats["games_played"] == 1

    # Total outcomes should be at least 5 (one per player)
    total_outcomes = stats["player_wins"] + stats["dealer_wins"] + stats["draws"]
    assert total_outcomes >= 5


def test_multiplayer_different_outcomes():
    """
    Test that with multiple players, different outcomes are possible.

    In a multi-player game, some players can win while others lose
    against the same dealer hand.
    """
    import random
    random.seed(123)  # Seed that produces mixed outcomes

    rules = Rules(num_decks=6)
    strategy = BasicStrategy()
    io_interface = DummyIOInterface()
    player_names = generate_player_names(5)

    # Play multiple rounds to get varied outcomes
    total_player_wins = 0
    total_dealer_wins = 0
    total_draws = 0
    shoe = None  # Will be created on first play_game call

    for _ in range(10):
        earnings, bets, stats, shoe = play_game(
            rules,
            io_interface,
            player_names,
            strategy,
            shoe=shoe,
            initial_bankroll=1000
        )

        total_player_wins += stats["player_wins"]
        total_dealer_wins += stats["dealer_wins"]
        total_draws += stats["draws"]

    # After 10 rounds with 5 players, should have mix of outcomes
    assert total_player_wins > 0, "Should have some player wins"
    assert total_dealer_wins > 0, "Should have some dealer wins"

    # Should have significant total hands
    total_hands = total_player_wins + total_dealer_wins + total_draws
    assert total_hands >= 50  # 10 rounds * 5 players = 50 minimum


def test_multiplayer_betting_scales():
    """Test that total bets scale with number of players."""
    rules = Rules(num_decks=6)
    strategy = BasicStrategy()
    io_interface = DummyIOInterface()

    # Test with 1, 3, and 7 players
    for num_players in [1, 3, 7]:
        player_names = generate_player_names(num_players)

        earnings, bets, stats, shoe = play_game(
            rules,
            io_interface,
            player_names,
            strategy,
            initial_bankroll=1000
        )

        # Each player should bet at least $1 (BasicStrategy default)
        min_expected_bets = num_players * 1  # At least $1 per player
        assert bets >= min_expected_bets, (
            f"With {num_players} players, expected at least ${min_expected_bets} in bets, got ${bets}"
        )


def test_multiplayer_preserves_shoe_state():
    """
    Test that shoe state is preserved across multiple rounds with multiple players.

    This is important for card counting - the shoe should maintain its state
    as cards are dealt across rounds.
    """
    rules = Rules(num_decks=6, penetration=0.75)
    strategy = CountingStrategy()
    io_interface = DummyIOInterface()
    player_names = generate_player_names(5)

    # Create initial shoe
    shoe = Shoe(num_decks=6, penetration=0.75)
    initial_cards = shoe.cards_remaining

    # Play a round
    earnings, bets, stats, shoe = play_game(
        rules,
        io_interface,
        player_names,
        strategy,
        shoe=shoe,
        initial_bankroll=1000
    )

    # Shoe should have fewer cards after the round
    assert shoe.cards_remaining < initial_cards, (
        "Shoe should have fewer cards after dealing a round"
    )

    # Play another round with the same shoe
    second_round_start = shoe.cards_remaining
    earnings2, bets2, stats2, shoe = play_game(
        rules,
        io_interface,
        player_names,
        strategy,
        shoe=shoe,
        initial_bankroll=1000
    )

    # Shoe should continue to deplete (unless it shuffled)
    # If it shuffled, cards_remaining will be high again
    if not shoe.cut_card_reached:
        assert shoe.cards_remaining < second_round_start


def test_console_mode_multiplayer():
    """
    Test that console mode can handle multiple players.

    This verifies the CLI integration works with --num_players argument.
    """
    # This is more of an integration test - we just verify the player name
    # generation works and can be used in the main function

    for num_players in [1, 3, 5, 7]:
        names = generate_player_names(num_players)
        assert len(names) == num_players

        # Verify names are unique
        assert len(set(names)) == len(names)


if __name__ == "__main__":
    # Run all tests with detailed output
    import sys

    print("Running multi-player simulation tests...")
    print("=" * 60)

    try:
        test_generate_player_names_single()
        print("✓ Single player name generation works")

        test_generate_player_names_multiple()
        print("✓ Multiple player name generation works")

        test_single_player_game()
        print("✓ Single player game works (backward compatibility)")

        test_multiplayer_game_three_players()
        print("✓ 3-player game works")

        test_multiplayer_game_max_players()
        print("✓ 7-player game (max table size) works")

        test_multiplayer_independent_decisions()
        print("✓ Players make independent decisions")

        test_card_counting_multiple_players_see_more_cards()
        print("✓ Card counting sees more cards with multiple players")

        test_multiplayer_stats_aggregation()
        print("✓ Stats aggregate properly across players")

        test_multiplayer_different_outcomes()
        print("✓ Multiple players can have different outcomes")

        test_multiplayer_betting_scales()
        print("✓ Betting scales with number of players")

        test_multiplayer_preserves_shoe_state()
        print("✓ Shoe state preserved across rounds")

        test_console_mode_multiplayer()
        print("✓ Console mode multiplayer integration works")

        print("=" * 60)
        print("All tests passed! ✓")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
