from abc import ABC, abstractmethod

from cardsharp.common.hand import Hand
from cardsharp.common.io_interface import IOInterface


class Actor(ABC):
    """
    Abstract base class representing an actor in a card game.

    :param name: Name of the actor
    :param initial_money: Initial amount of money actor has
    :param deck: The deck of cards the actor uses
    """

    def __init__(self, name: str, io_interface: IOInterface, initial_money: int = 1000):
        self.name = name
        self.hands = [Hand()]
        self.money = initial_money
        self.io_interface = io_interface

    @abstractmethod
    def reset_hands(self):
        """
        Reset the actor's hands to an empty state.

        :return: None
        """
        pass

    @abstractmethod
    def update_money(self, amount: int):
        """
        Update the actor's money by a specified amount.

        :param amount: The amount to update the actor's money by
        :return: None
        """
        pass

    @abstractmethod
    async def display_message(self, message: str):
        """
        Display a message from the actor.

        :param message: The message to display
        :return: None
        """
        pass


class SimplePlayer(Actor):
    """
    A simple player in a card game, extending from the Actor abstract base class.
    """

    def reset_hands(self):
        """
        Resets the player's hands to an empty state.

        :return: None
        """
        self.hands = [Hand()]

    def update_money(self, amount: int):
        """
        Update the player's money by a specified amount.

        :param amount: The amount to update the player's money by
        :return: None
        """
        self.money += amount

    async def display_message(self, message: str):
        """
        Sends a message from the player to the IO interface.

        :param message: The message to send
        :return: None
        """
        await self.io_interface.send_message(f"{self.name}: {message}")
