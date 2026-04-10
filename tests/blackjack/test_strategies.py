"""Tests for DealerStrategy, MartingaleStrategy, AggressiveStrategy,
and CountingStrategy edge cases not covered by test_counting_strategy.py.
"""

import pytest
from unittest.mock import MagicMock

from cardsharp.blackjack.strategy import (
    BasicStrategy,
    DealerStrategy,
    MartingaleStrategy,
    AggressiveStrategy,
    CountingStrategy,
)
from cardsharp.blackjack.action import Action
from cardsharp.blackjack.hand import BlackjackHand
from cardsharp.common.card import Card, Rank, Suit


def _card(rank, suit=Suit.HEARTS):
    return Card(suit, rank)


def _make_player(hand_cards, money=1000):
    """Mock player with a real BlackjackHand for value/soft/split checks."""
    player = MagicMock()
    hand = BlackjackHand()
    for c in hand_cards:
        hand.add_card(c)
    player.current_hand = hand
    player.money = money
    player.is_busted.return_value = hand.value() > 21

    # Build valid_actions based on hand
    actions = [Action.HIT, Action.STAND]
    if len(hand_cards) == 2:
        actions.append(Action.DOUBLE)
        if hand.can_split:
            actions.append(Action.SPLIT)
    player.valid_actions = actions
    return player


# -------------------------------------------------------------------
# DealerStrategy
# -------------------------------------------------------------------


class TestDealerStrategy:
    def test_hit_below_17(self):
        s = DealerStrategy()
        p = _make_player([_card(Rank.TEN), _card(Rank.FIVE)])
        assert s.decide_action(p) == Action.HIT

    def test_stand_at_17(self):
        s = DealerStrategy()
        p = _make_player([_card(Rank.TEN), _card(Rank.SEVEN)])
        assert s.decide_action(p) == Action.STAND

    def test_hit_soft_17_fallback(self):
        """Without game reference, always hits soft 17."""
        s = DealerStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.SIX)])
        assert s.decide_action(p) == Action.HIT

    def test_stand_at_18(self):
        s = DealerStrategy()
        p = _make_player([_card(Rank.TEN), _card(Rank.EIGHT)])
        assert s.decide_action(p) == Action.STAND

    def test_stand_when_busted(self):
        s = DealerStrategy()
        p = _make_player(
            [_card(Rank.TEN), _card(Rank.EIGHT), _card(Rank.FIVE)]
        )
        assert s.decide_action(p) == Action.STAND

    def test_never_insures(self):
        s = DealerStrategy()
        assert s.decide_insurance(MagicMock()) is False

    def test_hit_soft_17_with_rules_enabled(self):
        """With game.rules.dealer_hit_soft_17=True, hits soft 17."""
        from cardsharp.blackjack.rules import Rules

        s = DealerStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.SIX)])
        game = MagicMock()
        game.rules = Rules(dealer_hit_soft_17=True)
        assert s.decide_action(p, game=game) == Action.HIT

    def test_stand_soft_17_with_rules_disabled(self):
        """With game.rules.dealer_hit_soft_17=False, stands on soft 17."""
        from cardsharp.blackjack.rules import Rules

        s = DealerStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.SIX)])
        game = MagicMock()
        game.rules = Rules(dealer_hit_soft_17=False)
        assert s.decide_action(p, game=game) == Action.STAND


# -------------------------------------------------------------------
# MartingaleStrategy
# -------------------------------------------------------------------


class TestMartingaleBetting:
    def test_initial_bet(self):
        s = MartingaleStrategy(initial_bet=10)
        assert s.get_bet_amount(5, 1000, 500) == 10

    def test_double_after_loss(self):
        s = MartingaleStrategy(initial_bet=10)
        p = _make_player([_card(Rank.TEN), _card(Rank.SEVEN)])
        p.money = 990  # lost 10
        s.last_money = 1000
        s.last_bet = 10
        s.decide_action(p, _card(Rank.FIVE))
        assert s.current_bet == 20
        assert s.consecutive_losses == 1

    def test_reset_after_win(self):
        s = MartingaleStrategy(initial_bet=10)
        s.current_bet = 40
        s.consecutive_losses = 2
        p = _make_player([_card(Rank.TEN), _card(Rank.SEVEN)])
        p.money = 1040  # won
        s.last_money = 1000
        s.last_bet = 40
        s.decide_action(p, _card(Rank.FIVE))
        assert s.current_bet == 10
        assert s.consecutive_losses == 0

    def test_max_bet_override(self):
        s = MartingaleStrategy(initial_bet=10, max_bet_override=50)
        s.current_bet = 80
        assert s.get_bet_amount(5, 1000, 500) == 50

    def test_capped_by_player_money(self):
        s = MartingaleStrategy(initial_bet=10)
        s.current_bet = 80
        assert s.get_bet_amount(5, 1000, 30) == 30

    def test_min_bet_floor(self):
        s = MartingaleStrategy(initial_bet=3)
        assert s.get_bet_amount(5, 1000, 500) == 5

    def test_reset_bet(self):
        s = MartingaleStrategy(initial_bet=10)
        s.current_bet = 80
        s.consecutive_losses = 3
        s.reset_bet()
        assert s.current_bet == 10
        assert s.consecutive_losses == 0

    def test_no_change_on_push(self):
        """A push (money unchanged) should not trigger doubling or resetting."""
        s = MartingaleStrategy(initial_bet=10)
        s.current_bet = 20
        s.consecutive_losses = 1
        p = _make_player([_card(Rank.TEN), _card(Rank.SEVEN)])
        p.money = 1000
        s.last_money = 1000
        s.last_bet = 20
        s.decide_action(p, _card(Rank.FIVE))
        # Small loss (< half bet) doesn't trigger double
        assert s.current_bet == 20


# -------------------------------------------------------------------
# AggressiveStrategy
# -------------------------------------------------------------------


class TestAggressiveSplits:
    def test_split_aces(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.ACE)])
        assert s.decide_action(p, _card(Rank.FIVE)) == Action.SPLIT

    def test_split_eights(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.EIGHT), _card(Rank.EIGHT)])
        assert s.decide_action(p, _card(Rank.FIVE)) == Action.SPLIT

    def test_split_twos_vs_low(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.TWO), _card(Rank.TWO)])
        assert s.decide_action(p, _card(Rank.SIX)) == Action.SPLIT

    def test_no_split_twos_vs_high(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.TWO), _card(Rank.TWO)])
        assert s.decide_action(p, _card(Rank.NINE)) != Action.SPLIT

    def test_split_nines_vs_five(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.NINE), _card(Rank.NINE)])
        assert s.decide_action(p, _card(Rank.FIVE)) == Action.SPLIT

    def test_no_split_nines_vs_seven(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.NINE), _card(Rank.NINE)])
        assert s.decide_action(p, _card(Rank.SEVEN)) != Action.SPLIT

    def test_no_split_fives(self):
        """5s are never split (better to double on 10)."""
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.FIVE), _card(Rank.FIVE)])
        assert s.decide_action(p, _card(Rank.FIVE)) != Action.SPLIT

    def test_split_sixes_vs_low(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.SIX), _card(Rank.SIX)])
        assert s.decide_action(p, _card(Rank.FIVE)) == Action.SPLIT

    def test_split_sevens_vs_low(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.SEVEN), _card(Rank.SEVEN)])
        assert s.decide_action(p, _card(Rank.SIX)) == Action.SPLIT


class TestAggressiveDoubles:
    def test_double_10_vs_low(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.FOUR), _card(Rank.SIX)])
        assert s.decide_action(p, _card(Rank.FIVE)) == Action.DOUBLE

    def test_double_11_vs_low(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.FIVE), _card(Rank.SIX)])
        assert s.decide_action(p, _card(Rank.SEVEN)) == Action.DOUBLE

    def test_double_9_vs_low(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.FOUR), _card(Rank.FIVE)])
        assert s.decide_action(p, _card(Rank.SIX)) == Action.DOUBLE

    def test_no_double_vs_ten(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.FOUR), _card(Rank.SIX)])
        assert s.decide_action(p, _card(Rank.TEN)) != Action.DOUBLE

    def test_double_soft_15_vs_low(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.FOUR)])
        assert s.decide_action(p, _card(Rank.FIVE)) == Action.DOUBLE

    def test_no_double_soft_vs_high(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.FOUR)])
        assert s.decide_action(p, _card(Rank.EIGHT)) != Action.DOUBLE

    def test_no_double_three_cards(self):
        """Can't double with 3+ cards."""
        s = AggressiveStrategy()
        p = _make_player(
            [_card(Rank.THREE), _card(Rank.THREE), _card(Rank.THREE)]
        )
        assert s.decide_action(p, _card(Rank.FIVE)) != Action.DOUBLE


class TestAggressiveHitStand:
    def test_blackjack_stands(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.KING)])
        assert s.decide_action(p, _card(Rank.FIVE)) == Action.STAND

    def test_hit_hard_11(self):
        """With 3 cards totaling 11, can't double, should hit."""
        s = AggressiveStrategy()
        p = _make_player(
            [_card(Rank.TWO), _card(Rank.THREE), _card(Rank.SIX)]
        )
        assert s.decide_action(p, _card(Rank.TEN)) == Action.HIT

    def test_stand_hard_17_vs_low(self):
        s = AggressiveStrategy()
        p = _make_player(
            [_card(Rank.TEN), _card(Rank.FOUR), _card(Rank.THREE)]
        )
        assert s.decide_action(p, _card(Rank.FIVE)) == Action.STAND

    def test_hit_hard_14_vs_high(self):
        s = AggressiveStrategy()
        p = _make_player(
            [_card(Rank.TEN), _card(Rank.TWO), _card(Rank.TWO)]
        )
        assert s.decide_action(p, _card(Rank.EIGHT)) == Action.HIT

    def test_hit_soft_17(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.SIX)])
        # Need to remove DOUBLE from valid actions to test hit/stand
        p.valid_actions = [Action.HIT, Action.STAND]
        assert s.decide_action(p, _card(Rank.TEN)) == Action.HIT

    def test_hit_soft_18_vs_high(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.SEVEN)])
        p.valid_actions = [Action.HIT, Action.STAND]
        assert s.decide_action(p, _card(Rank.TEN)) == Action.HIT

    def test_stand_soft_18_vs_low(self):
        """With 3 cards (can't double), soft 18 vs low dealer stands."""
        s = AggressiveStrategy()
        p = _make_player(
            [_card(Rank.ACE), _card(Rank.THREE), _card(Rank.FOUR)]
        )
        assert s.decide_action(p, _card(Rank.FIVE)) == Action.STAND

    def test_stand_soft_19(self):
        s = AggressiveStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.EIGHT)])
        p.valid_actions = [Action.HIT, Action.STAND]
        assert s.decide_action(p, _card(Rank.TEN)) == Action.STAND

    def test_fallback_hit(self):
        """When no split/double/hit-stand method returns, default to HIT."""
        s = AggressiveStrategy()
        # Edge case: empty-ish hand, the _decide_on_stand_or_hit always
        # returns something, but let's verify the default path.
        p = _make_player(
            [_card(Rank.TWO), _card(Rank.THREE), _card(Rank.TWO)]
        )
        # Value 7, should hit
        assert s.decide_action(p, _card(Rank.TEN)) == Action.HIT


# -------------------------------------------------------------------
# CountingStrategy edge cases
# -------------------------------------------------------------------


class TestCountingEdgeCases:
    def test_exposed_card_updates_count(self):
        s = CountingStrategy(num_decks=6)
        s.receive_exposed_card_info(_card(Rank.FIVE))
        assert s.count == 1
        assert s.advantage_factor == pytest.approx(0.05)
        assert len(s.exposed_cards) == 1

    def test_exposed_high_card(self):
        s = CountingStrategy(num_decks=6)
        s.receive_exposed_card_info(_card(Rank.KING))
        assert s.count == -1

    def test_get_advantage_neutral(self):
        s = CountingStrategy(num_decks=6)
        assert s.get_advantage() == pytest.approx(-0.005, abs=0.001)

    def test_get_advantage_positive(self):
        s = CountingStrategy(num_decks=6)
        for _ in range(12):
            s.update_count(_card(Rank.FIVE))
        assert s.get_advantage() > 0

    def test_notify_shuffle(self):
        s = CountingStrategy(num_decks=6)
        s.count = 10
        s.true_count = 2.0
        s.counted_cards.add(1)
        s.notify_shuffle()
        assert s.count == 0
        assert s.true_count == 0.0
        assert len(s.counted_cards) == 0
        assert s.decks_remaining == 6.0

    def test_update_decks_remaining(self):
        s = CountingStrategy(num_decks=6)
        s.update_decks_remaining(104)  # 2 decks worth
        assert s.decks_remaining == pytest.approx(4.0)

    def test_update_decks_remaining_floor(self):
        s = CountingStrategy(num_decks=1)
        s.update_decks_remaining(51)
        assert s.decks_remaining == 0.5


# -------------------------------------------------------------------
# H17 / S17 strategy adjustments
# -------------------------------------------------------------------


class TestH17S17Adjustments:
    """The CSV is H17. When game rules are S17, 3 cells change."""

    def _game(self, dealer_hit_soft_17):
        from cardsharp.blackjack.rules import Rules

        game = MagicMock()
        game.rules = Rules(dealer_hit_soft_17=dealer_hit_soft_17)
        return game

    def test_hard_11_vs_ace_h17(self):
        """H17: double 11 vs A."""
        s = BasicStrategy()
        p = _make_player([_card(Rank.FIVE), _card(Rank.SIX)])
        result = s.decide_action(p, _card(Rank.ACE), game=self._game(True))
        assert result == Action.DOUBLE

    def test_hard_11_vs_ace_s17(self):
        """S17: hit 11 vs A."""
        s = BasicStrategy()
        p = _make_player([_card(Rank.FIVE), _card(Rank.SIX)])
        result = s.decide_action(p, _card(Rank.ACE), game=self._game(False))
        assert result == Action.HIT

    def test_soft_18_vs_2_h17(self):
        """H17: double-or-stand soft 18 vs 2."""
        s = BasicStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.SEVEN)])
        result = s.decide_action(p, _card(Rank.TWO), game=self._game(True))
        assert result == Action.DOUBLE

    def test_soft_18_vs_2_s17(self):
        """S17: stand soft 18 vs 2."""
        s = BasicStrategy()
        p = _make_player([_card(Rank.ACE), _card(Rank.SEVEN)])
        result = s.decide_action(p, _card(Rank.TWO), game=self._game(False))
        assert result == Action.STAND

    def test_pair_8_vs_ace_h17(self):
        """H17: surrender 8,8 vs A."""
        s = BasicStrategy()
        p = _make_player([_card(Rank.EIGHT), _card(Rank.EIGHT)])
        p.valid_actions = [Action.HIT, Action.STAND, Action.SPLIT, Action.SURRENDER]
        result = s.decide_action(p, _card(Rank.ACE), game=self._game(True))
        assert result == Action.SURRENDER

    def test_pair_8_vs_ace_s17(self):
        """S17: split 8,8 vs A."""
        s = BasicStrategy()
        p = _make_player([_card(Rank.EIGHT), _card(Rank.EIGHT)])
        result = s.decide_action(p, _card(Rank.ACE), game=self._game(False))
        assert result == Action.SPLIT

    def test_pair_8_vs_ace_h17_no_surrender(self):
        """H17 without surrender: fall back to split 8,8 vs A."""
        s = BasicStrategy()
        p = _make_player([_card(Rank.EIGHT), _card(Rank.EIGHT)])
        # No SURRENDER in valid actions
        result = s.decide_action(p, _card(Rank.ACE), game=self._game(True))
        assert result == Action.SPLIT

    def test_no_game_uses_h17_default(self):
        """Without game reference, the CSV (H17) is used as-is."""
        s = BasicStrategy()
        p = _make_player([_card(Rank.FIVE), _card(Rank.SIX)])
        result = s.decide_action(p, _card(Rank.ACE))
        assert result == Action.DOUBLE


# -------------------------------------------------------------------
# BasicStrategy fallback paths
# -------------------------------------------------------------------


class TestBasicStrategyFallbacks:
    def test_unknown_action_symbol(self):
        """Unknown CSV symbol defaults to HIT."""
        s = BasicStrategy()
        s._get_action_from_strategy = lambda ht, dc: "X"
        p = _make_player([_card(Rank.TEN), _card(Rank.FIVE)])
        assert s.decide_action(p, _card(Rank.SIX)) == Action.HIT

    def test_last_resort_stand(self):
        """When desired action isn't valid, fall back to available actions."""
        s = BasicStrategy()
        p = _make_player([_card(Rank.TEN), _card(Rank.FIVE)])
        p.valid_actions = [Action.STAND]
        result = s._get_valid_action(p, Action.HIT, "H")
        assert result == Action.STAND

    def test_last_resort_first_available(self):
        """When neither HIT nor STAND available, pick first valid action."""
        s = BasicStrategy()
        p = _make_player([_card(Rank.TEN), _card(Rank.FIVE)])
        p.valid_actions = [Action.SURRENDER]
        # HIT action that isn't in valid_actions triggers last-resort path
        result = s._get_valid_action(p, Action.HIT, "H")
        # HIT not in valid, STAND not in valid, falls to valid_actions[0]
        assert result == Action.SURRENDER

    def test_split_fallback_keyerror(self):
        """KeyError in split fallback hard-total lookup gracefully falls back."""
        s = BasicStrategy()
        p = _make_player([_card(Rank.EIGHT), _card(Rank.EIGHT)])
        p.valid_actions = [Action.HIT, Action.STAND]  # No SPLIT
        # Monkey-patch to raise KeyError on hard lookup
        original = s._get_action_from_strategy

        def bad_lookup(ht, dc):
            if ht.startswith("Hard"):
                return "ZZZZZ"  # Will cause KeyError in _map_action_symbol
            return original(ht, dc)

        s._get_action_from_strategy = bad_lookup
        result = s._get_valid_action(p, Action.SPLIT, "P", "5")
        assert result in (Action.HIT, Action.STAND)
