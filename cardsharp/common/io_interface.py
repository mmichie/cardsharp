import asyncio
from abc import ABC, abstractmethod


class IOInterface(ABC):
    """
    Abstract base class for an IO interface.

    Methods
    -------
    @abstractmethod
    async def output(self, message: str):
        Output a message to the interface.

    @abstractmethod
    async def get_player_action(self, player: "Actor"):
        Retrieve an action from a player.

    @abstractmethod
    async def check_numeric_response(self, ctx):
        Check if a response is numeric.
    """

    @abstractmethod
    async def output(self, message: str):
        pass

    @abstractmethod
    async def get_player_action(self, player: "Actor"):  # type: ignore
        pass

    @abstractmethod
    async def check_numeric_response(self, ctx):
        pass


class DummyIOInterface(IOInterface):
    """
    A dummy IO interface for simulation purposes. Does not perform any actual IO.

    Methods
    -------
    def output(self, message):
        Simulates output operation.

    def get_player_action(self, player, actions) -> str:
        Retrieve an action from a player.

    def check_numeric_response(self, response, min_val, max_val):
        Simulates numeric response check.
    """

    def output(self, message):
        pass

    def get_player_action(self, player, actions) -> str:
        return player.decide_action()

    def check_numeric_response(self, response, min_val, max_val):
        return True


class TestIOInterface(IOInterface):
    """
    A test IO interface for testing purposes. Collects output messages and simulates input actions.

    Methods
    -------
    async def output(self, message):
        Collect an output message.

    def add_player_action(self, action: str):
        Add a player action to the queue.

    async def get_player_action(self, player: "Actor") -> str:
        Retrieve an action from a player.

    async def check_numeric_response(self, ctx):
        Simulates numeric response check.

    async def prompt_user_action(self, player: "Actor", valid_actions: list[str]) -> str:
        Prompt a player for an action.
    """

    __test__ = False

    def __init__(self):
        self.sent_messages = []
        self.player_action = None
        self.player_actions = []

    async def output(self, message):
        await asyncio.sleep(0)  # Simulate asynchronous behavior
        self.sent_messages.append(message)

    def add_player_action(self, action: str):
        self.player_actions.append(action)

    async def get_player_action(self, player: "Actor") -> str:  # type: ignore
        # Simulate player action by popping the next action from the queue
        if self.player_actions:
            return self.player_actions.pop(0)
        else:
            raise ValueError("No more actions left in TestIOInterface queue.")

    async def check_numeric_response(self, ctx):
        # You can implement this method based on your needs
        pass

    async def prompt_user_action(
        self, player: "Actor", valid_actions: list[str]  # type: ignore
    ) -> str:
        # In the test interface, prompt_user_action is equivalent to get_player_action
        return await self.get_player_action(player)


class ConsoleIOInterface(IOInterface):
    """
    A console IO interface for interactive gameplay.

    Methods
    -------
    def output(self, message: str):
        Output a message to the console.

    async def get_player_action(self, player: "Actor"):
        Retrieve an action from a player.

    async def check_numeric_response(self, ctx):
        Check if a response is numeric.

    async def prompt_user_action(self, player: "Actor", valid_actions: list[str]) -> str:
        Prompt a player for an action.
    """

    def output(self, message: str):
        print(message)

    async def get_player_action(self, player: "Actor"):  # type: ignore
        action = input(f"{player.name}, it's your turn. What's your action? ")
        return action

    async def check_numeric_response(self, ctx):
        while True:
            response = input(ctx)
            try:
                return int(response)
            except ValueError:
                print("Invalid response, please enter a number.")

    async def prompt_user_action(
        self, player: "Actor", valid_actions: list[str]  # type: ignore
    ) -> str:
        while True:
            action = await self.get_player_action(player)
            if action in valid_actions:
                return action
            print(f"Invalid action, valid actions are: {', '.join(valid_actions)}")
