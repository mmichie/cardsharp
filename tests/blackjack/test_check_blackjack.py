from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.blackjack.state import DealingState
from cardsharp.blackjack.strategy import DealerStrategy
from cardsharp.common.card import Card, Rank, Suit
from cardsharp.common.io_interface import TestIOInterface


def test_check_blackjack():
    # setup io_interface and dealing_state
    io_interface = TestIOInterface()
    DealingState()

    # setup game and player
    rules = {
        "blackjack_payout": 1.5,
        "allow_insurance": True,
        "min_players": 1,
        "min_bet": 10,
        "max_players": 6,
    }
    game = BlackjackGame(rules, io_interface)
    strategy = DealerStrategy()
    player = Player("Alice", game.io_interface, strategy)
    game.add_player(player)
    game.set_state(DealingState())

    # setup player cards and place bet
    player.add_card(Card(Suit.HEARTS, Rank.ACE))
    player.add_card(Card(Suit.HEARTS, Rank.KING))
    player.place_bet(10)

    # Call the method under test
    assert game.players[0].hands[0].cards[0] == Card(Suit.HEARTS, Rank.ACE)
    assert game.players[0].hands[0].cards[1] == Card(Suit.HEARTS, Rank.KING)
    game.current_state.check_blackjack(  # type: ignore
        game
    )  # Assuming check_blackjack() is a coroutine
    assert game.players[0].is_done()  # Player should be done after getting a blackjack

    # Check the results
    assert (
        game.players[0].money == 1000 + 10 * 1.5
    )  # Player's initial money is 1000 and they were paid 1.5 times their bet
