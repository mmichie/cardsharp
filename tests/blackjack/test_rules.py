"""Unit tests for blackjack Rules class.

Covers branches missed by scenario tests: split/surrender/insurance guards,
resplit logic, simple getters, serialization, and five-card charlie.
"""

import pytest
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.hand import BlackjackHand
from cardsharp.common.testing import parse_card


def _hand(*specs):
    """Build a BlackjackHand from card specs like 'As', 'Kh'."""
    h = BlackjackHand()
    for s in specs:
        h.add_card(parse_card(s))
    return h


def _split_hand(*specs):
    """Build a BlackjackHand flagged as a split hand."""
    h = _hand(*specs)
    h._is_split = True
    return h


# -------------------------------------------------------------------
# is_blackjack
# -------------------------------------------------------------------


class TestIsBlackjack:
    def test_ace_king(self):
        assert Rules().is_blackjack(_hand("As", "Kh"))

    def test_ace_ten(self):
        assert Rules().is_blackjack(_hand("As", "Th"))

    def test_three_card_21(self):
        assert not Rules().is_blackjack(_hand("7h", "7d", "7s"))

    def test_two_card_not_21(self):
        assert not Rules().is_blackjack(_hand("Kh", "9d"))


# -------------------------------------------------------------------
# can_split
# -------------------------------------------------------------------


class TestCanSplit:
    def test_disabled(self):
        assert not Rules(allow_split=False).can_split(_hand("8h", "8d"))

    def test_pair(self):
        assert Rules().can_split(_hand("8h", "8d"))

    def test_non_pair(self):
        assert not Rules().can_split(_hand("8h", "9d"))

    def test_resplit_blocked_when_disabled(self):
        assert not Rules(allow_resplitting=False).can_split(
            _split_hand("8h", "8d")
        )

    def test_resplit_aces_always_blocked(self):
        assert not Rules(allow_resplitting=True).can_split(
            _split_hand("As", "Ad")
        )

    def test_resplit_non_aces_allowed(self):
        assert Rules(allow_resplitting=True).can_split(
            _split_hand("8h", "8d")
        )


# -------------------------------------------------------------------
# can_double_down (fallback path, no variant validator)
# -------------------------------------------------------------------


class TestCanDoubleDownFallback:
    """Test the fallback code when _action_validator is None."""

    def _rules(self, **kw):
        r = Rules(**kw)
        r._action_validator = None
        return r

    def test_disabled(self):
        assert not self._rules(allow_double_down=False).can_double_down(
            _hand("5h", "6d")
        )

    def test_three_cards(self):
        assert not self._rules().can_double_down(_hand("3h", "4d", "5s"))

    def test_split_without_das(self):
        assert not self._rules(allow_double_after_split=False).can_double_down(
            _split_hand("5h", "6d")
        )

    def test_split_with_das(self):
        assert self._rules(allow_double_after_split=True).can_double_down(
            _split_hand("5h", "6d")
        )

    def test_normal_two_cards(self):
        assert self._rules().can_double_down(_hand("5h", "6d"))


# -------------------------------------------------------------------
# can_insure
# -------------------------------------------------------------------


class TestCanInsure:
    def test_dealer_ace(self):
        rules = Rules(allow_insurance=True)
        assert rules.can_insure(_hand("As", "Kh"), _hand("Th", "9d"))

    def test_dealer_non_ace(self):
        rules = Rules(allow_insurance=True)
        assert not rules.can_insure(_hand("Kh", "As"), _hand("Th", "9d"))

    def test_disabled(self):
        rules = Rules(allow_insurance=False)
        assert not rules.can_insure(_hand("As", "Kh"), _hand("Th", "9d"))


# -------------------------------------------------------------------
# can_surrender (fallback path, no variant validator)
# -------------------------------------------------------------------


class TestCanSurrenderFallback:
    def _rules(self, **kw):
        r = Rules(**kw)
        r._action_validator = None
        return r

    def test_disabled(self):
        assert not self._rules(allow_surrender=False).can_surrender(
            _hand("Th", "6d"), is_first_action=True
        )

    def test_not_first_action(self):
        assert not self._rules(allow_surrender=True).can_surrender(
            _hand("Th", "6d"), is_first_action=False
        )

    def test_three_cards(self):
        assert not self._rules(allow_surrender=True).can_surrender(
            _hand("5h", "4d", "7s"), is_first_action=True
        )

    def test_split_hand(self):
        assert not self._rules(allow_surrender=True).can_surrender(
            _split_hand("Th", "6d"), is_first_action=True
        )

    def test_early_surrender(self):
        assert self._rules(
            allow_surrender=True, allow_early_surrender=True
        ).can_surrender(_hand("Th", "6d"), is_first_action=True)

    def test_late_surrender(self):
        assert self._rules(
            allow_surrender=True, allow_late_surrender=True
        ).can_surrender(_hand("Th", "6d"), is_first_action=True)

    def test_default_allows(self):
        """allow_surrender=True without early/late specified still allows."""
        assert self._rules(allow_surrender=True).can_surrender(
            _hand("Th", "6d"), is_first_action=True
        )


# -------------------------------------------------------------------
# can_resplit
# -------------------------------------------------------------------


class TestCanResplit:
    def test_disabled(self):
        assert not Rules(allow_resplitting=False).can_resplit(
            _split_hand("8h", "8d")
        )

    def test_aces_blocked(self):
        assert not Rules(allow_resplitting=True).can_resplit(
            _split_hand("As", "Ad")
        )

    def test_allowed(self):
        assert Rules(allow_resplitting=True).can_resplit(
            _split_hand("8h", "8d")
        )

    def test_non_pair(self):
        assert not Rules(allow_resplitting=True).can_resplit(
            _split_hand("8h", "9d")
        )


# -------------------------------------------------------------------
# Simple getters
# -------------------------------------------------------------------


class TestGetters:
    def test_num_decks(self):
        assert Rules(num_decks=8).get_num_decks() == 8

    def test_min_bet(self):
        assert Rules(min_bet=5.0).get_min_bet() == 5.0

    def test_max_bet(self):
        assert Rules(max_bet=500.0).get_max_bet() == 500.0

    def test_late_surrender(self):
        assert Rules(allow_late_surrender=True).can_late_surrender()
        assert not Rules(allow_late_surrender=False).can_late_surrender()

    def test_double_after_split(self):
        assert Rules(allow_double_after_split=True).can_double_after_split()
        assert not Rules(allow_double_after_split=False).can_double_after_split()

    def test_bonus_payout(self):
        rules = Rules(bonus_payouts={"suited-6-7-8": 2.0})
        assert rules.get_bonus_payout("suited-6-7-8") == 2.0
        assert rules.get_bonus_payout("nonexistent") == 0.0

    def test_time_limit(self):
        assert Rules(time_limit=30).get_time_limit() == 30

    def test_insurance_payout(self):
        assert Rules(insurance_payout=3.0).get_insurance_payout() == 3.0

    def test_dealer_peek(self):
        assert Rules(dealer_peek=True).should_dealer_peek()
        assert not Rules(dealer_peek=False).should_dealer_peek()

    def test_csm(self):
        assert Rules(use_csm=True).is_using_csm()
        assert not Rules(use_csm=False).is_using_csm()

    def test_early_surrender(self):
        assert Rules(allow_early_surrender=True).can_early_surrender()
        assert not Rules(allow_early_surrender=False).can_early_surrender()

    def test_max_splits(self):
        assert Rules(max_splits=4).get_max_splits() == 4

    def test_can_split_more(self):
        rules = Rules(max_splits=3)
        assert rules.can_split_more(2)       # 2 hands < 4
        assert not rules.can_split_more(4)   # 4 hands = max


# -------------------------------------------------------------------
# to_dict
# -------------------------------------------------------------------


class TestToDict:
    def test_all_fields_present(self):
        rules = Rules(
            blackjack_payout=1.2,
            num_decks=8,
            min_bet=5.0,
            max_bet=500.0,
            dealer_peek=True,
            five_card_charlie=True,
            penetration=0.80,
            burn_cards=2,
        )
        d = rules.to_dict()
        assert d["blackjack_payout"] == 1.2
        assert d["num_decks"] == 8
        assert d["min_bet"] == 5.0
        assert d["max_bet"] == 500.0
        assert d["dealer_peek"] is True
        assert d["five_card_charlie"] is True
        assert d["penetration"] == 0.80
        assert d["burn_cards"] == 2
        assert d["variant"] == "classic"


# -------------------------------------------------------------------
# should_dealer_hit
# -------------------------------------------------------------------


class TestShouldDealerHit:
    def test_hit_below_17(self):
        assert Rules().should_dealer_hit(_hand("Th", "5d"))

    def test_stand_hard_17(self):
        assert not Rules(dealer_hit_soft_17=False).should_dealer_hit(
            _hand("Th", "7d")
        )

    def test_hit_soft_17_enabled(self):
        assert Rules(dealer_hit_soft_17=True).should_dealer_hit(
            _hand("As", "6d")
        )

    def test_stand_soft_17_disabled(self):
        assert not Rules(dealer_hit_soft_17=False).should_dealer_hit(
            _hand("As", "6d")
        )

    def test_stand_at_18(self):
        assert not Rules().should_dealer_hit(_hand("Th", "8d"))


# -------------------------------------------------------------------
# Five-card Charlie
# -------------------------------------------------------------------


class TestFiveCardCharlie:
    def test_enabled(self):
        assert Rules(five_card_charlie=True).is_five_card_charlie(
            _hand("2h", "3d", "4s", "2c", "3s")
        )

    def test_disabled(self):
        assert not Rules(five_card_charlie=False).is_five_card_charlie(
            _hand("2h", "3d", "4s", "2c", "3s")
        )

    def test_four_cards(self):
        assert not Rules(five_card_charlie=True).is_five_card_charlie(
            _hand("2h", "3d", "4s", "5c")
        )

    def test_bust(self):
        assert not Rules(five_card_charlie=True).is_five_card_charlie(
            _hand("Th", "9d", "8s", "7c", "6h")
        )

    def test_six_cards(self):
        assert Rules(five_card_charlie=True).is_five_card_charlie(
            _hand("2h", "2d", "2s", "2c", "3s", "3h")
        )
