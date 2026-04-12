"""Tests for dealer probability computation."""

from cardsharp.blackjack.solver.dealer import (
    compute_dealer_table,
    compute_conditional_dealer_table,
    dealer_blackjack_prob,
)
from cardsharp.blackjack.solver.types import Deck


class TestDealerProbabilities:

    def test_probabilities_sum_to_one_infinite(self):
        table = compute_dealer_table(hit_soft_17=True, deck=Deck.infinite())
        for upcard, probs in table.items():
            total = sum(probs.values())
            assert abs(total - 1.0) < 1e-10, f"Upcard {upcard}: sum={total}"

    def test_probabilities_sum_to_one_finite(self):
        table = compute_dealer_table(hit_soft_17=True, deck=Deck.finite(6))
        for upcard, probs in table.items():
            total = sum(probs.values())
            assert abs(total - 1.0) < 1e-10, f"Upcard {upcard}: sum={total}"

    def test_conditional_probabilities_sum_to_one(self):
        table = compute_conditional_dealer_table(True, Deck.infinite())
        for upcard, probs in table.items():
            total = sum(probs.values())
            assert abs(total - 1.0) < 1e-10, f"Upcard {upcard}: sum={total}"

    def test_bust_rate_increases_for_stiff_cards(self):
        table = compute_dealer_table(True, Deck.infinite())
        stiff_bust = min(table[u].get(22, 0) for u in [4, 5, 6])
        strong_bust = max(table[u].get(22, 0) for u in [7, 8, 9, 10])
        assert stiff_bust > strong_bust

    def test_dealer_6_highest_bust(self):
        table = compute_dealer_table(True, Deck.infinite())
        bust_6 = table[6].get(22, 0)
        for upcard in [2, 3, 4, 5, 7, 8, 9, 10, 1]:
            assert bust_6 >= table[upcard].get(22, 0) - 0.001

    def test_h17_vs_s17_ace_up(self):
        h17 = compute_dealer_table(hit_soft_17=True, deck=Deck.infinite())
        s17 = compute_dealer_table(hit_soft_17=False, deck=Deck.infinite())
        assert s17[1].get(17, 0) > h17[1].get(17, 0)

    def test_only_totals_17_through_22(self):
        table = compute_dealer_table(True, Deck.infinite())
        valid_totals = {17, 18, 19, 20, 21, 22}
        for upcard, probs in table.items():
            for total in probs:
                assert total in valid_totals

    def test_finite_vs_infinite_similar(self):
        """6-deck finite should be close to infinite for dealer probs."""
        inf_t = compute_dealer_table(True, Deck.infinite())
        fin_t = compute_dealer_table(True, Deck.finite(6))
        for upcard in [2, 6, 10]:
            for total in [17, 18, 19, 20, 21, 22]:
                diff = abs(inf_t[upcard].get(total, 0) - fin_t[upcard].get(total, 0))
                assert diff < 0.01, f"Up {upcard}, total {total}: diff={diff}"


class TestDealerBlackjackProb:

    def test_ace_up_infinite(self):
        assert abs(dealer_blackjack_prob(1, Deck.infinite()) - 4 / 13) < 1e-10

    def test_ten_up_infinite(self):
        assert abs(dealer_blackjack_prob(10, Deck.infinite()) - 1 / 13) < 1e-10

    def test_ace_up_finite_1d(self):
        d = Deck.finite(1)
        # After dealing Ace up: 51 remaining, 16 ten-values
        p = dealer_blackjack_prob(1, d)
        assert abs(p - 16 / 51) < 1e-10

    def test_other_cards(self):
        for v in range(2, 10):
            assert dealer_blackjack_prob(v, Deck.infinite()) == 0.0


class TestConditionalDealer:

    def test_no_blackjack_in_conditional_ace(self):
        uncond = compute_dealer_table(True, Deck.infinite())
        cond = compute_conditional_dealer_table(True, Deck.infinite())
        assert cond[1].get(21, 0) < uncond[1].get(21, 0)

    def test_non_bj_upcards_unchanged(self):
        uncond = compute_dealer_table(True, Deck.infinite())
        cond = compute_conditional_dealer_table(True, Deck.infinite())
        for upcard in range(2, 10):
            for total in uncond[upcard]:
                assert abs(uncond[upcard][total] - cond[upcard][total]) < 1e-10
