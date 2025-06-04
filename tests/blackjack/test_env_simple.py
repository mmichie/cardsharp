"""
Simple test for environment integrator.
"""

from cardsharp.blackjack.casino import CasinoEnvironment
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


def test_casino_creation():
    """Test simple casino creation."""
    casino = CasinoEnvironment(
        casino_type="standard", time_of_day="evening", weekday=True, table_count=1
    )
    assert len(casino.tables) == 1
    assert len(casino.dealers) == 1


def test_bankroll_manager():
    """Test bankroll management."""
    # Create bankroll manager
    bankroll = BasicBankrollManager(
        initial_bankroll=1000.0,
        params=BankrollParameters(risk_tolerance=0.5, stop_loss=0.5, stop_win=1.0),
    )

    # Test basic operations
    assert bankroll.current_bankroll == 1000.0

    # Test win scenario
    bankroll.update_bankroll(result=100, bet_amount=50)
    assert bankroll.current_bankroll == 1100.0

    # Test loss scenario
    bankroll.update_bankroll(result=-50, bet_amount=50)
    assert bankroll.current_bankroll == 1050.0
