"""
Comprehensive tests for Dragon Tiger implementation.

Tests cover:
- Card value calculation
- Outcome determination
- Game flow
- Payouts for all bet types
- Statistics tracking
- Tie handling rules
"""

import pytest
from cardsharp.dragon_tiger import (
    DragonTigerGame,
    DragonTigerRules,
    BetType,
    Outcome,
    card_value,
)
from cardsharp.common.card import Card, Rank, Suit
from cardsharp.common.shoe import Shoe


class TestCardValue:
    """Tests for card value calculation."""

    def test_ace_is_one(self):
        """Test that Ace has value 1 (lowest)."""
        card = Card(Suit.HEARTS, Rank.ACE)
        assert card_value(card) == 1

    def test_number_cards(self):
        """Test that number cards have face value."""
        assert card_value(Card(Suit.HEARTS, Rank.TWO)) == 2
        assert card_value(Card(Suit.SPADES, Rank.FIVE)) == 5
        assert card_value(Card(Suit.DIAMONDS, Rank.NINE)) == 9
        assert card_value(Card(Suit.CLUBS, Rank.TEN)) == 10

    def test_face_cards(self):
        """Test that face cards have values 11-13."""
        assert card_value(Card(Suit.HEARTS, Rank.JACK)) == 11
        assert card_value(Card(Suit.SPADES, Rank.QUEEN)) == 12
        assert card_value(Card(Suit.DIAMONDS, Rank.KING)) == 13

    def test_all_ranks_have_values(self):
        """Test that all ranks produce valid values 1-13."""
        ranks = [
            Rank.ACE, Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE,
            Rank.SIX, Rank.SEVEN, Rank.EIGHT, Rank.NINE, Rank.TEN,
            Rank.JACK, Rank.QUEEN, Rank.KING
        ]
        for rank in ranks:
            card = Card(Suit.HEARTS, rank)
            value = card_value(card)
            assert 1 <= value <= 13, f"{rank} should have value 1-13, got {value}"


class TestOutcomeDetermination:
    """Tests for determining game outcomes."""

    def test_dragon_wins_higher_card(self):
        """Test Dragon wins when Dragon card is higher."""
        game = DragonTigerGame()
        dragon_card = Card(Suit.HEARTS, Rank.KING)  # 13
        tiger_card = Card(Suit.SPADES, Rank.FIVE)   # 5
        outcome = game.determine_outcome(dragon_card, tiger_card)
        assert outcome == Outcome.DRAGON_WIN

    def test_tiger_wins_higher_card(self):
        """Test Tiger wins when Tiger card is higher."""
        game = DragonTigerGame()
        dragon_card = Card(Suit.HEARTS, Rank.THREE)  # 3
        tiger_card = Card(Suit.SPADES, Rank.QUEEN)   # 12
        outcome = game.determine_outcome(dragon_card, tiger_card)
        assert outcome == Outcome.TIGER_WIN

    def test_tie_equal_cards(self):
        """Test Tie when cards have equal value."""
        game = DragonTigerGame()
        dragon_card = Card(Suit.HEARTS, Rank.SEVEN)
        tiger_card = Card(Suit.SPADES, Rank.SEVEN)
        outcome = game.determine_outcome(dragon_card, tiger_card)
        assert outcome == Outcome.TIE

    def test_tie_different_suits_same_rank(self):
        """Test that different suits with same rank is a tie."""
        game = DragonTigerGame()
        dragon_card = Card(Suit.HEARTS, Rank.ACE)
        tiger_card = Card(Suit.CLUBS, Rank.ACE)
        outcome = game.determine_outcome(dragon_card, tiger_card)
        assert outcome == Outcome.TIE


class TestPayouts:
    """Tests for payout calculations."""

    def test_dragon_bet_wins(self):
        """Test Dragon bet pays 1:1 on Dragon win."""
        game = DragonTigerGame()
        payout = game.calculate_payout(BetType.DRAGON, 100, Outcome.DRAGON_WIN)
        assert payout == 100

    def test_dragon_bet_loses(self):
        """Test Dragon bet loses on Tiger win."""
        game = DragonTigerGame()
        payout = game.calculate_payout(BetType.DRAGON, 100, Outcome.TIGER_WIN)
        assert payout == -100

    def test_dragon_bet_tie_loses(self):
        """Test Dragon bet loses on Tie (default rule)."""
        rules = DragonTigerRules(tie_push=False)
        game = DragonTigerGame(rules)
        payout = game.calculate_payout(BetType.DRAGON, 100, Outcome.TIE)
        assert payout == -100

    def test_dragon_bet_tie_pushes(self):
        """Test Dragon bet pushes on Tie (optional rule)."""
        rules = DragonTigerRules(tie_push=True)
        game = DragonTigerGame(rules)
        payout = game.calculate_payout(BetType.DRAGON, 100, Outcome.TIE)
        assert payout == 0

    def test_tiger_bet_wins(self):
        """Test Tiger bet pays 1:1 on Tiger win."""
        game = DragonTigerGame()
        payout = game.calculate_payout(BetType.TIGER, 100, Outcome.TIGER_WIN)
        assert payout == 100

    def test_tiger_bet_loses(self):
        """Test Tiger bet loses on Dragon win."""
        game = DragonTigerGame()
        payout = game.calculate_payout(BetType.TIGER, 100, Outcome.DRAGON_WIN)
        assert payout == -100

    def test_tiger_bet_tie_loses(self):
        """Test Tiger bet loses on Tie (default rule)."""
        rules = DragonTigerRules(tie_push=False)
        game = DragonTigerGame(rules)
        payout = game.calculate_payout(BetType.TIGER, 100, Outcome.TIE)
        assert payout == -100

    def test_tiger_bet_tie_pushes(self):
        """Test Tiger bet pushes on Tie (optional rule)."""
        rules = DragonTigerRules(tie_push=True)
        game = DragonTigerGame(rules)
        payout = game.calculate_payout(BetType.TIGER, 100, Outcome.TIE)
        assert payout == 0

    def test_tie_bet_wins_8to1(self):
        """Test Tie bet pays 8:1 on Tie."""
        rules = DragonTigerRules(tie_payout=8.0)
        game = DragonTigerGame(rules)
        payout = game.calculate_payout(BetType.TIE, 100, Outcome.TIE)
        assert payout == 800

    def test_tie_bet_wins_11to1(self):
        """Test Tie bet pays 11:1 on Tie (alternative payout)."""
        rules = DragonTigerRules(tie_payout=11.0)
        game = DragonTigerGame(rules)
        payout = game.calculate_payout(BetType.TIE, 100, Outcome.TIE)
        assert payout == 1100

    def test_tie_bet_loses_on_dragon(self):
        """Test Tie bet loses on Dragon win."""
        game = DragonTigerGame()
        payout = game.calculate_payout(BetType.TIE, 100, Outcome.DRAGON_WIN)
        assert payout == -100

    def test_tie_bet_loses_on_tiger(self):
        """Test Tie bet loses on Tiger win."""
        game = DragonTigerGame()
        payout = game.calculate_payout(BetType.TIE, 100, Outcome.TIGER_WIN)
        assert payout == -100


class TestGameFlow:
    """Tests for complete game flow."""

    def test_game_initialization(self):
        """Test game initializes correctly."""
        game = DragonTigerGame()
        assert game.rounds_played == 0
        assert game.dragon_wins == 0
        assert game.tiger_wins == 0
        assert game.ties == 0

    def test_play_single_round(self):
        """Test playing a single round."""
        game = DragonTigerGame()
        result, payout = game.play_round(BetType.DRAGON, 10)

        assert game.rounds_played == 1
        assert result.outcome in [Outcome.DRAGON_WIN, Outcome.TIGER_WIN, Outcome.TIE]
        assert isinstance(payout, (int, float))
        assert isinstance(result.dragon_card, Card)
        assert isinstance(result.tiger_card, Card)

    def test_multiple_rounds(self):
        """Test playing multiple rounds."""
        game = DragonTigerGame()

        for _ in range(100):
            game.play_round(BetType.DRAGON, 10)

        assert game.rounds_played == 100
        assert game.dragon_wins + game.tiger_wins + game.ties == 100

    def test_result_contains_cards(self):
        """Test that result contains both cards dealt."""
        game = DragonTigerGame()
        result, _ = game.play_round()

        assert result.dragon_card is not None
        assert result.tiger_card is not None
        assert result.dragon_value == card_value(result.dragon_card)
        assert result.tiger_value == card_value(result.tiger_card)

    def test_outcome_matches_card_values(self):
        """Test that outcome correctly reflects card values."""
        game = DragonTigerGame()

        for _ in range(50):
            result, _ = game.play_round()

            if result.dragon_value > result.tiger_value:
                assert result.outcome == Outcome.DRAGON_WIN
            elif result.tiger_value > result.dragon_value:
                assert result.outcome == Outcome.TIGER_WIN
            else:
                assert result.outcome == Outcome.TIE


class TestStatistics:
    """Tests for statistics tracking."""

    def test_statistics_tracking(self):
        """Test that statistics are tracked correctly."""
        import random
        random.seed(42)

        game = DragonTigerGame()

        # Play 100 rounds
        for _ in range(100):
            game.play_round(BetType.DRAGON, 10)

        stats = game.get_statistics()

        assert stats["rounds_played"] == 100
        assert stats["dragon_wins"] + stats["tiger_wins"] + stats["ties"] == 100
        assert 0 <= stats["dragon_win_rate"] <= 1
        assert 0 <= stats["tiger_win_rate"] <= 1
        assert 0 <= stats["tie_rate"] <= 1

    def test_dragon_tiger_roughly_equal(self):
        """Test that Dragon and Tiger win roughly equally over many games."""
        import random

        total_dragon = 0
        total_tiger = 0

        # Test with multiple seeds
        for seed in [42, 123, 456, 789]:
            random.seed(seed)
            game = DragonTigerGame()

            for _ in range(1000):
                game.play_round()

            stats = game.get_statistics()
            total_dragon += stats["dragon_wins"]
            total_tiger += stats["tiger_wins"]

        # Over 4000 games, Dragon and Tiger should be within 10% of each other
        ratio = total_dragon / total_tiger if total_tiger > 0 else 0
        assert 0.9 <= ratio <= 1.1, \
            f"Dragon and Tiger should win roughly equally (D:{total_dragon} vs T:{total_tiger})"

    def test_tie_rate_approximately_correct(self):
        """Test that tie rate is approximately 7.7% (1/13)."""
        import random
        random.seed(42)

        game = DragonTigerGame()

        # Play many rounds
        for _ in range(2000):
            game.play_round()

        stats = game.get_statistics()

        # Ties should be around 7.7% (we allow 5% - 12% due to variance)
        assert 0.05 <= stats["tie_rate"] <= 0.12, \
            f"Tie rate should be around 7.7%, got {stats['tie_rate']:.1%}"


class TestShoeIntegration:
    """Tests for shoe integration."""

    def test_shoe_integration(self):
        """Test that game works with custom shoe."""
        shoe = Shoe(num_decks=6, penetration=0.75)
        game = DragonTigerGame(shoe=shoe)

        initial_cards = shoe.cards_remaining

        # Play a round
        game.play_round()

        # Shoe should have 2 fewer cards
        assert shoe.cards_remaining == initial_cards - 2

    def test_multiple_rounds_with_shoe(self):
        """Test playing multiple rounds with the same shoe."""
        shoe = Shoe(num_decks=6, penetration=0.75)
        game = DragonTigerGame(shoe=shoe)

        # Play 50 rounds (100 cards)
        for _ in range(50):
            game.play_round()

        assert game.rounds_played == 50


def test_complete_simulation():
    """Integration test: run complete simulation."""
    import random
    random.seed(12345)

    results = {
        BetType.DRAGON: {"wins": 0, "losses": 0, "net": 0},
        BetType.TIGER: {"wins": 0, "losses": 0, "net": 0},
        BetType.TIE: {"wins": 0, "losses": 0, "net": 0},
    }

    # Simulate 1000 rounds with each bet type
    for bet_type in [BetType.DRAGON, BetType.TIGER, BetType.TIE]:
        game = DragonTigerGame()  # Fresh game for each bet type
        for _ in range(1000):
            result, payout = game.play_round(bet_type, 10)
            if payout > 0:
                results[bet_type]["wins"] += 1
            elif payout < 0:
                results[bet_type]["losses"] += 1
            results[bet_type]["net"] += payout

    # Dragon and Tiger should perform similarly
    # Tie should lose money (huge house edge)
    assert results[BetType.TIE]["net"] < results[BetType.DRAGON]["net"], \
        "Tie bets should lose more money than Dragon bets"
    assert results[BetType.TIE]["net"] < results[BetType.TIGER]["net"], \
        "Tie bets should lose more money than Tiger bets"

    # Dragon and Tiger should be close
    dragon_net = results[BetType.DRAGON]["net"]
    tiger_net = results[BetType.TIGER]["net"]
    diff = abs(dragon_net - tiger_net)
    assert diff < 500, \
        f"Dragon and Tiger should have similar results (D:{dragon_net} vs T:{tiger_net})"

    print("\nSimulation Results (1000 rounds each):")
    for bet_type in [BetType.DRAGON, BetType.TIGER, BetType.TIE]:
        net = results[bet_type]["net"]
        house_edge = -net / 10000 * 100  # Total wagered: 1000 * $10
        print(f"{bet_type.value:6s}: Net ${net:6.0f}, House Edge: {house_edge:5.2f}%")


if __name__ == "__main__":
    # Run all tests
    import sys

    print("Running Dragon Tiger tests...")
    print("=" * 60)

    pytest.main([__file__, "-v", "--tb=short"])
