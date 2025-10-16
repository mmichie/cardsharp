"""
Comprehensive tests for FastBasicStrategy.

Verifies that optimized integer-indexed strategy produces
identical results to original dict-based strategy.
"""

import pytest
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.blackjack.strategy_fast import FastBasicStrategy
from cardsharp.blackjack.hand import BlackjackHand
from cardsharp.blackjack.actor import Player
from cardsharp.common.card import Card, Rank, Suit
from cardsharp.common.io_interface import DummyIOInterface


class TestFastStrategyCorrectness:
    """Verify FastBasicStrategy matches BasicStrategy exactly."""

    def setup_method(self):
        """Set up both strategies for comparison."""
        self.basic_strategy = BasicStrategy()
        self.fast_strategy = FastBasicStrategy()
        self.io_interface = DummyIOInterface()

    def _create_player_with_hand(self, cards):
        """Helper to create player with specific hand."""
        from cardsharp.blackjack.rules import Rules

        player = Player("Test", self.io_interface, self.basic_strategy)
        hand = BlackjackHand()
        for card in cards:
            hand.add_card(card)
        player.hands = [hand]
        player.current_hand_index = 0
        player.hand_done = [False]
        player.done = False
        player.bets = [10]  # Add a bet for validation checks
        player.money = 1000  # Add money for affordability checks

        # Create a minimal mock game object for validation
        class MockGame:
            def __init__(self):
                self.rules = Rules()

        player.game = MockGame()
        return player

    def _get_all_dealer_cards(self):
        """Get representative cards for all dealer possibilities."""
        return [
            Card(Suit.HEARTS, Rank.TWO),
            Card(Suit.HEARTS, Rank.THREE),
            Card(Suit.HEARTS, Rank.FOUR),
            Card(Suit.HEARTS, Rank.FIVE),
            Card(Suit.HEARTS, Rank.SIX),
            Card(Suit.HEARTS, Rank.SEVEN),
            Card(Suit.HEARTS, Rank.EIGHT),
            Card(Suit.HEARTS, Rank.NINE),
            Card(Suit.HEARTS, Rank.TEN),
            Card(Suit.HEARTS, Rank.ACE),
        ]

    def test_hard_hands_match(self):
        """Verify all hard hands produce identical decisions."""
        dealer_cards = self._get_all_dealer_cards()

        # Test Hard 4-21
        for value in range(4, 22):
            # Create a hard hand with the target value
            if value <= 11:
                cards = [
                    Card(Suit.HEARTS, Rank.TWO),
                    Card(Suit.SPADES, Rank(value - 2)),
                ]
            else:
                cards = [
                    Card(Suit.HEARTS, Rank.TEN),
                    Card(Suit.SPADES, Rank(value - 10)),
                ]

            player_basic = self._create_player_with_hand(cards)
            player_fast = self._create_player_with_hand(cards)

            for dealer_card in dealer_cards:
                basic_action = self.basic_strategy.decide_action(
                    player_basic, dealer_card
                )
                fast_action = self.fast_strategy.decide_action(player_fast, dealer_card)

                assert basic_action == fast_action, (
                    f"Mismatch for Hard{value} vs {dealer_card}: "
                    f"Basic={basic_action}, Fast={fast_action}"
                )

    def test_soft_hands_match(self):
        """Verify all soft hands produce identical decisions."""
        dealer_cards = self._get_all_dealer_cards()

        # Test Soft 13-21 (Ace + 2-10)
        for second_value in range(2, 11):
            cards = [
                Card(Suit.HEARTS, Rank.ACE),
                Card(Suit.SPADES, Rank(second_value)),
            ]

            player_basic = self._create_player_with_hand(cards)
            player_fast = self._create_player_with_hand(cards)

            for dealer_card in dealer_cards:
                basic_action = self.basic_strategy.decide_action(
                    player_basic, dealer_card
                )
                fast_action = self.fast_strategy.decide_action(player_fast, dealer_card)

                soft_value = player_basic.current_hand.value()
                assert basic_action == fast_action, (
                    f"Mismatch for Soft{soft_value} vs {dealer_card}: "
                    f"Basic={basic_action}, Fast={fast_action}"
                )

    def test_pair_hands_match(self):
        """Verify all pair hands produce identical decisions."""
        dealer_cards = self._get_all_dealer_cards()

        # Test all pairs
        pair_ranks = [
            Rank.TWO,
            Rank.THREE,
            Rank.FOUR,
            Rank.FIVE,
            Rank.SIX,
            Rank.SEVEN,
            Rank.EIGHT,
            Rank.NINE,
            Rank.TEN,
            Rank.ACE,
        ]

        for rank in pair_ranks:
            cards = [Card(Suit.HEARTS, rank), Card(Suit.SPADES, rank)]

            player_basic = self._create_player_with_hand(cards)
            player_fast = self._create_player_with_hand(cards)

            for dealer_card in dealer_cards:
                basic_action = self.basic_strategy.decide_action(
                    player_basic, dealer_card
                )
                fast_action = self.fast_strategy.decide_action(player_fast, dealer_card)

                assert basic_action == fast_action, (
                    f"Mismatch for Pair{rank} vs {dealer_card}: "
                    f"Basic={basic_action}, Fast={fast_action}"
                )

    def test_face_card_pairs_match(self):
        """Verify face card pairs treated as 10-pairs."""
        dealer_cards = self._get_all_dealer_cards()

        # Test J-J, Q-Q, K-K all treated as Pair10
        face_ranks = [Rank.JACK, Rank.QUEEN, Rank.KING]

        for rank in face_ranks:
            cards = [Card(Suit.HEARTS, rank), Card(Suit.SPADES, rank)]

            player_basic = self._create_player_with_hand(cards)
            player_fast = self._create_player_with_hand(cards)

            for dealer_card in dealer_cards:
                basic_action = self.basic_strategy.decide_action(
                    player_basic, dealer_card
                )
                fast_action = self.fast_strategy.decide_action(player_fast, dealer_card)

                assert basic_action == fast_action, (
                    f"Mismatch for {rank}-{rank} vs {dealer_card}: "
                    f"Basic={basic_action}, Fast={fast_action}"
                )

    def test_comprehensive_coverage(self):
        """
        Comprehensive test covering many hand/dealer combinations.

        This test verifies correctness across a wide range of scenarios.
        """
        from cardsharp.blackjack.action import Action

        test_cases = [
            # (hand_cards, dealer_card, description)
            ([Card(Suit.HEARTS, Rank.TEN), Card(Suit.SPADES, Rank.SIX)], Card(Suit.HEARTS, Rank.FIVE), "Hard 16 vs 5"),
            ([Card(Suit.HEARTS, Rank.ACE), Card(Suit.SPADES, Rank.SEVEN)], Card(Suit.HEARTS, Rank.TEN), "Soft 18 vs 10"),
            ([Card(Suit.HEARTS, Rank.EIGHT), Card(Suit.SPADES, Rank.EIGHT)], Card(Suit.HEARTS, Rank.TEN), "Pair 8 vs 10"),
            ([Card(Suit.HEARTS, Rank.FIVE), Card(Suit.SPADES, Rank.FIVE)], Card(Suit.HEARTS, Rank.NINE), "Pair 5 vs 9"),
            ([Card(Suit.HEARTS, Rank.TEN), Card(Suit.SPADES, Rank.SEVEN)], Card(Suit.HEARTS, Rank.ACE), "Hard 17 vs A"),
            ([Card(Suit.HEARTS, Rank.ACE), Card(Suit.SPADES, Rank.ACE)], Card(Suit.HEARTS, Rank.SIX), "Pair A vs 6"),
        ]

        for hand_cards, dealer_card, description in test_cases:
            player_basic = self._create_player_with_hand(hand_cards)
            player_fast = self._create_player_with_hand(hand_cards)

            basic_action = self.basic_strategy.decide_action(player_basic, dealer_card)
            fast_action = self.fast_strategy.decide_action(player_fast, dealer_card)

            assert basic_action == fast_action, (
                f"Mismatch for {description}: "
                f"Basic={basic_action}, Fast={fast_action}"
            )


class TestFastStrategyPerformance:
    """Performance characterization tests."""

    def setup_method(self):
        """Set up strategies for benchmarking."""
        self.basic_strategy = BasicStrategy()
        self.fast_strategy = FastBasicStrategy()
        self.io_interface = DummyIOInterface()

    def test_fast_strategy_creates_tables(self):
        """Verify fast strategy tables are initialized."""
        assert len(self.fast_strategy.hard_table) == 18  # Hard 4-21
        assert len(self.fast_strategy.soft_table) == 9  # Soft 13-21
        assert len(self.fast_strategy.pair_table) == 11  # Pair 2-A

        # Verify all rows have 10 columns (dealer 2-A)
        for row in self.fast_strategy.hard_table:
            assert len(row) == 10
        for row in self.fast_strategy.soft_table:
            assert len(row) == 10
        for row in self.fast_strategy.pair_table:
            assert len(row) == 10

    def test_dealer_index_mapping(self):
        """Verify dealer card to index mapping is correct."""
        # Test all dealer cards map to correct indices
        test_cases = [
            (Card(Suit.HEARTS, Rank.TWO), 0),
            (Card(Suit.HEARTS, Rank.THREE), 1),
            (Card(Suit.HEARTS, Rank.NINE), 7),
            (Card(Suit.HEARTS, Rank.TEN), 8),
            (Card(Suit.HEARTS, Rank.JACK), 8),
            (Card(Suit.HEARTS, Rank.QUEEN), 8),
            (Card(Suit.HEARTS, Rank.KING), 8),
            (Card(Suit.HEARTS, Rank.ACE), 9),
        ]

        for card, expected_index in test_cases:
            actual_index = self.fast_strategy._get_dealer_index(card)
            assert actual_index == expected_index, (
                f"Dealer index mismatch for {card}: "
                f"expected={expected_index}, actual={actual_index}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
