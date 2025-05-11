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
from cardsharp.blackjack.rules import Rules


@pytest.fixture
def io_interface():
    return TestIOInterface()


@pytest.fixture
def rules():
    rules = Mock(spec=Rules)
    rules.min_bet = 10
    rules.max_bet = 1000
    rules.blackjack_payout = 1.5
    rules.can_split = Mock(return_value=True)
    rules.can_double_down = Mock(return_value=True)
    rules.can_insure = Mock(return_value=True)
    rules.get_max_splits = Mock(return_value=3)
    # Set up the should_dealer_hit mock to handle different cases correctly
    def should_dealer_hit_side_effect(hand):
        if not hand.cards:
            return True
        value = hand.value()
        is_soft_17 = value == 17 and hand.is_soft
        return value < 17 or (is_soft_17 and rules.dealer_hit_soft_17)

    rules.should_dealer_hit = Mock(side_effect=should_dealer_hit_side_effect)
    rules.dealer_hit_soft_17 = True
    rules.allow_split = True
    rules.allow_double_down = True
    rules.allow_insurance = True
    rules.allow_surrender = True
    rules.num_decks = 6
    return rules


@pytest.fixture
def dealer_strategy():
    return DealerStrategy()


@pytest.fixture
def mock_game(rules):
    game = Mock(spec=BlackjackGame)
    game.rules = rules
    game.visible_cards = []
    game.minimum_players = 1
    game.dealer = Mock()
    game.dealer.current_hand = BlackjackHand()
    return game


@pytest.fixture
def player(io_interface, dealer_strategy, mock_game):
    player = Player("Alice", io_interface, dealer_strategy)
    player.game = mock_game
    return player


@pytest.fixture
def dealer(io_interface):
    return Dealer("Dealer", io_interface)


def test_place_bet(player):
    assert player.money == 1000
    assert player.bets == []

    player.place_bet(100, min_bet=10)
    assert player.bets == [100]
    assert player.money == 900

    with pytest.raises(InsufficientFundsError):
        player.place_bet(1100, min_bet=10)
    assert player.bets == [100]
    assert player.money == 900


def test_place_bet_insufficient_money(player):
    with pytest.raises(InsufficientFundsError):
        player.place_bet(1100, min_bet=10)
    assert player.bets == []
    assert player.money == 1000


def test_payout(player):
    assert player.money == 1000
    assert player.bets == []
    assert player.total_winnings == 0

    player.place_bet(10, min_bet=10)
    assert player.money == 990
    assert player.bets == [10]

    player.payout(0, 20)

    assert player.money == 1010
    assert player.bets[0] == 0
    assert player.total_winnings == 10
    assert player.done is False

    player.reset()
    player.money = 1010
    player.total_winnings = 10
    player.place_bet(20, min_bet=10)
    assert player.money == 990
    player.payout(0, 50)

    assert player.money == 1040
    assert player.total_winnings == 40


def test_has_bet(player):
    assert not player.has_bet()

    player.place_bet(10, min_bet=10)
    assert player.has_bet()

    player.reset()
    assert not player.has_bet()


def test_stand(player):
    assert not player.is_done()

    player.stand()
    assert player.hand_done[player.current_hand_index] is True

    player.reset()
    assert not player.is_done()


def test_is_busted(player):
    assert not player.is_busted()

    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.add_card(Card(Suit.CLUBS, Rank.THREE))
    assert not player.is_busted()

    player.add_card(Card(Suit.SPADES, Rank.KING))
    player.add_card(Card(Suit.CLUBS, Rank.KING))
    assert player.is_busted()

    player.reset()
    assert not player.is_busted()


def test_decide_action(player, mock_game):
    player.add_card(Card(Suit.HEARTS, Rank.SIX))
    player.add_card(Card(Suit.DIAMONDS, Rank.FIVE))
    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.HIT

    player.add_card(Card(Suit.CLUBS, Rank.SIX))
    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.STAND

    player.reset()
    player.add_card(Card(Suit.HEARTS, Rank.SIX))
    player.add_card(Card(Suit.SPADES, Rank.ACE))
    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.HIT

    player.add_card(Card(Suit.CLUBS, Rank.KING))
    assert player.decide_action(Card(Suit.SPADES, Rank.TWO)) == Action.STAND


def test_buy_insurance(player, mock_game):
    assert player.money == 1000
    assert player.insurance == 0

    player.place_bet(100, min_bet=10)

    dealer_hand = BlackjackHand()
    dealer_hand.add_card(Card(Suit.HEARTS, Rank.ACE))
    mock_game.dealer.current_hand = dealer_hand

    insurance_amount = 50  # Exactly half the original bet
    player.buy_insurance(insurance_amount)
    assert player.insurance == insurance_amount
    assert player.money == 850

    with pytest.raises(ValueError):
        player.buy_insurance(51)  # More than half the original bet
    assert player.insurance == insurance_amount
    assert player.money == 850


def test_current_hand(dealer):
    assert len(dealer.current_hand.cards) == 0


def test_has_ace(dealer):
    dealer.add_card(Card(Suit.HEARTS, Rank.TWO))
    assert not dealer.has_ace()

    dealer.reset()

    dealer.add_card(Card(Suit.CLUBS, Rank.ACE))
    assert dealer.has_ace()


def test_add_card(dealer):
    dealer.add_card(Card(Suit.HEARTS, Rank.THREE))
    assert len(dealer.current_hand.cards) == 1
    assert dealer.current_hand.cards[0] == Card(Suit.HEARTS, Rank.THREE)


def test_should_hit(dealer, rules):
    # Test case for dealer hitting on soft 17
    rules.dealer_hit_soft_17 = True
    dealer.add_card(Card(Suit.HEARTS, Rank.ACE))
    dealer.add_card(Card(Suit.SPADES, Rank.SIX))
    assert dealer.should_hit(rules)  # Should hit on soft 17 when rule is True

    # Test case for dealer standing on soft 17
    rules.dealer_hit_soft_17 = False
    assert not dealer.should_hit(rules)  # Should not hit on soft 17 when rule is False


def test_invalid_action(player, mock_game):
    player.add_card(Card(Suit.HEARTS, Rank.FIVE))
    with pytest.raises(InvalidActionError):
        player.split()

    player.reset()
    # Player starts with 1000, betting 600 leaves 400
    player.place_bet(600, min_bet=10)
    assert player.money == 400
    player.add_card(Card(Suit.HEARTS, Rank.SIX))
    player.add_card(Card(Suit.DIAMONDS, Rank.FIVE))

    # Trying to double down with 600 bet needs 600 more, but only has 400
    with pytest.raises(InsufficientFundsError):
        player.double_down()


def test_dealer_should_hit(dealer, rules):
    dealer.add_card(Card(Suit.HEARTS, Rank.FOUR))
    dealer.add_card(Card(Suit.DIAMONDS, Rank.FIVE))
    assert dealer.should_hit(rules)  # Total 9, should hit

    dealer.reset()
    dealer.add_card(Card(Suit.HEARTS, Rank.TEN))
    dealer.add_card(Card(Suit.DIAMONDS, Rank.SEVEN))
    assert not dealer.should_hit(rules)  # Total 17, should not hit


def test_dealer_reset(dealer):
    dealer.add_card(Card(Suit.HEARTS, Rank.FOUR))
    dealer.add_card(Card(Suit.DIAMONDS, Rank.FIVE))

    dealer.reset()

    assert len(dealer.current_hand.cards) == 0


def test_player_split(player, mock_game):
    player.place_bet(100, min_bet=10)
    assert player.money == 900

    player.add_card(Card(Suit.HEARTS, Rank.FOUR))
    player.add_card(Card(Suit.DIAMONDS, Rank.FOUR))

    player.split()

    assert len(player.hands) == 2
    assert len(player.hands[0].cards) == 1
    assert len(player.hands[1].cards) == 1
    assert player.bets == [100, 100]
    assert player.money == 800


def test_player_add_card(player):
    card = Card(Suit.HEARTS, Rank.TWO)
    player.add_card(card)
    assert player.current_hand.cards[-1] == card


def test_player_reset(player):
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.place_bet(10, min_bet=10)
    player.reset()
    assert len(player.current_hand.cards) == 0
    assert player.bets == []
    assert not player.done


def test_player_dealer_interaction(player, dealer, mock_game):
    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.add_card(Card(Suit.HEARTS, Rank.THREE))
    dealer.add_card(Card(Suit.SPADES, Rank.TEN))
    dealer.add_card(Card(Suit.SPADES, Rank.NINE))

    action = player.decide_action(dealer.current_hand.cards[0])
    if action == Action.HIT:
        player.add_card(Card(Suit.HEARTS, Rank.FOUR))
    elif action == Action.STAND:
        while dealer.should_hit(mock_game.rules):
            dealer.add_card(Card(Suit.SPADES, Rank.TWO))

    assert player.current_hand.value() <= 21
    assert dealer.current_hand.value() <= 21


def test_valid_actions(player):
    player.reset()

    assert player.valid_actions == []

    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    assert set(player.valid_actions) == set([Action.HIT, Action.STAND])


def test_split_sufficient_funds(player, mock_game):
    player.place_bet(500, min_bet=10)
    assert player.money == 500

    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.add_card(Card(Suit.DIAMONDS, Rank.TWO))

    player.split()

    assert len(player.hands) == 2
    assert len(player.hands[0].cards) == 1
    assert len(player.hands[1].cards) == 1
    assert player.bets == [500, 500]
    assert player.money == 0
    assert player.total_bets == 1000


def test_split_insufficient_funds(player, mock_game):
    player.place_bet(600, min_bet=10)
    assert player.money == 400

    player.add_card(Card(Suit.HEARTS, Rank.TWO))
    player.add_card(Card(Suit.DIAMONDS, Rank.TWO))

    with pytest.raises(InsufficientFundsError):
        player.split()

    assert len(player.hands) == 1
    assert len(player.hands[0].cards) == 2
    assert player.bets == [600]
    assert player.money == 400
    assert player.total_bets == 600


def test_double_down_insufficient_funds(player, mock_game):
    # Player starts with 1000, betting 600 leaves 400
    player.place_bet(600, min_bet=10)
    assert player.money == 400

    player.add_card(Card(Suit.HEARTS, Rank.NINE))
    player.add_card(Card(Suit.DIAMONDS, Rank.TWO))

    # Trying to double down with 600 bet needs 600 more, but only has 400
    with pytest.raises(InsufficientFundsError):
        player.double_down()

    assert player.money == 400
    assert player.bets == [600]


def test_double_down_valid_bet(player, mock_game):
    player.place_bet(400, min_bet=10)
    assert player.money == 600

    player.add_card(Card(Suit.HEARTS, Rank.NINE))
    player.add_card(Card(Suit.DIAMONDS, Rank.TWO))

    player.double_down()

    assert player.money == 200
    assert player.bets == [800]
    assert player.total_bets == 800


def test_double_down_after_bust(player, mock_game):
    player.place_bet(400, min_bet=10)

    player.add_card(Card(Suit.SPADES, Rank.TEN))
    player.add_card(Card(Suit.HEARTS, Rank.TEN))
    player.add_card(Card(Suit.DIAMONDS, Rank.FIVE))
    assert player.is_busted()

    with pytest.raises(InvalidActionError):
        player.double_down()


def test_surrender(player):
    player.place_bet(100, min_bet=10)
    assert player.money == 900
    assert player.bets == [100]

    player.add_card(Card(Suit.HEARTS, Rank.EIGHT))
    player.add_card(Card(Suit.DIAMONDS, Rank.SEVEN))

    player.surrender()

    assert player.money == 950
    assert player.bets[0] == 0
    assert player.hand_done[0] is True
    assert player.total_winnings == -50

    player.reset()
    player.money = 950
    player.place_bet(100, min_bet=10)
    assert player.money == 850
    player.add_card(Card(Suit.HEARTS, Rank.EIGHT))
    player.add_card(Card(Suit.DIAMONDS, Rank.SEVEN))
    player.add_card(Card(Suit.CLUBS, Rank.TWO))

    with pytest.raises(InvalidActionError):
        player.surrender()

    assert player.money == 850
    assert player.bets == [100]

    stats = SimulationStats()

    mock_game = Mock()
    mock_player1 = Mock(winner=[])
    mock_player2 = Mock(winner=[])
    mock_game.players = [mock_player1, mock_player2]
    mock_game.io_interface = Mock()

    stats.update(mock_game)

    assert stats.games_played == 1
    assert stats.player_wins == 0
    assert stats.dealer_wins == 0
    assert stats.draws == 0


def test_payout_insurance(player):
    player.money = 1000
    player.insurance = 50

    # Insurance pays 2:1, so winning 50 should pay 100
    player.payout_insurance(
        150
    )  # Total payout includes original bet (50) plus winnings (100)
    assert player.money == 1150
    assert player.insurance == 0
    assert player.total_winnings == 100


def test_multiple_hands_tracking(player):
    # Test handling of multiple hands after split
    player.place_bet(100, min_bet=10)
    player.add_card(Card(Suit.HEARTS, Rank.EIGHT))
    player.add_card(Card(Suit.DIAMONDS, Rank.EIGHT))

    # Split the hand
    player.split()

    assert len(player.hands) == 2
    assert len(player.hand_done) == 2
    assert all(not done for done in player.hand_done)
    assert player.current_hand_index == 0

    # Complete first hand
    player.stand()
    assert player.hand_done[0] is True
    assert not player.hand_done[1]

    # Move to second hand
    player.current_hand_index = 1
    player.stand()
    assert all(done for done in player.hand_done)


def test_bust_tracking(player):
    player.place_bet(100, min_bet=10)

    # Add cards until bust
    player.add_card(Card(Suit.HEARTS, Rank.TEN))
    player.add_card(Card(Suit.DIAMONDS, Rank.EIGHT))
    player.add_card(Card(Suit.CLUBS, Rank.FIVE))

    # Total value is 23, should be busted
    assert player.current_hand.value() > 21
    assert player.is_busted()
    assert player.hand_done[player.current_hand_index]


def test_valid_actions_with_split(player, mock_game):
    player.place_bet(100, min_bet=10)

    # Add pair of cards
    player.add_card(Card(Suit.HEARTS, Rank.EIGHT))
    player.add_card(Card(Suit.DIAMONDS, Rank.EIGHT))

    valid_actions = player.valid_actions
    assert Action.SPLIT in valid_actions
    assert Action.HIT in valid_actions
    assert Action.STAND in valid_actions
    assert Action.DOUBLE in valid_actions


def test_can_afford_edge_cases(player):
    # Test exact amount
    assert player.can_afford(1000)

    # Test one over
    assert not player.can_afford(1001)

    # Test zero
    assert player.can_afford(0)

    # Test negative amount (should return True as it's not a valid case)
    assert player.can_afford(-1)


def test_multiple_split_tracking(player, mock_game):
    player.place_bet(100, min_bet=10)

    # First split
    player.add_card(Card(Suit.HEARTS, Rank.EIGHT))
    player.add_card(Card(Suit.DIAMONDS, Rank.EIGHT))
    player.split()

    assert len(player.hands) == 2
    assert len(player.bets) == 2
    assert player.bets == [100, 100]

    # Second split
    player.add_card(Card(Suit.CLUBS, Rank.EIGHT))
    player.split()

    assert len(player.hands) == 3
    assert len(player.bets) == 3
    assert player.bets == [100, 100, 100]
    assert player.money == 700


def test_blackjack_detection(player):
    player.place_bet(100, min_bet=10)

    # Deal blackjack
    player.add_card(Card(Suit.HEARTS, Rank.ACE))
    player.add_card(Card(Suit.DIAMONDS, Rank.KING))

    assert player.current_hand.is_blackjack
    assert player.current_hand.value() == 21


def test_soft_hand_detection(player):
    player.add_card(Card(Suit.HEARTS, Rank.ACE))
    player.add_card(Card(Suit.DIAMONDS, Rank.SIX))

    assert player.current_hand.is_soft
    assert player.current_hand.value() == 17

    player.add_card(Card(Suit.CLUBS, Rank.FIVE))
    assert not player.current_hand.is_soft
    assert player.current_hand.value() == 12


def test_hand_value_with_multiple_aces(player):
    # Test multiple aces handling
    player.add_card(Card(Suit.HEARTS, Rank.ACE))
    player.add_card(Card(Suit.DIAMONDS, Rank.ACE))
    player.add_card(Card(Suit.CLUBS, Rank.ACE))

    assert player.current_hand.value() == 13
