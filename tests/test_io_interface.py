import pytest
from cardsharp.common.io_interface import (
    DummyIOInterface,
    TestIOInterface,
    ConsoleIOInterface,
)
from cardsharp.blackjack.action import Action


class MockPlayer:
    def __init__(self, name):
        self.name = name
        self.available_actions = ["action1", "action2"]

    def decide_action(self, valid_actions):
        return valid_actions[0]  # Simply return the first valid action


def test_dummy_io_interface_methods():
    interface = DummyIOInterface()
    player = MockPlayer(name="Test")

    assert interface.output("Test") is None
    assert interface.input("prompt") == ""
    assert (
        interface.get_player_action(player, player.available_actions)
        == player.available_actions[0]
    )
    assert interface.check_numeric_response("Enter a number: ") == 1


def test_console_io_interface_methods(mocker):
    interface = ConsoleIOInterface()

    # Mock the builtin input function
    mocker.patch(
        "builtins.input", side_effect=["test_input", Action.HIT.name.lower(), "5"]
    )

    # Test output method (since it uses print, we just ensure it doesn't throw an error)
    interface.output("Test message")

    # Test input method
    assert interface.input("Enter something: ") == "test_input"

    # Test get_player_action method
    player = MockPlayer(
        name="Alice"
    )  # Create a player object with a name and available actions
    assert (
        interface.get_player_action(player, [Action.HIT]) == Action.HIT
    )  # Pass the player object and assert that the method correctly gets the valid action

    # Test check_numeric_response method
    assert interface.check_numeric_response("Enter a number between 5 and 10: ") == 5


def test_test_io_interface_methods():
    interface = TestIOInterface()

    # Test output method
    interface.output("Test")
    assert interface.sent_messages == ["Test"]

    # Test add_player_action and get_player_action methods
    interface.add_player_action("action1")
    assert interface.get_player_action(None, ["action1", "action2"]) == "action1"

    # Test that ValueError is raised when no more actions are available
    with pytest.raises(ValueError):
        interface.get_player_action(None, ["action1", "action2"])

    # Test check_numeric_response method (here, it's left unimplemented so no need to test it)

    # Test prompt_user_action method
    interface.add_player_action("action2")
    assert interface.prompt_user_action(None, ["action1", "action2"]) == "action2"
