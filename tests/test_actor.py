from cardsharp.common.hand import Hand
from cardsharp.common.actor import SimplePlayer


def test_simple_player_initialization():
    player = SimplePlayer("John Doe")

    assert player.name == "John Doe"
    assert len(player.hands) == 1
    assert isinstance(player.hands[0], Hand)
    assert player.money == 1000


def test_simple_player_reset_hands():
    player = SimplePlayer("John Doe")
    player.reset_hands()

    assert len(player.hands) == 1
    assert isinstance(player.hands[0], Hand)


def test_simple_player_update_money():
    player = SimplePlayer("John Doe")
    player.update_money(200)

    assert player.money == 1200


def test_simple_player_display_message(capsys):
    player = SimplePlayer("John Doe")
    player.display_message("Hello World!")

    captured = capsys.readouterr()  # capture print output

    assert captured.out == "John Doe: Hello World!\n"
