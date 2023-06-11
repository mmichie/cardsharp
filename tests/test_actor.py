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


def test_simple_player_reset_hands():
    io_interface = TestIOInterface()
    player = SimplePlayer("John Doe", io_interface)
    player.reset_hands()

    assert len(player.hands) == 1
    assert isinstance(player.hands[0], Hand)


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

