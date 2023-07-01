import pytest

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.actor import Dealer, InsufficientFundsError, Player
from cardsharp.blackjack.hand import BlackjackHand
from cardsharp.blackjack.strategy import DealerStrategy
from cardsharp.common.card import Card, Rank, Suit
from cardsharp.common.io_interface import TestIOInterface


@pytest.fixture
def io_interface():
    return TestIOInterface()


@pytest.fixture
def dealer_strategy():
    return DealerStrategy()


@pytest.fixture
def player(io_interface, dealer_strategy):
    return Player("Alice", io_interface, dealer_strategy)


@pytest.fixture
def dealer(io_interface):
    return Dealer("Dealer", io_interface)


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


def test_has_bet(player):
    # Initial state
    assert not player.has_bet()

    # Place a bet
    player.place_bet(10)
    assert player.has_bet()

    # Reset the bet
    player.reset()
    assert not player.has_bet()


def test_stand(player):
    # Initial state
    assert not player.is_done()

    # Player chooses to stand
    player.stand()
    assert player.is_done()

    # Reset the player's turn
    player.reset()
    assert not player.is_done()


def test_is_busted(player):
    # Initial state
    assert not player.is_busted()

    # Add cards that won't result in a bust
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.add_card(Card(Suit.CLUBS, Rank.THREE))
    assert not player.is_busted()

    # Add cards that results in a bust
    player.add_card(Card(Suit.SPADES, Rank.KING))
    player.add_card(Card(Suit.CLUBS, Rank.KING))
    assert player.is_busted()

    # Reset the player's hand
    player.reset()
    assert not player.is_busted()


def test_decide_action(player):
    # Test when the player's hand value is less than 17
    player.add_card(Card(Suit.HEARTS, Rank.SIX))
    player.add_card(Card(Suit.DIAMONDS, Rank.FIVE))
    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.HIT

    # Test when the player's hand value is 17 but not a soft 17
    player.add_card(Card(Suit.CLUBS, Rank.SIX))
    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.STAND

    # Test when the player's hand value is a soft 17
    player.reset()
    player.add_card(Card(Suit.HEARTS, Rank.SIX))
    player.add_card(Card(Suit.SPADES, Rank.ACE))
    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.HIT

    # Test when the player's hand value is over 21 (busted)
    player.add_card(Card(Suit.CLUBS, Rank.KING))
    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.STAND

    # Test when the player's hand value is 20
    player.reset()
    player.add_card(Card(Suit.HEARTS, Rank.QUEEN))
    player.add_card(Card(Suit.DIAMONDS, Rank.KING))
    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.STAND

    # Test when the player's hand value is less than 17 but has an Ace (soft hand)
    player.reset()
    player.add_card(Card(Suit.HEARTS, Rank.ACE))
    player.add_card(Card(Suit.DIAMONDS, Rank.FIVE))
    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.HIT

    # Test when the player's hand value is 17 with an Ace (soft 17)
    player.add_card(Card(Suit.CLUBS, Rank.TEN))
    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.HIT


def test_decide_action_busted(player):
    # Add cards that results in a bust
    player.add_card(Card(Suit.HEARTS, Rank.QUEEN))
    player.add_card(Card(Suit.DIAMONDS, Rank.KING))
    player.add_card(Card(Suit.SPADES, Rank.THREE))

    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.STAND


def test_buy_insurance(player):
    # Initial state
    assert player.money == 1000
    assert player.insurance == 0

    # Buy insurance
    player.buy_insurance(50)
    assert player.insurance == 50
    assert player.money == 950

    # Attempt to buy insurance exceeding available money
    with pytest.raises(InsufficientFundsError):
        player.buy_insurance(2000)
    assert player.insurance == 50  # Insurance should not be updated
    assert player.money == 950  # Money should remain unchanged


def test_current_hand(dealer):
    # Test that current hand is empty initially
    assert len(dealer.current_hand.cards) == 0


def test_has_ace(dealer):
    # Test without Ace
    dealer.add_card(Card(Suit.HEARTS, Rank.TWO))
    assert not dealer.has_ace()

    dealer.reset()

    # Test with Ace
    dealer.add_card(Card(Suit.CLUBS, Rank.ACE))
    assert dealer.has_ace()


def test_add_card(dealer):
    dealer.add_card(Card(Suit.HEARTS, Rank.THREE))
    assert len(dealer.current_hand.cards) == 1
    assert dealer.current_hand.cards[0] == Card(Suit.HEARTS, Rank.THREE)


def test_should_hit(dealer):
    # Test when hand value is less than 17
    dealer.add_card(Card(Suit.DIAMONDS, Rank.FOUR))
    dealer.add_card(Card(Suit.SPADES, Rank.FIVE))
    assert dealer.should_hit()

    dealer.reset()

    # Assert that dealer current hand is BlackjackHand
    assert isinstance(dealer.current_hand, BlackjackHand)

    # Test when hand value is 17 but soft
    dealer.add_card(Card(Suit.HEARTS, Rank.SIX))
    dealer.add_card(Card(Suit.DIAMONDS, Rank.ACE))
    assert dealer.should_hit()

    dealer.reset()

    # Test when hand value is more than 17
    dealer.add_card(Card(Suit.CLUBS, Rank.KING))
    dealer.add_card(Card(Suit.SPADES, Rank.EIGHT))
    assert not dealer.should_hit()

    dealer.reset()

    # Test when hand value is exactly 17 and not soft
    dealer.add_card(Card(Suit.HEARTS, Rank.SEVEN))
    dealer.add_card(Card(Suit.CLUBS, Rank.TEN))
    assert not dealer.should_hit()
