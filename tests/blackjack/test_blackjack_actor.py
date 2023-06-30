import pytest

from cardsharp.blackjack.actor import InsufficientFundsError, Player
from cardsharp.common.io_interface import TestIOInterface


@pytest.fixture
def io_interface():
    return TestIOInterface()


@pytest.fixture
def player(io_interface):
    return Player("Alice", io_interface)


def test_place_bet(player):
    # Initial state
    assert player.money == 1000
    assert player.bet == 0

    # Place a valid bet
    player.place_bet(10)
    assert player.bet == 10
    assert player.money == 990

    # Place a bet greater than the available money
    with pytest.raises(InsufficientFundsError):
        player.place_bet(10000)
    assert player.bet == 10  # Bet should not be updated
    assert player.money == 990  # Money should remain unchanged


def test_place_bet_insufficient_money(player):
    # Place a bet greater than the available money
    with pytest.raises(InsufficientFundsError):
        player.place_bet(10000)
    assert player.bet == 0  # Bet should not be updated
    assert player.money == 1000  # Money should remain unchanged


def test_payout(player):
    # Initial state
    assert player.money == 1000
    assert player.bet == 0

    # Place a bet
    player.place_bet(10)

    # Perform a payout
    player.payout(20)
    assert (
        player.money == 1020
    )  # 990 (money after bet) + 10 (original bet) + 20 (payout)
    assert player.bet == 0  # Bet should be reset to 0
    assert player.insurance == 0  # Insurance should be reset to 0
    assert player.is_done()  # Player should be done after getting a payout


def test_payout_no_bet(player):
    # Initial state
    assert player.money == 1000
    assert player.bet == 0

    # Perform a payout without placing a bet
    player.payout(20)
    assert player.money == 1020  # 1000 (initial money) + 20 (payout)
    assert player.bet == 0  # Bet should remain unchanged


def test_payout_with_bet_zero(player):
    # Initial state
    assert player.money == 1000
    assert player.bet == 0

    # Perform a payout with bet = 0
    player.payout(20)
    assert player.money == 1020  # 1000 (initial money) + 20 (payout)
    assert player.bet == 0  # Bet should remain unchanged
