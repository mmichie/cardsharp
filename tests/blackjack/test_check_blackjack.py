from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.blackjack.state import DealingState
from cardsharp.blackjack.strategy import DealerStrategy
from cardsharp.common.card import Card, Rank, Suit
from cardsharp.common.io_interface import TestIOInterface


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

    # Verify initial state
    assert player.money == initial_money - bet_amount
    assert player.bets[0] == bet_amount
    assert game.players[0].hands[0].cards[0] == Card(Suit.HEARTS, Rank.ACE)
    assert game.players[0].hands[0].cards[1] == Card(Suit.HEARTS, Rank.KING)

    # Check the hand value and blackjack status
    assert player.current_hand.value() == 21, "Player's hand value should be 21"
    assert player.current_hand.is_blackjack, "Player should have a blackjack"

    # Call the method under test
    game.current_state.check_blackjack(game)

    # Check the results
    assert player.is_done(), "Player should be done after getting a blackjack"
    expected_payout = bet_amount + int(bet_amount * rules["blackjack_payout"])
    assert player.money == initial_money - bet_amount + expected_payout
    assert player.bets[0] == 0, "Bet should be reset after payout"
