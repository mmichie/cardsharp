import pytest
from cardsharp.common.card import Card, Rank, Suit
from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.blackjack.state import DealingState
from cardsharp.common.io_interface import TestIOInterface
from typing import Coroutine


@pytest.fixture
def io_interface():
    return TestIOInterface()


@pytest.fixture
def dealing_state():
    return DealingState()


@pytest.fixture
def game(io_interface, dealing_state):
    rules = {
        "blackjack_payout": 1.5,
        "allow_insurance": True,
        "min_players": 1,
        "min_bet": 10,
        "max_players": 6,
    }
    game = BlackjackGame(rules, io_interface)
    player = Player("Alice", game.io_interface)
    game.add_player(player)
    game.set_state(dealing_state)

    player.add_card(Card(Suit.HEARTS, Rank.ACE))
    player.add_card(Card(Suit.HEARTS, Rank.KING))
    player.place_bet(10)

    return game


def test_check_blackjack(game):
    # Call the method under test
    assert game.players[0].hands[0].cards[0] == Card(Suit.HEARTS, Rank.ACE)
    assert game.players[0].hands[0].cards[1] == Card(Suit.HEARTS, Rank.KING)
    game.current_state.check_blackjack(game)
    assert game.players[0].is_done()  # Player should be done after getting a blackjack

    # Check the results
    assert (
        game.players[0].money == 1000 + 10 * 1.5
    )  # Player's initial money is 1000 and they were paid 1.5 times their bet
