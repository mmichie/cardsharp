"""
Scenario-based blackjack tests using RiggedShoe.

These tests verify game logic by specifying exact player/dealer hands
and asserting on outcomes. The ``scenario`` fixture (from conftest.py)
handles all boilerplate: shoe creation, game setup, and result extraction.
"""

import pytest
from cardsharp.common.testing import RiggedShoe, parse_card, cards


# ---------------------------------------------------------------------------
# Blackjack (natural 21) scenarios
# ---------------------------------------------------------------------------


class TestBlackjackNaturals:

    def test_player_blackjack_wins(self, scenario):
        result = scenario(player=["As", "Kh"], dealer=["Th", "7d"])
        assert result.player_blackjack
        assert result.player_won
        assert result.player_value == 21

    def test_dealer_blackjack_wins(self, scenario):
        result = scenario(player=["Th", "9h"], dealer=["As", "Kd"])
        assert result.dealer_blackjack
        assert result.dealer_won

    def test_both_blackjack_pushes(self, scenario):
        result = scenario(player=["As", "Kh"], dealer=["Ah", "Kd"])
        assert result.player_blackjack
        assert result.dealer_blackjack
        assert result.is_push


# ---------------------------------------------------------------------------
# Bust scenarios
# ---------------------------------------------------------------------------


class TestBusts:

    def test_player_busts_on_hit(self, scenario):
        """Player has hard 16 vs dealer 7, hits and gets K -> bust."""
        result = scenario(
            player=["Th", "6h"],
            dealer=["7h", "Td"],
            extra=["Kc"],
        )
        assert result.player_bust
        assert result.dealer_won

    def test_dealer_busts(self, scenario):
        """Player stands on 19, dealer has 16 and draws a 10 -> bust."""
        result = scenario(
            player=["Th", "9h"],
            dealer=["6h", "Td"],
            extra=["Kc"],
        )
        assert result.dealer_bust
        assert result.player_won


# ---------------------------------------------------------------------------
# Push scenarios
# ---------------------------------------------------------------------------


class TestPush:

    def test_equal_values_push(self, scenario):
        result = scenario(player=["Th", "8h"], dealer=["9d", "9c"])
        assert result.is_push
        assert result.player_value == 18
        assert result.dealer_value == 18


# ---------------------------------------------------------------------------
# Double down scenarios
# ---------------------------------------------------------------------------


class TestDoubleDown:

    def test_double_on_11(self, scenario):
        """Player has 11 (7+4), doubles, gets 9 -> 20."""
        result = scenario(
            player=["7h", "4s"],
            dealer=["8h", "Kd"],
            extra=["9c"],
            rules={"allow_double_down": True},
        )
        assert result.player_value == 20
        assert "double" in result.actions_taken


# ---------------------------------------------------------------------------
# Split scenarios
# ---------------------------------------------------------------------------


class TestSplits:

    def test_never_split_tens(self, scenario):
        """Basic strategy: never split 10s. Stand on 20."""
        result = scenario(
            player=["Th", "Td"],
            dealer=["7h", "Kh"],
            extra=["8h"],
            rules={"allow_split": True},
        )
        assert result.player_value == 20
        assert "split" not in result.actions_taken

    def test_never_split_fives(self, scenario):
        """Basic strategy: never split 5s. Should double on 10."""
        result = scenario(
            player=["5h", "5d"],
            dealer=["9h", "Kh"],
            extra=["Th"],
            rules={"allow_split": True, "allow_double_down": True},
        )
        assert result.player_value == 20
        assert "split" not in result.actions_taken

    def test_nines_vs_7_stands(self, scenario):
        """9,9 vs 7: stand on 18, don't split."""
        result = scenario(
            player=["9h", "9d"],
            dealer=["7h", "Kh"],
            rules={"allow_split": True},
        )
        assert result.player_value == 18
        assert "split" not in result.actions_taken
        assert result.player_won

    def test_hard_16_vs_6_stands(self, scenario):
        """Hard 16 vs 6: stand (dealer likely busts)."""
        result = scenario(
            player=["Th", "6s"],
            dealer=["6h", "Kd"],
            extra=["Kh"],  # dealer: 6+K=16, hits K -> bust
        )
        assert result.player_value == 16
        assert result.player_won


# ---------------------------------------------------------------------------
# Surrender scenarios
# ---------------------------------------------------------------------------


class TestSurrender:

    def test_surrender_16_vs_ace(self, scenario):
        result = scenario(
            player=["Th", "6s"],
            dealer=["As", "9d"],
            rules={"allow_surrender": True},
        )
        assert result.is_surrender

    def test_surrender_16_vs_10(self, scenario):
        """Hard 16 vs 10 -- surrender."""
        result = scenario(
            player=["Th", "6s"],
            dealer=["Kh", "9d"],
        )
        assert result.is_surrender

    def test_surrender_15_vs_10(self, scenario):
        """Hard 15 vs 10 -- surrender."""
        result = scenario(
            player=["Th", "5s"],
            dealer=["Kh", "8d"],
        )
        assert result.is_surrender

    def test_surrender_16_vs_9(self, scenario):
        """Hard 16 vs 9 -- surrender."""
        result = scenario(
            player=["Th", "6s"],
            dealer=["9h", "Kd"],
        )
        assert result.is_surrender

    def test_late_surrender(self, scenario):
        """Late surrender allowed after dealer checks for blackjack."""
        result = scenario(
            player=["Th", "6h"],
            dealer=["As", "9d"],
            rules={"allow_late_surrender": True},
        )
        assert result.is_surrender


# ---------------------------------------------------------------------------
# Dealer rules
# ---------------------------------------------------------------------------


class TestDealerRules:

    def test_dealer_stands_on_soft_17(self, scenario):
        """Dealer has A+6=soft 17, stands. Player 19 wins."""
        result = scenario(
            player=["Th", "9h"],
            dealer=["As", "6h"],
            extra=["5h"],
            rules={"dealer_hit_soft_17": False},
        )
        assert result.player_won
        assert result.dealer_value == 17

    def test_dealer_hits_soft_17(self, scenario):
        """Dealer has A+6=soft 17, hits, gets 4 -> 21. Player 19 loses."""
        result = scenario(
            player=["Th", "9h"],
            dealer=["As", "6h"],
            extra=["4h"],
            rules={"dealer_hit_soft_17": True},
        )
        assert result.dealer_won
        assert result.dealer_value == 21


# ---------------------------------------------------------------------------
# Soft hand scenarios
# ---------------------------------------------------------------------------


class TestSoftHands:

    def test_soft_17_hits_to_21(self, scenario):
        """Player has A+6=soft 17, hits, gets 4 -> 21."""
        result = scenario(
            player=["As", "6h"],
            dealer=["2d", "Td"],
            extra=["4h", "8h"],  # player hits 4, dealer hits 8
        )
        assert result.player_won
        assert result.player_value == 21

    def test_ace_revaluation_soft_to_hard(self, scenario):
        """A+5=soft 16, hit 8 -> hard 14 (ace demoted to 1), hit 7 -> 21."""
        result = scenario(
            player=["As", "5h"],
            dealer=["9d", "Kd"],
            extra=["8c", "7d"],
        )
        assert result.player_won
        assert result.player_value == 21

    def test_soft_18_hits_vs_strong_upcard(self, scenario):
        """Soft 18 vs 10 -- basic strategy says hit."""
        result = scenario(
            player=["As", "7h"],
            dealer=["Th", "9d"],
            extra=["3c"],  # A+7+3 = 21
        )
        assert "hit" in result.actions_taken
        assert result.player_value == 21

    def test_soft_18_vs_3_doubles(self, scenario):
        """Soft 18 vs 3: basic strategy says double (DS)."""
        result = scenario(
            player=["As", "7h"],
            dealer=["3d", "5c"],
            extra=["2h", "Kh"],  # player doubles +2 -> 20, dealer 3+5+K=18
            rules={"allow_double_down": True},
        )
        assert "double" in result.actions_taken
        assert result.player_value == 20
        assert result.player_won


# ---------------------------------------------------------------------------
# Actual split scenarios
# ---------------------------------------------------------------------------


class TestSplitExecution:

    def test_split_eights(self, scenario):
        """Split 8s vs 6. Each hand gets a 10 -> 18. Dealer busts."""
        result = scenario(
            player=["8h", "8d"],
            dealer=["6h", "Td"],
            # Split cards: hand1 gets Th, hand2 gets Td
            # Dealer: 16, hits 8c -> bust
            extra=["Th", "Td", "8c"],
            rules={"allow_split": True},
        )
        assert "split" in result.actions_taken
        assert result.player_won

    def test_split_aces_one_card_only(self, scenario):
        """Split aces get only one card each, forced to stand."""
        result = scenario(
            player=["As", "Ac"],
            dealer=["7h", "Td"],
            # Each ace gets one card: Kh -> 21, Qd -> 21
            extra=["Kh", "Qd"],
            rules={"allow_split": True},
        )
        assert "split" in result.actions_taken
        assert result.player_won

    def test_double_after_split(self, scenario):
        """Split 8s, then double each hand (DAS allowed)."""
        result = scenario(
            player=["8h", "8d"],
            dealer=["6h", "Td"],
            # Split cards: hand1=8h+3c=11, hand2=8d+2d=10
            # Hand1 doubles: 11+9c=20
            # Hand2 doubles: 10+Tc=20
            # Dealer: 16, hits Kc -> bust
            extra=["3c", "2d", "9c", "Tc", "Kc"],
            rules={
                "allow_split": True,
                "allow_double_down": True,
                "allow_double_after_split": True,
            },
        )
        assert "split" in result.actions_taken
        assert "double" in result.actions_taken
        assert result.player_won

    def test_no_double_after_split(self, scenario):
        """Split 8s, DAS disallowed: must hit instead of double, both bust."""
        result = scenario(
            player=["8h", "8d"],
            dealer=["7h", "Kh"],
            # Hand1: 8h+3c=11, can't double, hit 5h->16, hit 9h->bust
            # Hand2: 8d+2h=10, can't double, hit 6h->16, hit Tc->bust
            extra=["3c", "2h", "5h", "9h", "6h", "Tc"],
            rules={"allow_split": True, "allow_double_after_split": False},
        )
        assert "split" in result.actions_taken
        assert "double" not in result.actions_taken
        assert result.dealer_won

    def test_split_nines_vs_9(self, scenario):
        """Split 9s vs 9: hand1 gets T->19 (push), hand2 gets 8->17 (loss)."""
        result = scenario(
            player=["9h", "9c"],
            dealer=["9d", "Th"],
            extra=["Td", "8h"],
            rules={"allow_split": True},
        )
        assert "split" in result.actions_taken

    def test_split_aces_both_get_21(self, scenario):
        """Split aces each get a 10-value card -> 21. Dealer has 19."""
        result = scenario(
            player=["As", "Ac"],
            dealer=["Kh", "9h"],
            extra=["Kd", "Th"],
            rules={"allow_split": True},
        )
        assert "split" in result.actions_taken
        assert result.player_won


# ---------------------------------------------------------------------------
# Multi-hit and dealer multi-draw scenarios
# ---------------------------------------------------------------------------


class TestMultipleHits:

    def test_player_hits_three_times(self, scenario):
        """Player has 7 (4+3), hits 3 times to reach 21."""
        result = scenario(
            player=["4h", "3s"],
            dealer=["Th", "8d"],
            extra=["2c", "5d", "7c"],  # 4+3+2+5+7 = 21
        )
        assert result.player_won
        assert result.player_value == 21
        assert result.actions_taken.count("hit") >= 3

    def test_dealer_draws_four_cards(self, scenario):
        """Player stands on 19. Dealer has 5, draws 4 cards, busts."""
        result = scenario(
            player=["Th", "9h"],
            dealer=["2h", "3d"],
            # Dealer: 2+3=5, +2=7, +3=10, +4=14, +8=22 bust
            extra=["2c", "3c", "4c", "8c"],
        )
        assert result.dealer_bust
        assert result.player_won


# ---------------------------------------------------------------------------
# 21-vs-blackjack distinction
# ---------------------------------------------------------------------------


class TestTwentyOneVsBlackjack:

    def test_hit_to_21_is_not_blackjack(self, scenario):
        """Player hits to 21 -- wins, but it is NOT a natural blackjack."""
        result = scenario(
            player=["7h", "4d"],
            dealer=["9h", "8d"],
            extra=["Th"],  # 7+4+T = 21
        )
        assert result.player_won
        assert result.player_value == 21
        assert not result.player_blackjack

    def test_dealer_blackjack_ends_round_immediately(self, scenario):
        """Dealer natural blackjack ends round; player never plays."""
        result = scenario(
            player=["7h", "4d"],
            dealer=["As", "Kh"],
        )
        assert result.dealer_blackjack
        assert result.dealer_won
        # Player was dealt 11 but never got to hit
        assert result.player_value == 11
        assert result.actions_taken == []


# ---------------------------------------------------------------------------
# Five-card Charlie
# ---------------------------------------------------------------------------


class TestFiveCardCharlie:

    def test_five_card_charlie_wins(self, scenario):
        """5 cards totaling 16 beats dealer's 20 with charlie rule."""
        result = scenario(
            player=["2h", "3h"],
            dealer=["Kh", "9h"],
            # 2+3+4+2+5 = 16, five cards -> charlie
            extra=["4h", "2d", "5h"],
            rules={"five_card_charlie": True},
        )
        assert result.player_won
        assert result.player_value == 16

    def test_five_card_charlie_low_total(self, scenario):
        """5 cards totaling 11 still wins via charlie rule."""
        result = scenario(
            player=["2h", "2s"],
            dealer=["Kh", "Th"],
            # 2+2+2+2+3 = 11, five cards -> charlie
            extra=["2d", "2c", "3h"],
            rules={"five_card_charlie": True},
        )
        assert result.player_won
        assert result.player_value == 11


# ---------------------------------------------------------------------------
# Surrender fallback
# ---------------------------------------------------------------------------


class TestSurrenderFallback:

    def test_no_surrender_falls_back_to_hit(self, scenario):
        """16 vs A: would surrender but rule disallows, so player hits."""
        result = scenario(
            player=["Th", "6s"],
            dealer=["As", "9d"],
            extra=["3h"],  # hits: 16+3 = 19, dealer has 20
            rules={"allow_surrender": False},
        )
        assert not result.is_surrender
        assert result.player_value == 19
        assert result.dealer_won

    def test_no_surrender_on_non_qualifying_hand(self, scenario):
        """12 vs 6: basic strategy says stand, not surrender."""
        result = scenario(
            player=["Th", "2s"],
            dealer=["6h", "Td"],
            extra=["Kc"],  # dealer: 6+T=16, hits K -> bust
        )
        assert not result.is_surrender
        assert result.player_won
        assert result.player_value == 12


# ---------------------------------------------------------------------------
# Basic strategy edge cases
# ---------------------------------------------------------------------------


class TestBasicStrategyEdgeCases:

    def test_hard_16_vs_8_hits(self, scenario):
        """16 vs 8: basic strategy says hit, not surrender."""
        result = scenario(
            player=["Th", "6s"],
            dealer=["8s", "Kd"],
            extra=["3h"],  # 16+3 = 19, dealer 8+K=18
        )
        assert not result.is_surrender
        assert "hit" in result.actions_taken
        assert result.player_value == 19
        assert result.player_won

    def test_10_vs_ace_hits_not_doubles(self, scenario):
        """Hard 10 vs A: hit, not double."""
        result = scenario(
            player=["6h", "4h"],
            dealer=["As", "7h"],
            extra=["Kh"],  # 6+4+K = 20, dealer A+7=18
            rules={"allow_double_down": True},
        )
        assert "double" not in result.actions_taken
        assert result.player_value == 20
        assert result.player_won


# ---------------------------------------------------------------------------
# RiggedShoe unit tests
# ---------------------------------------------------------------------------


class TestRiggedShoe:

    def test_deals_in_order(self):
        shoe = RiggedShoe(cards("As", "Kh", "Th"))
        assert shoe.deal() == parse_card("As")
        assert shoe.deal() == parse_card("Kh")
        assert shoe.deal() == parse_card("Th")

    def test_cards_remaining(self):
        shoe = RiggedShoe(cards("As", "Kh", "Th"))
        assert shoe.cards_remaining == 3
        shoe.deal()
        assert shoe.cards_remaining == 2

    def test_exhaustion_error(self):
        shoe = RiggedShoe(cards("As"))
        shoe.deal()
        with pytest.raises(ValueError, match="RiggedShoe exhausted"):
            shoe.deal()

    def test_from_hands_single_player(self):
        shoe = RiggedShoe.from_hands(
            player=["As", "Kh"],
            dealer=["Th", "7d"],
            extra=["5c"],
        )
        # Deal order: As, Th, Kh, 7d, 5c
        assert shoe.deal() == parse_card("As")
        assert shoe.deal() == parse_card("Th")
        assert shoe.deal() == parse_card("Kh")
        assert shoe.deal() == parse_card("7d")
        assert shoe.deal() == parse_card("5c")

    def test_from_hands_multiplayer(self):
        shoe = RiggedShoe.from_hands(
            players=[["As", "Kh"], ["8h", "8d"]],
            dealer=["Th", "7d"],
            extra=["3c"],
        )
        # Round 1: P1(As), P2(8h), D(Th)
        # Round 2: P1(Kh), P2(8d), D(7d)
        # Extra: 3c
        assert shoe.deal() == parse_card("As")
        assert shoe.deal() == parse_card("8h")
        assert shoe.deal() == parse_card("Th")
        assert shoe.deal() == parse_card("Kh")
        assert shoe.deal() == parse_card("8d")
        assert shoe.deal() == parse_card("7d")
        assert shoe.deal() == parse_card("3c")

    def test_shuffle_is_noop(self):
        shoe = RiggedShoe(cards("As", "Kh"))
        shoe.deal()
        shoe.shuffle()
        # shuffle does NOT reset position
        assert shoe.cards_remaining == 1

    def test_rejects_player_and_players(self):
        with pytest.raises(ValueError, match="not both"):
            RiggedShoe.from_hands(
                player=["As", "Kh"],
                players=[["8h", "8d"]],
                dealer=["Th", "7d"],
            )


# ---------------------------------------------------------------------------
# parse_card / cards helpers
# ---------------------------------------------------------------------------


class TestCardParsing:

    def test_parse_card(self):
        from cardsharp.common.card import Suit, Rank

        c = parse_card("As")
        assert c.suit == Suit.SPADES
        assert c.rank == Rank.ACE

    def test_parse_ten(self):
        from cardsharp.common.card import Rank

        c = parse_card("Th")
        assert c.rank == Rank.TEN

    def test_cards_helper(self):
        result = cards("As", "Kh", "Td")
        assert len(result) == 3

    def test_invalid_notation_raises(self):
        with pytest.raises(ValueError, match="Invalid card notation"):
            parse_card("Zx")
