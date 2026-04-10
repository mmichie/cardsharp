"""Statistical validation of house edge against published theory.

Runs large simulations with basic strategy and asserts the measured
house edge falls within a confidence interval of the known theoretical
value. This catches subtle bugs (wrong payouts, strategy errors, rule
misconfigurations) that individual scenario tests cannot detect.

Reference values from Wizard of Odds / Griffin / Schlesinger.
"""

import random
import math

import pytest

from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.state import _state_placing_bets
from cardsharp.common.io_interface import DummyIOInterface


def _simulate(rules, num_rounds, seed=42):
    """Run num_rounds of basic strategy and return (house_edge, std_err)."""
    random.seed(seed)

    io = DummyIOInterface()
    game = BlackjackGame(rules, io)

    strategy = BasicStrategy()
    player = Player("Sim", io, strategy, initial_money=10_000_000)
    game.add_player(player)
    game.set_state(_state_placing_bets)

    results = []  # per-round net as fraction of initial bet

    for _ in range(num_rounds):
        money_before = player.money
        game.play_round()
        money_after = player.money

        net = money_after - money_before
        wager = player.initial_bets if player.initial_bets > 0 else rules.min_bet
        results.append(net / wager)

        game.reset()

    mean = sum(results) / len(results)
    variance = sum((r - mean) ** 2 for r in results) / (len(results) - 1)
    std_err = math.sqrt(variance / len(results))

    house_edge = -mean  # positive = house advantage
    return house_edge, std_err


class TestHouseEdge:
    """Validate simulated house edge against published values.

    Each test uses a seeded RNG for reproducibility and asserts the
    measured edge is within 4 standard errors of the expected value.
    This gives ~99.99% confidence against false failures while still
    catching real bugs (which shift the edge by 1-5%).
    """

    NUM_ROUNDS = 200_000

    def test_six_deck_h17(self):
        """6-deck H17, no DAS, late surrender.

        Published edge: ~0.55-0.65% (Wizard of Odds).
        """
        rules = Rules(
            num_decks=6,
            dealer_hit_soft_17=True,
            allow_double_down=True,
            allow_split=True,
            allow_surrender=True,
            allow_late_surrender=True,
            allow_double_after_split=False,
            allow_resplitting=False,
            dealer_peek=True,
            blackjack_payout=1.5,
            penetration=0.75,
        )

        edge, se = _simulate(rules, self.NUM_ROUNDS)

        # Assert within 4 SE of expected 0.6% (generous bound)
        expected = 0.006
        tolerance = max(4 * se, 0.005)  # at least 0.5% tolerance
        assert abs(edge - expected) < tolerance, (
            f"6-deck H17 edge {edge:.4%} (SE={se:.4%}) "
            f"outside {expected:.2%} +/- {tolerance:.2%}"
        )

    def test_six_deck_s17(self):
        """6-deck S17, no DAS, late surrender.

        Published edge: ~0.35-0.45% (Wizard of Odds).
        S17 is ~0.2% better for the player than H17.
        """
        rules = Rules(
            num_decks=6,
            dealer_hit_soft_17=False,
            allow_double_down=True,
            allow_split=True,
            allow_surrender=True,
            allow_late_surrender=True,
            allow_double_after_split=False,
            allow_resplitting=False,
            dealer_peek=True,
            blackjack_payout=1.5,
            penetration=0.75,
        )

        edge, se = _simulate(rules, self.NUM_ROUNDS)

        expected = 0.004
        tolerance = max(4 * se, 0.005)
        assert abs(edge - expected) < tolerance, (
            f"6-deck S17 edge {edge:.4%} (SE={se:.4%}) "
            f"outside {expected:.2%} +/- {tolerance:.2%}"
        )

    def test_s17_lower_than_h17(self):
        """S17 should have a lower house edge than H17 (same rules otherwise).

        This is a fundamental blackjack principle -- doesn't depend on
        exact numbers, just relative ordering.
        """
        base = dict(
            num_decks=6,
            allow_double_down=True,
            allow_split=True,
            allow_surrender=True,
            allow_late_surrender=True,
            allow_double_after_split=False,
            allow_resplitting=False,
            dealer_peek=True,
            blackjack_payout=1.5,
            penetration=0.75,
        )

        h17_edge, _ = _simulate(Rules(dealer_hit_soft_17=True, **base), 100_000, seed=99)
        s17_edge, _ = _simulate(Rules(dealer_hit_soft_17=False, **base), 100_000, seed=99)

        assert s17_edge < h17_edge, (
            f"S17 edge ({s17_edge:.4%}) should be lower than "
            f"H17 edge ({h17_edge:.4%})"
        )

    def test_6_to_5_worse_than_3_to_2(self):
        """6:5 blackjack payout should produce a higher house edge than 3:2.

        The 6:5 payout adds ~1.4% to the house edge -- one of the largest
        single-rule effects. Easy to detect even with moderate sample size.
        """
        base = dict(
            num_decks=6,
            dealer_hit_soft_17=True,
            allow_double_down=True,
            allow_split=True,
            allow_surrender=True,
            allow_late_surrender=True,
            dealer_peek=True,
            penetration=0.75,
        )

        edge_3_2, _ = _simulate(Rules(blackjack_payout=1.5, **base), 100_000, seed=77)
        edge_6_5, _ = _simulate(Rules(blackjack_payout=1.2, **base), 100_000, seed=77)

        assert edge_6_5 > edge_3_2 + 0.005, (
            f"6:5 edge ({edge_6_5:.4%}) should be >{0.5}% higher than "
            f"3:2 edge ({edge_3_2:.4%})"
        )
