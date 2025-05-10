"""
Simple test for environment integrator.
"""

import unittest
import os
import tempfile
from unittest.mock import MagicMock, patch

from cardsharp.blackjack.casino import CasinoEnvironment, TableConditions, DealerProfile
from cardsharp.blackjack.bankroll import BasicBankrollManager, BankrollParameters
from cardsharp.blackjack.strategy import Strategy


class MockStrategy(Strategy):
    """Mock strategy for testing."""

    def decide_action(self, player, dealer_up_card, game):
        """Mock decision making."""
        return "stand"

    def decide_insurance(self, player):
        """Mock insurance decision."""
        return False


class TestEnvironmentSimple(unittest.TestCase):
    """Simple tests for environment integration."""

    def test_casino_creation(self):
        """Test simple casino creation."""
        casino = CasinoEnvironment(
            casino_type="standard",
            time_of_day="evening",
            weekday=True,
            table_count=1
        )
        self.assertEqual(len(casino.tables), 1)
        self.assertEqual(len(casino.dealers), 1)

    def test_bankroll_manager(self):
        """Test bankroll management."""
        # Create bankroll manager
        bankroll = BasicBankrollManager(
            initial_bankroll=1000.0,
            params=BankrollParameters(
                risk_tolerance=0.5,
                stop_loss=0.5,
                stop_win=1.0
            )
        )

        # Test basic operations
        self.assertEqual(bankroll.current_bankroll, 1000.0)

        # Test win scenario
        bankroll.update_bankroll(result=100, bet_amount=50)
        self.assertEqual(bankroll.current_bankroll, 1100.0)

        # Test loss scenario
        bankroll.update_bankroll(result=-50, bet_amount=50)
        self.assertEqual(bankroll.current_bankroll, 1050.0)


if __name__ == "__main__":
    unittest.main()