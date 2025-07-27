"""
This module contains the IOInterface abstract base class and its implementations.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import aiofiles

from cardsharp.blackjack.action import Action

if TYPE_CHECKING:
    from cardsharp.common.actor import Actor


class IOInterface(ABC):
    """
    Abstract base class for an IO interface.

    This class defines the interface for input/output operations in the game.
    Subclasses can be either synchronous or asynchronous.
    """

    @abstractmethod
    def output(self, message: str) -> None:
        """Output a message to the interface."""
        pass

    @abstractmethod
    def input(self, prompt: str) -> str:
        """Get input from the user with a prompt."""
        pass

    @abstractmethod
    def get_player_action(
        self, player: Actor, valid_actions: list[Action], time_limit: int = 0
    ) -> Action:
        """Retrieve an action from a player with optional time limit in seconds."""
        pass

    @abstractmethod
    def check_numeric_response(self, ctx: str) -> int:
        """Check if a response is numeric and return the integer value."""
        pass


class DummyIOInterface(IOInterface):
    """
    A dummy IO interface for simulation purposes. Does not perform any actual IO.

    Methods
    -------
    def output(self, message):
        Simulates output operation.

    def input(self, prompt):
        Simulates input operation.

    def get_player_action(self, player, actions) -> str:
        Retrieve an action from a player.

    def check_numeric_response(self, response, min_val, max_val):
        Simulates numeric response check.
    """

    def output(self, message: str) -> None:
        """Simulates output operation."""
        pass

    def input(self, prompt: str) -> str:
        """Simulates input operation."""
        return ""

    def get_player_action(
        self, player: Actor, valid_actions: list[Action], time_limit: int = 0
    ) -> Action:
        if valid_actions:
            return valid_actions[0]  # Default to the first valid action
        else:
            raise ValueError("No valid actions available.")

    def check_numeric_response(self, ctx: str) -> int:
        """Always returns 1 for simulation."""
        return 1


class TestIOInterface(IOInterface):
    """
    A test IO interface for testing purposes. Collects output messages and simulates input actions.

    Methods
    -------
    def output(self, message):
        Collect an output message.

    def input(self, prompt):
        Return a test input.

    def add_player_action(self, action: str):
        Add a player action to the queue.

    def get_player_action(self, player: "Actor") -> str:
        Retrieve an action from a player.

    def check_numeric_response(self, ctx):
        Simulates numeric response check.

    def prompt_user_action(self, player: "Actor", valid_actions: list[str]) -> str:
        Prompt a player for an action.
    """

    __test__ = False

    def __init__(self):
        self.sent_messages = []
        self.player_actions = []
        self.input_responses = []

    def output(self, message: str) -> None:
        self.sent_messages.append(message)

    def input(self, prompt: str) -> str:
        if self.input_responses:
            return self.input_responses.pop(0)
        return "test_input"

    def add_player_action(self, action: Action):
        """Add a player action to the queue."""
        self.player_actions.append(action)

    def get_player_action(
        self, player: Actor, valid_actions: list[Action], time_limit: int = 0
    ) -> Action:
        if self.player_actions:
            return self.player_actions.pop(0)
        else:
            raise ValueError("No more actions left in TestIOInterface queue.")

    def check_numeric_response(self, ctx: str) -> int:
        """Returns 1 for testing."""
        return 1

    def prompt_user_action(
        self, player: Actor, valid_actions: list[Action], time_limit: int = 0
    ) -> Action:
        """Prompt a player for an action."""
        return self.get_player_action(player, valid_actions, time_limit)


class ConsoleIOInterface(IOInterface):
    """
    A console IO interface for interactive gameplay.

    Methods
    -------
    def output(self, message: str):
        Output a message to the console.

    def input(self, prompt: str):
        Get input from the console.

    def get_player_action(self, player: "Actor", valid_actions: list[str]):
        Retrieve an action from a player and check if it's valid.

    def check_numeric_response(self, ctx):
        Check if a response is numeric.
    """

    def output(self, message: str) -> None:
        print(message)

    def input(self, prompt: str) -> str:
        return input(prompt)

    def get_player_action(
        self, player: Actor, valid_actions: list[Action], time_limit: int = 0
    ) -> Action:
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError("Time limit expired")

        attempts = 0
        while attempts < 3:  # Setting a maximum number of attempts
            # If time limit is set, configure the alarm
            if time_limit > 0:
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(time_limit)  # Set alarm for time_limit seconds
                print(f"You have {time_limit} seconds to decide...")

            try:
                action_input = input(
                    f"{player.name}, it's your turn. What's your action? "
                ).lower()

                # Reset the alarm
                if time_limit > 0:
                    signal.alarm(0)

                for action in Action:
                    if action_input == action.name.lower() and action in valid_actions:
                        return action

                print(
                    f"Invalid action, valid actions are: {', '.join([a.name for a in valid_actions])}"
                )
                attempts += 1

            except TimeoutError:
                # Time limit expired
                print("Time limit expired! Defaulting to STAND.")
                return (
                    Action.STAND if Action.STAND in valid_actions else valid_actions[0]
                )

        raise Exception("Too many invalid attempts. Game aborted.")

    def check_numeric_response(self, ctx: str) -> int:
        attempts = 0
        while attempts < 3:  # Setting a maximum number of attempts
            response = input(ctx)
            try:
                return int(response)
            except ValueError:
                print("Invalid response, please enter a number.")
                attempts += 1
        raise Exception("Too many invalid responses. Operation aborted.")


class LoggingIOInterface(IOInterface):
    """
    A logging IO interface for recording purposes. Writes output messages to a log file.

    This class provides a hybrid sync/async approach where output is written to a file
    and input is simulated.
    """

    def __init__(self, log_file_path: str):
        self.log_file_path = log_file_path
        self._loop = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    def output(self, message: str) -> None:
        """Write an output message to the log file."""
        with open(self.log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write(message + "\n")

    def input(self, prompt: str) -> str:
        """Log the prompt and return empty string."""
        self.output(f"[INPUT PROMPT] {prompt}")
        return ""

    def get_player_action(
        self, player: Actor, valid_actions: list[Action], time_limit: int = 0
    ) -> Action:
        """Get player action using their strategy."""
        if hasattr(player, "decide_action"):
            return player.decide_action(valid_actions)
        return valid_actions[0] if valid_actions else Action.STAND

    def check_numeric_response(self, ctx: str) -> int:
        """Always returns 1 for logging interface."""
        self.output(f"[NUMERIC PROMPT] {ctx}")
        return 1

    async def output_async(self, message: str) -> None:
        """Async version of output for compatibility."""
        async with aiofiles.open(
            self.log_file_path, mode="a", encoding="utf-8"
        ) as log_file:
            await log_file.write(message + "\n")

    async def get_player_action_async(
        self, player: Actor, valid_actions: list[Action], time_limit: int = 0
    ) -> Action:
        """Async version of get_player_action."""
        await asyncio.sleep(0)
        return self.get_player_action(player, valid_actions, time_limit)


class AsyncIOInterfaceWrapper:
    """
    A wrapper class to facilitate asynchronous execution of synchronous IO operations
    defined in an IOInterface implementation. This class uses a ThreadPoolExecutor to
    run synchronous methods in separate threads, allowing them to be awaited in an
    asynchronous context. This enables seamless integration of synchronous IO operations
    into asynchronous codebases, such as asynchronous web frameworks or chatbots.
    """

    def __init__(self, io_interface: IOInterface):
        self.io_interface = io_interface
        self.executor = ThreadPoolExecutor()

    async def output(self, message: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.executor, self.io_interface.output, message)

    async def input(self, prompt: str) -> str:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            self.executor, self.io_interface.input, prompt
        )
        return result

    async def get_player_action(
        self, player: Actor, valid_actions: list[Action], time_limit: int = 0
    ) -> Action:
        loop = asyncio.get_running_loop()
        action = await loop.run_in_executor(
            self.executor,
            self.io_interface.get_player_action,
            player,
            valid_actions,
            time_limit,
        )
        return action

    async def check_numeric_response(self, ctx: str) -> int:
        loop = asyncio.get_running_loop()
        numeric_response = await loop.run_in_executor(
            self.executor, self.io_interface.check_numeric_response, ctx
        )
        return numeric_response
