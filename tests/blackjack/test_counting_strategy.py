"""
Deterministic tests for the card counting strategy.

These tests verify counting mechanics with exact card sequences --
no randomness, no statistics. Each test constructs a specific situation
and asserts the strategy does the right thing.
"""

import random

import pytest
from cardsharp.common.card import Card, Suit, Rank
from cardsharp.common.shoe import Shoe
from cardsharp.common.testing import RiggedShoe, cards
from cardsharp.blackjack.strategy import CountingStrategy, BasicStrategy
from cardsharp.blackjack.action import Action
from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.blackjack import BlackjackGame, play_game
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.state import _state_placing_bets
from cardsharp.common.io_interface import DummyIOInterface


# ---------------------------------------------------------------------------
# Hi-Lo count tracking
# ---------------------------------------------------------------------------


class TestHiLoCount:

    def test_high_cards_decrement_count(self):
        """10, J, Q, K, A are all -1."""
        s = CountingStrategy(num_decks=1)
        for rank in (Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING, Rank.ACE):
            s.update_count(Card(Suit.HEARTS, rank))
        assert s.count == -5

    def test_low_cards_increment_count(self):
        """2, 3, 4, 5, 6 are all +1."""
        s = CountingStrategy(num_decks=1)
        for rank in (Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX):
            s.update_count(Card(Suit.HEARTS, rank))
        assert s.count == 5

    def test_neutral_cards_no_change(self):
        """7, 8, 9 are neutral (0)."""
        s = CountingStrategy(num_decks=1)
        for rank in (Rank.SEVEN, Rank.EIGHT, Rank.NINE):
            s.update_count(Card(Suit.HEARTS, rank))
        assert s.count == 0

    def test_mixed_hand_cancels_out(self):
        """One low + one high = net zero."""
        s = CountingStrategy(num_decks=1)
        s.update_count(Card(Suit.HEARTS, Rank.FIVE))   # +1
        s.update_count(Card(Suit.HEARTS, Rank.KING))   # -1
        assert s.count == 0

    def test_count_accumulates_across_multiple_cards(self):
        """Verify running count over a sequence of known cards."""
        s = CountingStrategy(num_decks=1)
        # 2(+1), 3(+1), T(-1), A(-1), 5(+1), 7(0), K(-1)
        sequence = [Rank.TWO, Rank.THREE, Rank.TEN, Rank.ACE,
                    Rank.FIVE, Rank.SEVEN, Rank.KING]
        for rank in sequence:
            s.update_count(Card(Suit.SPADES, rank))
        # +1 +1 -1 -1 +1 +0 -1 = 0
        assert s.count == 0


# ---------------------------------------------------------------------------
# True count calculation
# ---------------------------------------------------------------------------


class TestTrueCount:

    def test_true_count_divides_by_decks_remaining(self):
        s = CountingStrategy(num_decks=6)
        s.count = 6
        s.decks_remaining = 3.0
        s.calculate_true_count()
        assert s.true_count == 2.0

    def test_true_count_with_half_deck(self):
        s = CountingStrategy(num_decks=1)
        s.count = 3
        s.decks_remaining = 0.5
        s.calculate_true_count()
        assert s.true_count == 6.0

    def test_true_count_negative(self):
        s = CountingStrategy(num_decks=6)
        s.count = -4
        s.decks_remaining = 2.0
        s.calculate_true_count()
        assert s.true_count == -2.0

    def test_true_count_floors_at_half_deck(self):
        """decks_remaining never goes below 0.5 in the formula."""
        s = CountingStrategy(num_decks=1)
        s.count = 2
        s.decks_remaining = 0.1  # set artificially low
        s.calculate_true_count()
        # max(0.5, 0.1) = 0.5, so TC = 2/0.5 = 4
        assert s.true_count == 4.0


# ---------------------------------------------------------------------------
# Bet sizing
# ---------------------------------------------------------------------------


class TestBetSizing:

    def test_minimum_bet_at_zero_count(self):
        s = CountingStrategy(num_decks=1)
        s.count = 0
        s.decks_remaining = 1.0
        assert s.get_bet_amount(10, 1000, 10000) == 10

    def test_minimum_bet_at_negative_count(self):
        s = CountingStrategy(num_decks=1)
        s.count = -5
        s.decks_remaining = 1.0
        assert s.get_bet_amount(10, 1000, 10000) == 10

    def test_minimum_bet_at_tc_1(self):
        """TC +1 is breakeven -- still bet minimum."""
        s = CountingStrategy(num_decks=1)
        s.count = 1
        s.decks_remaining = 1.0
        assert s.get_bet_amount(10, 1000, 10000) == 10

    def test_4x_bet_at_tc_2(self):
        """TC +2: ~0.5% player edge, start escalating."""
        s = CountingStrategy(num_decks=1)
        s.count = 2
        s.decks_remaining = 1.0
        assert s.get_bet_amount(10, 1000, 10000) == 40

    def test_8x_bet_at_tc_3(self):
        s = CountingStrategy(num_decks=1)
        s.count = 3
        s.decks_remaining = 1.0
        assert s.get_bet_amount(10, 1000, 10000) == 80

    def test_12x_bet_at_tc_4(self):
        s = CountingStrategy(num_decks=1)
        s.count = 4
        s.decks_remaining = 1.0
        assert s.get_bet_amount(10, 1000, 10000) == 120

    def test_20x_bet_at_tc_5(self):
        s = CountingStrategy(num_decks=1)
        s.count = 5
        s.decks_remaining = 1.0
        assert s.get_bet_amount(10, 1000, 10000) == 200

    def test_20x_bet_at_tc_10(self):
        """Max bet caps at 20x regardless of how high TC goes."""
        s = CountingStrategy(num_decks=1)
        s.count = 10
        s.decks_remaining = 1.0
        assert s.get_bet_amount(10, 1000, 10000) == 200

    def test_bet_capped_at_max_bet(self):
        s = CountingStrategy(num_decks=1)
        s.count = 10
        s.decks_remaining = 1.0
        assert s.get_bet_amount(10, 100, 10000) == 100

    def test_bet_capped_at_player_money(self):
        s = CountingStrategy(num_decks=1)
        s.count = 10
        s.decks_remaining = 1.0
        assert s.get_bet_amount(10, 1000, 50) == 50

    def test_half_deck_amplifies_true_count(self):
        """RC=2 with 0.5 decks remaining -> TC=4 -> 12x bet."""
        s = CountingStrategy(num_decks=1)
        s.count = 2
        s.decks_remaining = 0.5
        assert s.get_bet_amount(10, 1000, 10000) == 120


# ---------------------------------------------------------------------------
# Insurance decisions
# ---------------------------------------------------------------------------


class TestInsuranceDecision:

    def test_take_insurance_at_tc_3(self):
        s = CountingStrategy(num_decks=1)
        s.count = 3
        s.decks_remaining = 1.0
        assert s.decide_insurance(None) is True

    def test_take_insurance_at_tc_5(self):
        s = CountingStrategy(num_decks=1)
        s.count = 5
        s.decks_remaining = 1.0
        assert s.decide_insurance(None) is True

    def test_decline_insurance_at_tc_2(self):
        s = CountingStrategy(num_decks=1)
        s.count = 2
        s.decks_remaining = 1.0
        assert s.decide_insurance(None) is False

    def test_decline_insurance_at_zero(self):
        s = CountingStrategy(num_decks=1)
        s.count = 0
        s.decks_remaining = 1.0
        assert s.decide_insurance(None) is False

    def test_decline_insurance_negative_count(self):
        s = CountingStrategy(num_decks=1)
        s.count = -3
        s.decks_remaining = 1.0
        assert s.decide_insurance(None) is False


# ---------------------------------------------------------------------------
# Count reset on shuffle
# ---------------------------------------------------------------------------


class TestCountReset:

    def test_reset_clears_count(self):
        s = CountingStrategy(num_decks=6)
        s.count = 5
        s.true_count = 2.5
        s.counted_cards = {1, 2, 3}
        s.reset_count()
        assert s.count == 0
        assert s.true_count == 0.0
        assert len(s.counted_cards) == 0

    def test_reset_restores_initial_decks(self):
        s = CountingStrategy(num_decks=6)
        s.decks_remaining = 1.5
        s.reset_count()
        assert s.decks_remaining == 6.0

    def test_reset_with_single_deck(self):
        s = CountingStrategy(num_decks=1)
        s.decks_remaining = 0.5
        s.count = 4
        s.reset_count()
        assert s.decks_remaining == 1.0
        assert s.count == 0


# ---------------------------------------------------------------------------
# Play deviations (Illustrious 18) -- integration tests
# ---------------------------------------------------------------------------


def _play_counting_scenario(*, player_cards, dealer_cards, extra=None,
                            running_count=0, decks_remaining=1.0,
                            rules_kwargs=None):
    """Helper: play a hand with a counting strategy at a known count.

    Returns the actions taken by the player.
    """
    shoe = RiggedShoe.from_hands(
        player=player_cards, dealer=dealer_cards, extra=extra or [],
    )
    rules = Rules(**(rules_kwargs or {}))
    io = DummyIOInterface()
    game = BlackjackGame(rules, io, shoe)

    strategy = CountingStrategy(num_decks=1)
    strategy.count = running_count
    strategy.decks_remaining = decks_remaining

    player = Player("Counter", io, strategy, initial_money=10000)
    game.add_player(player)
    game.set_state(_state_placing_bets)
    game.play_round()

    # Extract actions from the player's action history
    actions = []
    for hand_actions in player.action_history:
        for action in hand_actions:
            actions.append(action)
    return actions


class TestPlayDeviations:

    def test_stand_16_vs_10_at_tc_0(self):
        """Illustrious 18: Stand on 16 vs 10 when TC >= 0 (normally hit).

        Dealt cards: 9(0)+7(0)+T(-1)+8(0) shift count by -1.
        Pre-set count=+1 so TC=0 at decision time.
        """
        actions = _play_counting_scenario(
            player_cards=["9h", "7s"],   # 16, neutral cards
            dealer_cards=["Th", "8d"],   # T is -1, 8 is neutral
            running_count=1,             # +1 - 1(T) = 0 at decision
        )
        assert Action.STAND in actions
        assert Action.HIT not in actions

    def test_hit_16_vs_10_at_tc_negative(self):
        """Below TC 0: revert to basic strategy hit on 16 vs 10.

        Dealt cards shift count by -1 (the T). Pre-set -1, final TC=-2.
        """
        actions = _play_counting_scenario(
            player_cards=["9h", "7s"],
            dealer_cards=["Th", "8d"],
            extra=["8h"],  # hit card -> bust (24), doesn't matter
            running_count=-1,
        )
        assert Action.HIT in actions

    def test_stand_12_vs_3_at_tc_2(self):
        """Stand on 12 vs 3 when TC >= 2 (normally hit).

        Dealt cards: 9(0)+3(+1)+3(+1)+8(0) shift by +2.
        Pre-set 0, TC=2 at decision.
        """
        actions = _play_counting_scenario(
            player_cards=["9h", "3s"],   # 12
            dealer_cards=["3h", "8d"],   # 3 is +1, 8 neutral
            extra=["9c"],                # dealer: 3+8=11, hits 9 → 20
            running_count=0,
        )
        assert Action.STAND in actions

    def test_hit_12_vs_3_at_tc_below_2(self):
        """Below TC 2: basic strategy hits 12 vs 3.

        Dealt cards shift by +2. Pre-set -2, TC=0.
        """
        actions = _play_counting_scenario(
            player_cards=["9h", "3s"],
            dealer_cards=["3h", "8d"],
            extra=["7h", "9c"],  # player hits 7 → 19, dealer hits 9 → 20
            running_count=-2,
        )
        assert Action.HIT in actions

    def test_double_11_vs_ace_at_tc_1(self):
        """Double 11 vs A when TC >= 1 (normally hit).

        Dealt cards: 7(0)+4(+1)+A(-1)+8(0) shift by 0.
        Pre-set 1, TC=1 at decision.
        """
        actions = _play_counting_scenario(
            player_cards=["7h", "4s"],   # 11
            dealer_cards=["As", "8d"],   # A(-1), 8(0)
            extra=["9c"],                # double card → 20
            running_count=1,
            rules_kwargs={"allow_double_down": True},
        )
        assert Action.DOUBLE in actions

    def test_hit_11_vs_ace_at_tc_0(self):
        """Below TC 1: basic strategy hits 11 vs A.

        Dealt cards shift by 0. Pre-set 0, TC=0.
        """
        actions = _play_counting_scenario(
            player_cards=["7h", "4s"],
            dealer_cards=["As", "8d"],
            extra=["Tc"],  # hit card → 21
            running_count=0,
            rules_kwargs={"allow_double_down": True},
        )
        assert Action.HIT in actions
        assert Action.DOUBLE not in actions

    def test_hit_12_vs_4_at_negative_tc(self):
        """Hit 12 vs 4 when TC < 0 (normally stand).

        Dealt cards: 9(0)+3(+1)+4(+1)+8(0) shift by +2.
        Pre-set -3, TC=-1 at decision.
        """
        actions = _play_counting_scenario(
            player_cards=["9h", "3s"],   # 12
            dealer_cards=["4h", "8d"],   # 4(+1), 8(0)
            extra=["8h", "9c"],          # player hits 8 → 20, dealer hits 9
            running_count=-3,
        )
        assert Action.HIT in actions

    def test_stand_12_vs_4_at_tc_0(self):
        """At TC >= 0: basic strategy stands on 12 vs 4.

        Dealt cards shift by +2. Pre-set -2, TC=0.
        """
        actions = _play_counting_scenario(
            player_cards=["9h", "3s"],
            dealer_cards=["4h", "8d"],
            extra=["9c"],  # dealer: 4+8=12, hits 9 → 21
            running_count=-2,
        )
        assert Action.STAND in actions

    def test_basic_strategy_at_neutral_count(self):
        """With count=0 and neutral dealt cards, matches basic strategy."""
        # Hard 17 vs 10: basic says stand. T(-1) shifts count.
        actions = _play_counting_scenario(
            player_cards=["9h", "8s"],   # 17, neutral
            dealer_cards=["Th", "7d"],   # T(-1), 7(0)
            running_count=1,             # +1 - 1 = 0
        )
        assert Action.STAND in actions


# ---------------------------------------------------------------------------
# Full game integration: count tracks correctly through a hand
# ---------------------------------------------------------------------------


class TestCountIntegration:

    def test_count_updates_from_visible_cards(self):
        """After a game, count reflects all dealt cards."""
        shoe = RiggedShoe.from_hands(
            player=["Th", "9s"],  # T(-1), 9(0)
            dealer=["Kh", "7d"],  # K(-1), 7(0). Dealer has 17, stands.
        )
        rules = Rules()
        io = DummyIOInterface()
        game = BlackjackGame(rules, io, shoe)

        strategy = CountingStrategy(num_decks=1)
        player = Player("Counter", io, strategy, initial_money=1000)
        game.add_player(player)
        game.set_state(_state_placing_bets)
        game.play_round()

        # Count all visible cards post-game (like play_game does)
        for card in game.visible_cards:
            card_id = id(card)
            if card_id not in strategy.counted_cards:
                strategy.update_count(card)
                strategy.counted_cards.add(card_id)

        # T(-1) + 9(0) + K(-1) + 7(0) = -2
        assert strategy.count == -2

    def test_count_tracks_dealer_hit_cards(self):
        """Count includes dealer's hit cards, not just initial deal."""
        shoe = RiggedShoe.from_hands(
            player=["Th", "9s"],  # stand on 19
            dealer=["2h", "3d"],  # 5, must hit
            extra=["4c", "5c", "8h"],  # dealer: 2+3+4+5=14, +8=22 bust
        )
        rules = Rules()
        io = DummyIOInterface()
        game = BlackjackGame(rules, io, shoe)

        strategy = CountingStrategy(num_decks=1)
        player = Player("Counter", io, strategy, initial_money=1000)
        game.add_player(player)
        game.set_state(_state_placing_bets)
        game.play_round()

        # Post-game: count dealer hit cards that decide_action missed
        for card in game.visible_cards:
            card_id = id(card)
            if card_id not in strategy.counted_cards:
                strategy.update_count(card)
                strategy.counted_cards.add(card_id)

        # T(-1) + 9(0) + 2(+1) + 3(+1) + 4(+1) + 5(+1) + 8(0) = +3
        assert strategy.count == 3

    def test_bet_reflects_count_from_previous_cards(self):
        """After seeing low cards, count goes up and next bet increases."""
        rules = Rules(min_bet=10, max_bet=1000)
        io = DummyIOInterface()
        strategy = CountingStrategy(num_decks=6)

        # Feed the strategy a bunch of low cards directly
        low_cards = [
            Card(Suit.HEARTS, Rank.TWO),
            Card(Suit.HEARTS, Rank.THREE),
            Card(Suit.HEARTS, Rank.FOUR),
            Card(Suit.HEARTS, Rank.FIVE),
            Card(Suit.HEARTS, Rank.SIX),
            Card(Suit.SPADES, Rank.TWO),
            Card(Suit.SPADES, Rank.THREE),
            Card(Suit.SPADES, Rank.FOUR),
        ]
        for card in low_cards:
            strategy.update_count(card)

        # 8 low cards = count +8
        assert strategy.count == 8

        # Simulate having dealt 8 cards from a 6-deck shoe
        strategy.decks_remaining = max(0.5, (312 - 8) / 52)  # ~5.85
        strategy.calculate_true_count()

        # TC = 8 / 5.85 ≈ 1.37
        assert strategy.true_count > 1.0

        # TC ~1.37 truncates to 1 → minimum bet (need TC >= 2 to escalate)
        bet = strategy.get_bet_amount(10, 1000, 10000)
        assert bet == 10, f"Expected minimum bet at TC~1.37, got {bet}"


# ---------------------------------------------------------------------------
# End-to-end: counting beats basic over same shoes
# ---------------------------------------------------------------------------


class TestCountingBeatsBasic:

    def test_counting_outperforms_basic_over_same_shoes(self):
        """Play 500 shoes with both strategies on identical card sequences.

        This is the definitive test: same cards, different strategies.
        Counting should earn significantly more than basic.
        """
        basic_earn = 0
        counting_earn = 0
        counting_initial_bets = 0
        basic_initial_bets = 0
        rules = Rules(min_bet=10, max_bet=1000)
        io = DummyIOInterface()

        for seed in range(500):
            random.seed(seed)
            shoe_b = Shoe(num_decks=1, penetration=0.75)
            strat_b = BasicStrategy()

            random.seed(seed)
            shoe_c = Shoe(num_decks=1, penetration=0.75)
            strat_c = CountingStrategy(num_decks=1)

            for _ in range(20):
                e, _, ib, _, s = play_game(
                    rules, io, ["P"], strat_b, shoe_b, 10000
                )
                basic_earn += e
                basic_initial_bets += ib
                shoe_b = s

                e, _, ib, _, s = play_game(
                    rules, io, ["P"], strat_c, shoe_c, 10000
                )
                counting_earn += e
                counting_initial_bets += ib
                shoe_c = s

        # Counting must earn more than basic
        assert counting_earn > basic_earn, (
            f"Counting ({counting_earn:+.0f}) should beat basic ({basic_earn:+.0f})"
        )

        # Counting should show a player edge on initial wagers
        player_edge = counting_earn / counting_initial_bets
        assert player_edge > 0, (
            f"Counting should be profitable, got {player_edge:.4%} edge"
        )
