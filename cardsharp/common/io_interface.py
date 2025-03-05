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
        """Output a message to the interface."""

    @abstractmethod
    async def get_player_action(
        self, player: Actor, valid_actions: list[Action], time_limit: int = 0
    ) -> Action:
        """Retrieve an action from a player with optional time limit in seconds."""

    @abstractmethod
    async def check_numeric_response(self, ctx):
        """Check if a response is numeric."""


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
        """Simulates output operation."""
        pass

    def get_player_action(
        self, player: Actor, valid_actions: list[Action], time_limit: int = 0
    ) -> Action:
        if valid_actions:
            return valid_actions[0]  # Default to the first valid action
        else:
            raise ValueError("No valid actions available.")

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
        self.player_actions = []

    def output(self, message):
        self.sent_messages.append(message)

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

    def check_numeric_response(self, ctx):
        pass

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

    def get_player_action(self, player: "Actor", valid_actions: list[str]):
        Retrieve an action from a player and check if it's valid.

    def check_numeric_response(self, ctx):
        Check if a response is numeric.
    """

    def output(self, message: str):
        print(message)

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
                print(f"Time limit expired! Defaulting to STAND.")
                return (
                    Action.STAND if Action.STAND in valid_actions else valid_actions[0]
                )

        raise Exception("Too many invalid attempts. Game aborted.")

    def check_numeric_response(self, ctx):
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

    Methods
    -------
    async def output(self, message):
        Write an output message to the log file.

    async def get_player_action(self, player: "Actor") -> str:
        Retrieve an action from a player.

    async def check_numeric_response(self, ctx):
        Simulates numeric response check.
    """

    def __init__(self, log_file_path):
        self.log_file_path = log_file_path

    async def output(self, message):
        async with aiofiles.open(
            self.log_file_path, mode="a", encoding="utf-8"
        ) as log_file:
            await log_file.write(message + "\n")
        await asyncio.sleep(0)  # Yield control to the event loop

    async def get_player_action(
        self, player: Actor, valid_actions: list[Action], time_limit: int = 0
    ) -> Action:
        await asyncio.sleep(0)
        return player.decide_action(valid_actions)

    async def check_numeric_response(self, ctx):
        await asyncio.sleep(0)  # Simulate asynchronous behavior


class AsyncIOInterfaceWrapper:
    """
    A wrapper class to facilitate asynchronous execution of synchronous IO operations
    defined in an IOInterface implementation. This class uses a ThreadPoolExecutor to
    run synchronous methods in separate threads, allowing them to be awaited in an
    asynchronous context. This enables seamless integration of synchronous IO operations
    into asynchronous codebases, such as asynchronous web frameworks or chatbots.
    """

    def __init__(self, io_interface):
        self.io_interface = io_interface
        self.executor = ThreadPoolExecutor()

    async def output(self, message: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.executor, self.io_interface.output, message)

    async def get_player_action(self, player, valid_actions, time_limit: int = 0):
        loop = asyncio.get_running_loop()
        action = await loop.run_in_executor(
            self.executor,
            self.io_interface.get_player_action,
            player,
            valid_actions,
            time_limit,
        )
        return action

    async def check_numeric_response(self, ctx):
        loop = asyncio.get_running_loop()
        numeric_response = await loop.run_in_executor(
            self.executor, self.io_interface.check_numeric_response, ctx
        )
        return numeric_response
