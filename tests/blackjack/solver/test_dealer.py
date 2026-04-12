"""Tests for dealer probability computation."""

import pytest
from cardsharp.blackjack.solver.dealer import (
    compute_dealer_table,
    compute_conditional_dealer_table,
    dealer_blackjack_prob,
)


class TestDealerProbabilities:

    def test_probabilities_sum_to_one(self):
        """Every upcard's outcome distribution must sum to 1.0."""
        table = compute_dealer_table(hit_soft_17=True)
        for upcard, probs in table.items():
            total = sum(probs.values())
            assert abs(total - 1.0) < 1e-10, (
                f"Upcard {upcard}: probs sum to {total}"
            )

    def test_conditional_probabilities_sum_to_one(self):
        table = compute_conditional_dealer_table(hit_soft_17=True)
        for upcard, probs in table.items():
            total = sum(probs.values())
            assert abs(total - 1.0) < 1e-10, (
                f"Upcard {upcard}: conditional probs sum to {total}"
            )

    def test_bust_rate_increases_for_stiff_cards(self):
        """Dealer bust rate should be higher for 4-6 than for 7-A."""
        table = compute_dealer_table(hit_soft_17=True)
        stiff_bust = min(table[u].get(22, 0) for u in [4, 5, 6])
        strong_bust = max(table[u].get(22, 0) for u in [7, 8, 9, 10])
        assert stiff_bust > strong_bust

    def test_dealer_6_highest_bust(self):
        """Dealer showing 6 should have the highest bust probability."""
        table = compute_dealer_table(hit_soft_17=True)
        bust_6 = table[6].get(22, 0)
        for upcard in [2, 3, 4, 5, 7, 8, 9, 10, 1]:
            assert bust_6 >= table[upcard].get(22, 0) - 0.001

    def test_h17_vs_s17_ace_up(self):
        """H17 should give different dealer probs than S17 for Ace up."""
        h17 = compute_dealer_table(hit_soft_17=True)
        s17 = compute_dealer_table(hit_soft_17=False)
        # With S17, dealer stands on soft 17 → higher P(17)
        assert s17[1].get(17, 0) > h17[1].get(17, 0)

    def test_only_totals_17_through_22(self):
        """Dealer final totals should only be 17-21 or 22 (bust)."""
        table = compute_dealer_table(hit_soft_17=True)
        valid_totals = {17, 18, 19, 20, 21, 22}
        for upcard, probs in table.items():
            for total in probs:
                assert total in valid_totals, (
                    f"Upcard {upcard}: unexpected total {total}"
                )


class TestDealerBlackjackProb:

    def test_ace_up(self):
        assert abs(dealer_blackjack_prob(1) - 4 / 13) < 1e-10

    def test_ten_up(self):
        assert abs(dealer_blackjack_prob(10) - 1 / 13) < 1e-10

    def test_other_cards(self):
        for v in range(2, 10):
            assert dealer_blackjack_prob(v) == 0.0


class TestConditionalDealer:

    def test_no_blackjack_in_conditional_ace(self):
        """Conditional on no BJ with Ace up, dealer can still make 21 via
        multi-card routes but the probability should be much lower."""
        uncond = compute_dealer_table(hit_soft_17=True)
        cond = compute_conditional_dealer_table(hit_soft_17=True)
        # Unconditional includes BJ (a+10 = 21), conditional excludes it
        assert cond[1].get(21, 0) < uncond[1].get(21, 0)

    def test_non_bj_upcards_unchanged(self):
        """For upcards 2-9, conditional = unconditional."""
        uncond = compute_dealer_table(hit_soft_17=True)
        cond = compute_conditional_dealer_table(hit_soft_17=True)
        for upcard in range(2, 10):
            for total in uncond[upcard]:
                assert abs(uncond[upcard][total] - cond[upcard][total]) < 1e-10
