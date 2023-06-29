import pytest
import asyncio
from cardsharp.common.io_interface import (
    DummyIOInterface,
    TestIOInterface,
    ConsoleIOInterface,
)
from cardsharp.common.actor import SimplePlayer


class MockPlayer:
    def decide_action(self):
        return "action1"


def test_dummy_io_interface_methods():
    interface = DummyIOInterface()
    player = MockPlayer()

    assert interface.output("Test") is None
    assert interface.get_player_action(player, ["action1", "action2"]) == "action1"
    assert interface.check_numeric_response((1, 5), 1, 5) is True


def test_test_io_interface_methods():
    interface = TestIOInterface()

    # Test output method
    asyncio.run(interface.output("Test"))
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

    # Test output method (since it uses print, we just ensure it doesn't throw an error)
    interface.output("Test message")  # No asyncio.run()

    # Test get_player_action method
    player = SimplePlayer(
        name="Alice", io_interface=DummyIOInterface()
    )  # Create a player object with a name
    assert (
        asyncio.run(interface.get_player_action(player)) == "Test message"
    )  # Pass the player object
