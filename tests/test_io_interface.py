import pytest
import asyncio
from cardsharp.common.io_interface import (
    DummyIOInterface,
    TestIOInterface,
    ConsoleIOInterface,
)
from cardsharp.common.actor import SimplePlayer


def test_dummy_io_interface_methods():
    interface = DummyIOInterface()

    assert asyncio.run(interface.display_message("Test")) is None
    assert asyncio.run(interface.send_message("Test")) is None
    assert (
        asyncio.run(interface.get_player_action(None, ["action1", "action2"]))
        == "action1"
    )
    assert asyncio.run(interface.check_numeric_response((1, 5), 1, 5)) is True


def test_test_io_interface_methods():
    interface = TestIOInterface()

    # Test send_message method
    asyncio.run(interface.send_message("Test"))
    assert interface.sent_messages == ["Test"]

    # Test add_player_action and get_player_action methods
    interface.add_player_action("action1")
    assert asyncio.run(interface.get_player_action(None)) == "action1"

    # Test that ValueError is raised when no more actions are available
    with pytest.raises(ValueError):
        asyncio.run(interface.get_player_action(None))

    # Test check_numeric_response method (here, it's left unimplemented so no need to test it)

    # Test prompt_user_action method
    interface.add_player_action("action2")
    assert (
        asyncio.run(interface.prompt_user_action(None, ["action1", "action2"]))
        == "action2"
    )


def test_console_io_interface_methods(mocker):
    interface = ConsoleIOInterface()

    # Mock the builtin input function
    mocker.patch("builtins.input", side_effect=["Test message", "action1", "5"])

    # Test send_message method (since it uses print, we just ensure it doesn't throw an error)
    asyncio.run(interface.send_message("Test message"))

    # Test get_player_action method
    player = SimplePlayer(
        name="Alice", io_interface=DummyIOInterface()
    )  # Create a player object with a name
    assert (
        asyncio.run(interface.get_player_action(player)) == "Test message"
    )  # Pass the player object