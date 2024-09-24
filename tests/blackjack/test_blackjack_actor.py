import pytest
from unittest.mock import Mock

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.actor import (
    Dealer,
    InsufficientFundsError,
    InvalidActionError,
    Player,
)
from cardsharp.blackjack.hand import BlackjackHand
from cardsharp.blackjack.strategy import DealerStrategy
from cardsharp.blackjack.stats import SimulationStats
from cardsharp.blackjack.state import DealingState
from cardsharp.blackjack.blackjack import BlackjackGame
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
    assert player.bets == []

    # Place a valid bet
    player.place_bet(10, min_bet=10)
    assert player.bets == [10]
    assert player.money == 990

    # Place a bet greater than the available money
    with pytest.raises(InsufficientFundsError):
        player.place_bet(10000, min_bet=10)
    assert player.bets == [10]  # Bets should not be updated
    assert player.money == 990  # Money should remain unchanged


def test_place_bet_insufficient_money(player):
    # Place a bet greater than the available money
    with pytest.raises(InsufficientFundsError):
        player.place_bet(10000, min_bet=10)
    assert player.bets == []  # Bets should not be updated
    assert player.money == 1000  # Money should remain unchanged


def test_payout(player):
    # Initial state
    assert player.money == 1000
    assert player.bets == []
    assert player.total_winnings == 0

    # Place a bet
    player.place_bet(10, min_bet=10)
    assert player.money == 990
    assert player.bets == [10]

    # Perform a payout (winning scenario)
    player.payout(0, 20)  # Payout for hand index 0

    # Check final state
    assert player.money == 1010, "Player's money should be 1010 after payout"
    assert player.bets[0] == 0, "Bet should be reset to 0 after payout"
    assert (
        player.total_winnings == 10
    ), "Total winnings should be 10 (20 payout - 10 original bet)"
    assert player.done is False, "Player should not be marked as done after payout"

    # Additional test for a larger payout (e.g., blackjack scenario)
    player.reset()
    player.money = 1010  # Set money to previous total
    player.total_winnings = 10  # Ensure total_winnings is cumulative
    player.place_bet(20, min_bet=10)
    assert player.money == 990  # 1010 - 20
    player.payout(0, 50)  # Payout for hand index 0

    assert player.money == 1040, "Player's money should be 1040 after blackjack payout"
    assert (
        player.total_winnings == 40
    ), "Total winnings should be 40 (10 from first win + 30 from blackjack)"


def test_has_bet(player):
    # Initial state
    assert not player.has_bet()

    # Place a bet
    player.place_bet(10, min_bet=10)
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

    # Add cards that result in a bust
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


def test_invalid_action(player):
    # Player attempts to split without having a splittable hand
    player.add_card(Card(Suit.HEARTS, Rank.FIVE))
    with pytest.raises(InvalidActionError):
        player.split()

    # Player attempts to double down without having sufficient funds
    player.place_bet(900, min_bet=10)  # Assuming player's initial money is 1000
    player.add_card(Card(Suit.HEARTS, Rank.SIX))
    player.add_card(Card(Suit.DIAMONDS, Rank.FIVE))
    with pytest.raises(InsufficientFundsError):
        player.double_down()


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


def test_dealer_reset(dealer):
    # Dealer is given some cards
    dealer.add_card(Card(Suit.HEARTS, Rank.FOUR))
    dealer.add_card(Card(Suit.DIAMONDS, Rank.FIVE))

    # Reset the dealer
    dealer.reset()

    # Check that the dealer's hand is now empty
    assert len(dealer.current_hand.cards) == 0


def test_player_split(player):
    # Player places a bet
    player.place_bet(100, min_bet=10)
    assert player.money == 900

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

    # Check that bets have been updated
    assert player.bets == [100, 100]
    assert player.money == 800  # Deducted additional bet for split


def test_player_add_card(player):
    card = Card(Suit.HEARTS, Rank.TWO)
    player.add_card(card)
    assert (
        player.current_hand.cards[-1] == card
    )  # check if the last card in the hand is the added card


def test_player_reset(player):
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.place_bet(10, min_bet=10)
    player.reset()
    assert len(player.current_hand.cards) == 0  # hand should be empty
    assert player.bets == []  # bets should be reset
    assert player.done is False  # player should not be done


def test_player_dealer_interaction(player, dealer):
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.add_card(Card(Suit.HEARTS, Rank.THREE))
    dealer.add_card(Card(Suit.SPADES, Rank.TEN))
    dealer.add_card(Card(Suit.SPADES, Rank.NINE))

    action = player.decide_action(dealer.current_hand.cards[0])
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

    # When the player has two cards of the same rank, actions including split should be valid
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    expected_actions = {
        Action.HIT,
        Action.STAND,
        Action.SPLIT,
        Action.DOUBLE,
        Action.SURRENDER,
        Action.INSURANCE,
    }
    assert set(player.valid_actions) == expected_actions

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
    player.place_bet(200, min_bet=10)
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


def test_split_sufficient_funds(player):
    # Place a bet
    player.place_bet(500, min_bet=10)
    assert player.money == 500  # Verify remaining money after bet

    # Add two cards of the same rank to the player's hand
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.add_card(Card(Suit.DIAMONDS, Rank.TWO))

    # Player should be able to split
    player.split()

    # Verify the split occurred
    assert len(player.hands) == 2
    assert len(player.hands[0].cards) == 1
    assert len(player.hands[1].cards) == 1
    assert player.money == 0  # All money should now be in bets
    assert player.bets == [500, 500]  # Bets for both hands
    assert player.total_bets == 1000  # Total bets should be doubled


def test_split_insufficient_funds(player):
    # Place a bet that's more than half the player's money
    player.place_bet(600, min_bet=10)
    assert player.money == 400  # Verify remaining money after bet

    # Add two cards of the same rank to the player's hand
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.add_card(Card(Suit.DIAMONDS, Rank.TWO))

    # Player should not be able to split because they don't have enough money
    with pytest.raises(InsufficientFundsError):
        player.split()

    # Verify no split occurred
    assert len(player.hands) == 1
    assert len(player.hands[0].cards) == 2
    assert player.money == 400  # Money should remain unchanged
    assert player.bets == [600]  # Bet should remain unchanged
    assert player.total_bets == 600  # Total bets should remain unchanged


def test_double_down_insufficient_funds(player):
    # Place a bet that is half of the player's initial money
    player.place_bet(600, min_bet=10)

    # Add initial cards
    player.add_card(Card(Suit.HEARTS, Rank.NINE))
    player.add_card(Card(Suit.DIAMONDS, Rank.TWO))

    # Player should not be able to double down because they don't have enough money
    with pytest.raises(InsufficientFundsError):
        player.double_down()

    # Player's money should not have been reduced further
    assert player.money == 400

    # Player's bet should still be the same
    assert player.bets == [600]


def test_double_down_valid_bet(player):
    # Place a bet that is less than half of the player's initial money
    player.place_bet(400, min_bet=10)

    # Add initial cards
    player.add_card(Card(Suit.HEARTS, Rank.NINE))
    player.add_card(Card(Suit.DIAMONDS, Rank.TWO))

    # Player should be able to double down
    player.double_down()

    # Player's money should be reduced by the bet amount
    assert player.money == 200

    # Player's bet should be doubled
    assert player.bets == [800]
    assert player.total_bets == 800


def test_double_down_no_initial_bet(player):
    # Player has not placed any bet yet
    assert player.bets == []

    # Player should not be able to double down without an initial bet
    with pytest.raises(InvalidActionError):
        player.double_down()


def test_double_down_after_bust(player):
    # Place a bet
    player.place_bet(400, min_bet=10)

    # Add cards to make player bust
    player.add_card(Card(Suit.SPADES, Rank.TEN))
    player.add_card(Card(Suit.HEARTS, Rank.TEN))
    player.add_card(Card(Suit.DIAMONDS, Rank.FIVE))
    assert player.is_busted()

    # Player should not be able to double down after busting
    with pytest.raises(InvalidActionError):
        player.double_down()


def test_surrender(player):
    # Place a bet
    player.place_bet(100, min_bet=10)
    assert player.money == 900
    assert player.bets == [100]

    # Add two cards
    player.add_card(Card(Suit.HEARTS, Rank.EIGHT))
    player.add_card(Card(Suit.DIAMONDS, Rank.SEVEN))

    # Player chooses to surrender
    player.surrender()

    # Player should get half their bet back
    assert player.money == 950  # 900 + 50 (half of 100)
    assert player.bets[0] == 0  # Bet is reset
    assert player.hand_done[0] is True
    assert player.total_winnings == -50  # Lost half the bet

    # Attempt to surrender with more than two cards
    player.reset()
    player.money = 950  # Reset money to previous amount
    player.place_bet(100, min_bet=10)
    assert player.money == 850  # 950 - 100
    player.add_card(Card(Suit.HEARTS, Rank.EIGHT))
    player.add_card(Card(Suit.DIAMONDS, Rank.SEVEN))
    player.add_card(Card(Suit.CLUBS, Rank.TWO))

    with pytest.raises(InvalidActionError):
        player.surrender()

    # Money and bets should remain unchanged
    assert player.money == 850  # Money remains the same after failed surrender
    assert player.bets == [100]


def test_check_blackjack():
    # Setup io_interface and dealing_state
    io_interface = TestIOInterface()

    # Setup game and player
    rules = {
        "blackjack_payout": 1.5,
        "allow_insurance": True,
        "min_players": 1,
        "min_bet": 10,
        "max_players": 6,
        "num_decks": 6,
        "penetration": 0.75,
    }
    game = BlackjackGame(rules, io_interface)
    strategy = DealerStrategy()
    player = Player("Alice", game.io_interface, strategy)
    game.add_player(player)
    game.set_state(DealingState())

    # Setup player cards and place bet
    player.add_card(Card(Suit.HEARTS, Rank.ACE))
    player.add_card(Card(Suit.HEARTS, Rank.KING))
    initial_money = player.money
    bet_amount = 10
    player.place_bet(bet_amount, min_bet=10)

    # Check blackjack
    game.current_state.check_blackjack(game)

    # Verify payout
    expected_payout = int(bet_amount + bet_amount * game.rules["blackjack_payout"])
    assert player.money == initial_money - bet_amount + expected_payout


def test_simulation_stats_update():
    stats = SimulationStats()

    # Mock a game object
    mock_game = Mock()
    mock_player1 = Mock(winner=[])
    mock_player2 = Mock(winner=[])
    mock_game.players = [mock_player1, mock_player2]
    mock_game.io_interface = Mock()

    # Run update once and check values
    stats.update(mock_game)

    # Check that games_played is incremented
    assert stats.games_played == 1

    # Since there are no winners, wins and losses should remain zero
    assert stats.player_wins == 0
    assert stats.dealer_wins == 0
    assert stats.draws == 0
