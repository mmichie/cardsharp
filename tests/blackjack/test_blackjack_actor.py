import pytest

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.actor import (
    Dealer,
    InsufficientFundsError,
    InvalidActionError,
    Player,
)
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


@pytest.mark.asyncio
async def test_decide_action(player):
    # Test when the player's hand value is less than 17
    player.add_card(Card(Suit.HEARTS, Rank.SIX))
    player.add_card(Card(Suit.DIAMONDS, Rank.FIVE))
    assert await player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.HIT

    # Test when the player's hand value is 17 but not a soft 17
    player.add_card(Card(Suit.CLUBS, Rank.SIX))
    assert await player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.STAND

    # Test when the player's hand value is a soft 17
    player.reset()
    player.add_card(Card(Suit.HEARTS, Rank.SIX))
    player.add_card(Card(Suit.SPADES, Rank.ACE))
    assert await player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.HIT

    # Test when the player's hand value is over 21 (busted)
    player.add_card(Card(Suit.CLUBS, Rank.KING))
    assert await player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.STAND

    # Test when the player's hand value is 20
    player.reset()
    player.add_card(Card(Suit.HEARTS, Rank.QUEEN))
    player.add_card(Card(Suit.DIAMONDS, Rank.KING))
    assert await player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.STAND

    # Test when the player's hand value is less than 17 but has an Ace (soft hand)
    player.reset()
    player.add_card(Card(Suit.HEARTS, Rank.ACE))
    player.add_card(Card(Suit.DIAMONDS, Rank.FIVE))
    assert await player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.HIT

    # Test when the player's hand value is 17 with an Ace (soft 17)
    player.add_card(Card(Suit.CLUBS, Rank.TEN))
    assert await player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.HIT


@pytest.mark.asyncio
async def test_decide_action_busted(player):
    # Add cards that results in a bust
    player.add_card(Card(Suit.HEARTS, Rank.QUEEN))
    player.add_card(Card(Suit.DIAMONDS, Rank.KING))
    player.add_card(Card(Suit.SPADES, Rank.THREE))

    assert await player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.STAND


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


# Test for InvalidActionError exception
def test_invalid_action(player):
    # Player attempts to split without having a splittable hand
    player.add_card(Card(Suit.HEARTS, Rank.FIVE))
    with pytest.raises(InvalidActionError):
        player.split()

    # Player attempts to double down without having sufficient funds
    player.place_bet(900)  # Assuming player's initial money is 1000
    with pytest.raises(InsufficientFundsError):
        player.double_down()


# Test for Dealer's should_hit method
def test_dealer_should_hit(dealer):
    # Test when dealer's hand value is less than 17
    dealer.add_card(Card(Suit.HEARTS, Rank.FOUR))
    dealer.add_card(Card(Suit.DIAMONDS, Rank.FIVE))
    assert dealer.should_hit()

    # Test when dealer's hand value is 17 but not a soft 17
    dealer.reset()
    dealer.add_card(Card(Suit.CLUBS, Rank.SEVEN))
    dealer.add_card(Card(Suit.SPADES, Rank.TEN))
    assert not dealer.should_hit()

    # Test when dealer's hand value is over 17
    dealer.reset()
    dealer.add_card(Card(Suit.HEARTS, Rank.KING))
    dealer.add_card(Card(Suit.CLUBS, Rank.EIGHT))
    assert not dealer.should_hit()


# Test for Dealer's reset method
def test_dealer_reset(dealer):
    # Dealer is given some cards
    dealer.add_card(Card(Suit.HEARTS, Rank.FOUR))
    dealer.add_card(Card(Suit.DIAMONDS, Rank.FIVE))

    # Reset the dealer
    dealer.reset()

    # Check that the dealer's hand is now empty
    assert len(dealer.current_hand.cards) == 0


# Test for Player's split method
def test_player_split(player):
    # Player is given two cards of the same rank
    player.add_card(Card(Suit.HEARTS, Rank.FOUR))
    player.add_card(Card(Suit.DIAMONDS, Rank.FOUR))

    # Player splits their hand
    player.split()

    # Check that the player now has two hands
    assert len(player.hands) == 2

    # Check that each hand only has one card
    assert len(player.hands[0].cards) == 1
    assert len(player.hands[1].cards) == 1


# Test for Player's add_card method
def test_player_add_card(player):
    card = Card(Suit.HEARTS, Rank.TWO)
    player.add_card(card)
    assert (
        player.current_hand.cards[-1] == card
    )  # check if the last card in the hand is the added card


# Test for Player's reset method
def test_player_reset(player):
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.place_bet(10)
    player.reset()
    assert len(player.current_hand.cards) == 0  # hand should be empty
    assert player.bet == 0  # bet should be reset to 0
    assert player.money == 1000  # money should be reset to initial value
    assert player.done is False  # player should not be done


# Test for Dealer's add_card method
def test_dealer_add_card(dealer):
    card = Card(Suit.HEARTS, Rank.TWO)
    dealer.add_card(card)
    assert (
        dealer.current_hand.cards[-1] == card
    )  # check if the last card in the hand is the added card


# Test for player-dealer interaction
@pytest.mark.asyncio
async def test_player_dealer_interaction(player, dealer):
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.add_card(Card(Suit.HEARTS, Rank.THREE))
    dealer.add_card(Card(Suit.SPADES, Rank.TEN))
    dealer.add_card(Card(Suit.SPADES, Rank.NINE))

    action = await player.decide_action(dealer.current_hand.cards[0])
    if action == Action.HIT:
        player.add_card(Card(Suit.HEARTS, Rank.FOUR))
    elif action == Action.STAND:
        while dealer.should_hit():
            dealer.add_card(Card(Suit.SPADES, Rank.TWO))

    assert player.current_hand.value() <= 21
    assert dealer.current_hand.value() <= 21


def test_valid_actions(player):
    # Reset the player's state
    player.reset()

    # Initially, no actions should be valid since player doesn't have any cards
    assert player.valid_actions == []

    # When the player has a single card, only hit and stand actions should be valid
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    assert set(player.valid_actions) == set([Action.HIT, Action.STAND])

    # When the player has two cards of the same rank, all actions including split should be valid
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    assert set(player.valid_actions) == set(Action)

    # After the player stands, no more actions should be valid
    player.stand()
    assert player.valid_actions == []


def test_can_afford(player):
    # When the player has enough money
    assert player.can_afford(500)  # Player initially has 1000

    # When the player does not have enough money
    assert not player.can_afford(2000)  # Player initially has 1000

    # When the player has just enough money
    assert player.can_afford(1000)  # Player initially has 1000

    # After making a bet
    player.place_bet(200)
    assert player.can_afford(300)  # Player now has 800
    assert not player.can_afford(900)  # Player now has 800


def test_hit(player):
    # Initial state
    assert len(player.current_hand.cards) == 0
    assert not player.is_done()

    # Player hits once, should not be done
    player.hit(Card(Suit.HEARTS, Rank.TWO))
    assert len(player.current_hand.cards) == 1
    assert not player.is_done()

    # Player hits again, should not be done
    player.hit(Card(Suit.HEARTS, Rank.THREE))
    assert len(player.current_hand.cards) == 2
    assert not player.is_done()

    # Player hits and busts, should be done
    player.hit(Card(Suit.HEARTS, Rank.KING))
    player.hit(Card(Suit.DIAMONDS, Rank.KING))
    assert len(player.current_hand.cards) == 4
    assert player.is_done()


def test_split_insufficient_funds(player):
    # Place a bet
    player.place_bet(500)

    # Add two cards of the same rank to the player's hand
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.add_card(Card(Suit.DIAMONDS, Rank.TWO))

    # Player should not be able to split because they don't have enough money
    with pytest.raises(InsufficientFundsError):
        player.split()

    # Player's money should not have been reduced
    assert player.money == 500

    # Player's hand should still contain two cards
    assert len(player.current_hand.cards) == 2


def test_double_down_insufficient_funds(player):
    # Place a bet that is half of the player's initial money
    player.place_bet(600)

    # Player should not be able to double down because they don't have enough money
    with pytest.raises(InsufficientFundsError):
        player.double_down()

    # Player's money should not have been reduced further
    assert player.money == 400

    # Player's bet should still be the same
    assert player.bet == 600


def test_double_down_valid_bet(player):
    # Place a bet that is less than half of the player's initial money
    player.place_bet(400)

    # Player should be able to double down
    player.double_down()

    # Player's money should be reduced by the bet amount
    assert player.money == 200

    # Player's bet should be doubled
    assert player.bet == 800


def test_double_down_no_initial_bet(player):
    # Player has not placed any bet yet
    assert player.bet == 0

    # Player should not be able to double down without an initial bet
    with pytest.raises(InvalidActionError):
        player.double_down()


def test_double_down_after_bust(player):
    # Place a bet
    player.place_bet(400)

    # Add cards to make player bust
    player.add_card(Card(Suit.SPADES, Rank.TEN))
    player.add_card(Card(Suit.HEARTS, Rank.TEN))
    player.add_card(Card(Suit.DIAMONDS, Rank.FIVE))
    assert player.is_busted()

    # Player should not be able to double down after busting
    with pytest.raises(InvalidActionError):
        player.double_down()
