import asyncio
from cardsharp.common.hand import Hand
from cardsharp.common.actor import SimplePlayer
from cardsharp.common.io_interface import TestIOInterface


def test_simple_player_initialization():
    io_interface = TestIOInterface()
    player = SimplePlayer("John Doe", io_interface)

    assert player.name == "John Doe"
    assert len(player.hands) == 1
    assert isinstance(player.hands[0], Hand)
    assert player.money == 1000
    assert player.io_interface == io_interface
    assert player.current_hand == player.hands[0]  # added this line


def test_simple_player_reset():
    io_interface = TestIOInterface()
    player = SimplePlayer("John Doe", io_interface)
    player.hands.append(Hand())
    player.next_hand()  # switch to the second hand
    player.reset()

    assert len(player.hands) == 1
    assert isinstance(player.hands[0], Hand)
    assert player.current_hand == player.hands[0]  # added this line


def test_simple_player_update_money():
    io_interface = TestIOInterface()
    player = SimplePlayer("John Doe", io_interface)
    player.update_money(200)

    assert player.money == 1200


def test_simple_player_display_message():
    io_interface = TestIOInterface()
    player = SimplePlayer("John Doe", io_interface)
    asyncio.run(player.display_message("Hello World!"))  # run async function

    assert io_interface.sent_messages == ["John Doe: Hello World!"]


def test_next_hand():
    io_interface = TestIOInterface()
    player = SimplePlayer("John Doe", io_interface)
    hand1 = player.current_hand
    player.hands.append(Hand())
    player.next_hand()
    hand2 = player.current_hand
    assert hand1 != hand2
    player.next_hand()
    hand1_again = player.current_hand
    assert hand1 == hand1_again  # it should wrap around to the first hand


def test_multiple_hands_switching():
    io_interface = TestIOInterface()
    player = SimplePlayer("John Doe", io_interface)

    hand1 = player.current_hand
    player.hands.append(Hand())
    player.hands.append(Hand())

    player.next_hand()
    hand2 = player.current_hand
    assert hand1 != hand2

    player.next_hand()
    hand3 = player.current_hand
    assert hand1 != hand3 and hand2 != hand3

    player.next_hand()
    assert player.current_hand == hand1  # it should wrap around to the first hand


def test_adding_new_hand():
    io_interface = TestIOInterface()
    player = SimplePlayer("John Doe", io_interface)

    hand1 = player.current_hand
    player.hands.append(Hand())

    player.next_hand()
    hand2 = player.current_hand
    assert hand1 != hand2

    player.hands.append(Hand())  # add a new hand

    player.next_hand()
    hand3 = player.current_hand
    assert hand1 != hand3 and hand2 != hand3
