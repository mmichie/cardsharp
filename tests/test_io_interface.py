import pytest
from cardsharp.common.io_interface import (
    DummyIOInterface,
    TestIOInterface,
    ConsoleIOInterface,
)


class MockPlayer:
    def __init__(self, name):
        self.name = name
        self.available_actions = ["action1", "action2"]

    def decide_action(self):
        return "action1"


@pytest.mark.asyncio
async def test_dummy_io_interface_methods():
    interface = DummyIOInterface()
    player = MockPlayer(name="Test")

    assert await interface.output("Test") is None
    assert await interface.get_player_action(player) == "action1"
    assert await interface.check_numeric_response((1, 5), 1, 5) is True


@pytest.mark.asyncio
async def test_test_io_interface_methods():
    interface = TestIOInterface()

    # Test output method
    await interface.output("Test")
    assert interface.sent_messages == ["Test"]

    # Test add_player_action and get_player_action methods
    interface.add_player_action("action1")
    assert await interface.get_player_action(None) == "action1"

    # Test that ValueError is raised when no more actions are available
    with pytest.raises(ValueError):
        await interface.get_player_action(None)

    # Test check_numeric_response method (here, it's left unimplemented so no need to test it)

    # Test prompt_user_action method
    interface.add_player_action("action2")
    assert await interface.prompt_user_action(None, ["action1", "action2"]) == "action2"


@pytest.mark.asyncio
async def test_console_io_interface_methods(mocker):
    interface = ConsoleIOInterface()

    # Mock the builtin input function
    mocker.patch("builtins.input", side_effect=["action1", "5"])

    # Test output method (since it uses print, we just ensure it doesn't throw an error)
    await interface.output("Test message")

    # Test get_player_action method
    player = MockPlayer(
        name="Alice"
    )  # Create a player object with a name and available actions
    assert (
        await interface.get_player_action(player) == "action1"
    )  # Pass the player object and assert that the method correctly gets the valid action

    # Test check_numeric_response method
    assert (
        await interface.check_numeric_response("Enter a number between 5 and 10: ") == 5
    )
