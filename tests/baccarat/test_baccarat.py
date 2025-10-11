"""
Comprehensive tests for Baccarat implementation.

Tests cover:
- Hand value calculation (modulo 10)
- Natural detection
- Player drawing rules
- Banker drawing rules (complex table)
- Game flow
- Payouts and commissions
- Statistics tracking
"""

import pytest
from cardsharp.baccarat import (
    BaccaratGame,
    BaccaratHand,
    BaccaratRules,
    BetType,
    Outcome
)
from cardsharp.baccarat.rules import player_draws_third_card, banker_draws_third_card
from cardsharp.common.card import Card, Rank, Suit
from cardsharp.common.shoe import Shoe


class TestBaccaratHand:
    """Tests for BaccaratHand value calculation."""

    def test_empty_hand(self):
        """Test that empty hand has value 0."""
        hand = BaccaratHand()
        assert hand.value() == 0
        assert hand.card_count() == 0

    def test_single_digit_values(self):
        """Test hands with single-digit totals."""
        hand = BaccaratHand()
        hand.add_card(Card(Suit.HEARTS, Rank.TWO))
        hand.add_card(Card(Suit.SPADES, Rank.THREE))
        assert hand.value() == 5

    def test_modulo_10_calculation(self):
        """Test that values wrap at 10 (modulo 10)."""
        # 17 should become 7
        hand = BaccaratHand()
        hand.add_card(Card(Suit.HEARTS, Rank.NINE))
        hand.add_card(Card(Suit.SPADES, Rank.EIGHT))
        assert hand.value() == 7  # 17 % 10 = 7

        # 20 should become 0
        hand2 = BaccaratHand()
        hand2.add_card(Card(Suit.HEARTS, Rank.TEN))
        hand2.add_card(Card(Suit.SPADES, Rank.KING))
        assert hand2.value() == 0  # 0 + 0 = 0

    def test_face_cards_worth_zero(self):
        """Test that 10, J, Q, K are worth 0."""
        for rank in [Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING]:
            hand = BaccaratHand()
            hand.add_card(Card(Suit.HEARTS, rank))
            hand.add_card(Card(Suit.SPADES, Rank.FIVE))
            assert hand.value() == 5  # 0 + 5 = 5

    def test_ace_worth_one(self):
        """Test that Aces are worth 1."""
        hand = BaccaratHand()
        hand.add_card(Card(Suit.HEARTS, Rank.ACE))
        hand.add_card(Card(Suit.SPADES, Rank.FOUR))
        assert hand.value() == 5  # 1 + 4 = 5

    def test_natural_eight(self):
        """Test natural 8 detection."""
        hand = BaccaratHand()
        hand.add_card(Card(Suit.HEARTS, Rank.THREE))
        hand.add_card(Card(Suit.SPADES, Rank.FIVE))
        assert hand.value() == 8
        assert hand.is_natural()

    def test_natural_nine(self):
        """Test natural 9 detection."""
        hand = BaccaratHand()
        hand.add_card(Card(Suit.HEARTS, Rank.FOUR))
        hand.add_card(Card(Suit.SPADES, Rank.FIVE))
        assert hand.value() == 9
        assert hand.is_natural()

    def test_not_natural_with_three_cards(self):
        """Test that three-card hands are never natural."""
        hand = BaccaratHand()
        hand.add_card(Card(Suit.HEARTS, Rank.FOUR))
        hand.add_card(Card(Suit.SPADES, Rank.FOUR))
        hand.add_card(Card(Suit.DIAMONDS, Rank.ACE))
        assert hand.value() == 9
        assert not hand.is_natural()  # Only first two cards count for natural

    def test_third_card_value(self):
        """Test getting value of third card."""
        hand = BaccaratHand()
        hand.add_card(Card(Suit.HEARTS, Rank.TWO))
        hand.add_card(Card(Suit.SPADES, Rank.THREE))

        # No third card yet
        assert hand.third_card_value() == -1

        # Add third card
        hand.add_card(Card(Suit.DIAMONDS, Rank.SEVEN))
        assert hand.third_card_value() == 7


class TestDrawingRules:
    """Tests for Player and Banker drawing rules."""

    def test_player_draws_on_0_through_5(self):
        """Test that Player draws on 0-5."""
        for value in range(6):
            assert player_draws_third_card(value), f"Player should draw on {value}"

    def test_player_stands_on_6_and_7(self):
        """Test that Player stands on 6-7."""
        for value in [6, 7]:
            assert not player_draws_third_card(value), f"Player should stand on {value}"

    def test_banker_draws_without_player_third_card(self):
        """Test Banker drawing when Player doesn't draw."""
        # Banker draws on 0-5 when Player doesn't draw
        for value in range(6):
            assert banker_draws_third_card(value, player_drew=False, player_third_card=-1)

        # Banker stands on 6-7 when Player doesn't draw
        for value in [6, 7]:
            assert not banker_draws_third_card(value, player_drew=False, player_third_card=-1)

    def test_banker_draws_on_0_1_2_always(self):
        """Test that Banker always draws on 0-2 regardless of Player's third card."""
        for banker_value in [0, 1, 2]:
            for player_third in range(10):
                assert banker_draws_third_card(banker_value, True, player_third), \
                    f"Banker {banker_value} should draw against Player third card {player_third}"

    def test_banker_3_draws_except_player_8(self):
        """Test Banker 3 draws except when Player's third card is 8."""
        # Draws on all except 8
        for player_third in [0, 1, 2, 3, 4, 5, 6, 7, 9]:
            assert banker_draws_third_card(3, True, player_third), \
                f"Banker 3 should draw against Player {player_third}"

        # Stands on Player 8
        assert not banker_draws_third_card(3, True, 8)

    def test_banker_4_draws_on_player_2_through_7(self):
        """Test Banker 4 draws only on Player 2-7."""
        # Draws on 2-7
        for player_third in [2, 3, 4, 5, 6, 7]:
            assert banker_draws_third_card(4, True, player_third), \
                f"Banker 4 should draw against Player {player_third}"

        # Stands on 0, 1, 8, 9
        for player_third in [0, 1, 8, 9]:
            assert not banker_draws_third_card(4, True, player_third), \
                f"Banker 4 should stand against Player {player_third}"

    def test_banker_5_draws_on_player_4_through_7(self):
        """Test Banker 5 draws only on Player 4-7."""
        # Draws on 4-7
        for player_third in [4, 5, 6, 7]:
            assert banker_draws_third_card(5, True, player_third), \
                f"Banker 5 should draw against Player {player_third}"

        # Stands on 0-3, 8-9
        for player_third in [0, 1, 2, 3, 8, 9]:
            assert not banker_draws_third_card(5, True, player_third), \
                f"Banker 5 should stand against Player {player_third}"

    def test_banker_6_draws_on_player_6_and_7(self):
        """Test Banker 6 draws only on Player 6-7."""
        # Draws on 6-7
        for player_third in [6, 7]:
            assert banker_draws_third_card(6, True, player_third), \
                f"Banker 6 should draw against Player {player_third}"

        # Stands on 0-5, 8-9
        for player_third in [0, 1, 2, 3, 4, 5, 8, 9]:
            assert not banker_draws_third_card(6, True, player_third), \
                f"Banker 6 should stand against Player {player_third}"

    def test_banker_7_always_stands(self):
        """Test that Banker always stands on 7."""
        for player_third in range(10):
            assert not banker_draws_third_card(7, True, player_third), \
                f"Banker 7 should stand against Player {player_third}"


class TestBaccaratGame:
    """Tests for complete game flow."""

    def test_game_initialization(self):
        """Test game initializes correctly."""
        game = BaccaratGame()
        assert game.rounds_played == 0
        assert game.player_wins == 0
        assert game.banker_wins == 0
        assert game.ties == 0

    def test_play_single_round(self):
        """Test playing a single round."""
        game = BaccaratGame()
        result, payout = game.play_round(BetType.BANKER, 10)

        assert game.rounds_played == 1
        assert result.outcome in [Outcome.PLAYER_WIN, Outcome.BANKER_WIN, Outcome.TIE]
        assert isinstance(payout, (int, float))

    def test_natural_stops_drawing(self):
        """Test that naturals prevent further drawing."""
        import random
        random.seed(42)

        game = BaccaratGame()
        # Play rounds until we get a natural
        found_natural = False
        for _ in range(100):
            result, _ = game.play_round()
            if result.player_natural or result.banker_natural:
                found_natural = True
                # With a natural, at most 2 cards per hand
                assert result.player_cards == 2
                assert result.banker_cards == 2
                break

        assert found_natural, "Should find at least one natural in 100 rounds"

    def test_player_win_payout(self):
        """Test Player bet payout (1:1)."""
        rules = BaccaratRules()
        game = BaccaratGame(rules)

        # Player bet wins 1:1
        payout = game.calculate_payout(BetType.PLAYER, 100, Outcome.PLAYER_WIN)
        assert payout == 100

        # Player bet loses
        payout = game.calculate_payout(BetType.PLAYER, 100, Outcome.BANKER_WIN)
        assert payout == -100

        # Player bet pushes on tie
        payout = game.calculate_payout(BetType.PLAYER, 100, Outcome.TIE)
        assert payout == 0

    def test_banker_win_payout_with_commission(self):
        """Test Banker bet payout (1:1 minus 5% commission)."""
        rules = BaccaratRules(banker_commission=0.05)
        game = BaccaratGame(rules)

        # Banker bet wins 1:1 minus 5%
        payout = game.calculate_payout(BetType.BANKER, 100, Outcome.BANKER_WIN)
        assert payout == 95  # 100 * (1 - 0.05) = 95

        # Banker bet loses
        payout = game.calculate_payout(BetType.BANKER, 100, Outcome.PLAYER_WIN)
        assert payout == -100

        # Banker bet pushes on tie
        payout = game.calculate_payout(BetType.BANKER, 100, Outcome.TIE)
        assert payout == 0

    def test_tie_bet_payout(self):
        """Test Tie bet payout (8:1)."""
        rules = BaccaratRules(tie_payout=8.0)
        game = BaccaratGame(rules)

        # Tie bet wins 8:1
        payout = game.calculate_payout(BetType.TIE, 100, Outcome.TIE)
        assert payout == 800

        # Tie bet loses on Player win
        payout = game.calculate_payout(BetType.TIE, 100, Outcome.PLAYER_WIN)
        assert payout == -100

        # Tie bet loses on Banker win
        payout = game.calculate_payout(BetType.TIE, 100, Outcome.BANKER_WIN)
        assert payout == -100

    def test_statistics_tracking(self):
        """Test that statistics are tracked correctly."""
        import random
        random.seed(42)

        game = BaccaratGame()

        # Play 100 rounds
        for _ in range(100):
            game.play_round(BetType.BANKER, 10)

        stats = game.get_statistics()

        assert stats["rounds_played"] == 100
        assert stats["player_wins"] + stats["banker_wins"] + stats["ties"] == 100
        assert 0 <= stats["player_win_rate"] <= 1
        assert 0 <= stats["banker_win_rate"] <= 1
        assert 0 <= stats["tie_rate"] <= 1

    def test_banker_wins_more_often(self):
        """Test that Banker wins slightly more often than Player (as expected)."""
        import random

        # Test with multiple seeds to get statistical average
        total_banker_wins = 0
        total_player_wins = 0

        for seed in [42, 123, 456]:
            random.seed(seed)
            game = BaccaratGame()

            # Play many rounds to see statistical trend
            for _ in range(1000):
                game.play_round(BetType.BANKER, 10)

            stats = game.get_statistics()
            total_banker_wins += stats["banker_wins"]
            total_player_wins += stats["player_wins"]

        # Banker should win more often than Player over many games
        # (historically ~50.68% vs ~49.32% of decisive hands)
        # We use lenient check since even 3000 rounds can have variance
        assert total_banker_wins >= total_player_wins * 0.95, \
            f"Banker should win approximately as often or more than Player over many hands (B:{total_banker_wins} vs P:{total_player_wins})"

    def test_tie_rate_approximately_correct(self):
        """Test that tie rate is approximately 9.5% (historical average)."""
        import random
        random.seed(42)

        game = BaccaratGame()

        # Play many rounds
        for _ in range(1000):
            game.play_round()

        stats = game.get_statistics()

        # Ties should be around 9.5% (we allow 5% - 15% due to variance)
        assert 0.05 <= stats["tie_rate"] <= 0.15, \
            f"Tie rate should be around 9.5%, got {stats['tie_rate']:.1%}"

    def test_shoe_integration(self):
        """Test that game works with custom shoe."""
        shoe = Shoe(num_decks=6, penetration=0.75)
        game = BaccaratGame(shoe=shoe)

        initial_cards = shoe.cards_remaining

        # Play a round
        game.play_round()

        # Shoe should have fewer cards
        assert shoe.cards_remaining < initial_cards

    def test_multiple_rounds_with_same_shoe(self):
        """Test playing multiple rounds with the same shoe."""
        shoe = Shoe(num_decks=6, penetration=0.75)
        game = BaccaratGame(shoe=shoe)

        # Play 50 rounds
        for _ in range(50):
            game.play_round()

        assert game.rounds_played == 50
        # Shoe should eventually shuffle
        assert game.shoe.cards_remaining < shoe.total_cards


def test_complete_simulation():
    """Integration test: run complete simulation."""
    import random
    random.seed(12345)

    game = BaccaratGame()
    results = {
        BetType.PLAYER: {"wins": 0, "losses": 0, "net": 0},
        BetType.BANKER: {"wins": 0, "losses": 0, "net": 0},
        BetType.TIE: {"wins": 0, "losses": 0, "net": 0},
    }

    # Simulate 1000 rounds with each bet type
    for bet_type in [BetType.PLAYER, BetType.BANKER, BetType.TIE]:
        game = BaccaratGame()  # Fresh game for each bet type
        for _ in range(1000):
            result, payout = game.play_round(bet_type, 10)
            if payout > 0:
                results[bet_type]["wins"] += 1
            elif payout < 0:
                results[bet_type]["losses"] += 1
            results[bet_type]["net"] += payout

    # Banker should perform best (lowest house edge ~1.06%)
    # Player should be second (~1.24%)
    # Tie should lose money (huge house edge ~14.4%)
    assert results[BetType.TIE]["net"] < results[BetType.PLAYER]["net"], \
        "Tie bets should lose more money than Player bets"
    assert results[BetType.TIE]["net"] < results[BetType.BANKER]["net"], \
        "Tie bets should lose more money than Banker bets"

    print("\nSimulation Results (1000 rounds each):")
    for bet_type in [BetType.PLAYER, BetType.BANKER, BetType.TIE]:
        net = results[bet_type]["net"]
        house_edge = -net / 10000 * 100  # Total wagered: 1000 * $10
        print(f"{bet_type.value:6s}: Net ${net:6.0f}, House Edge: {house_edge:5.2f}%")


if __name__ == "__main__":
    # Run all tests
    import sys

    print("Running Baccarat tests...")
    print("=" * 60)

    pytest.main([__file__, "-v", "--tb=short"])
