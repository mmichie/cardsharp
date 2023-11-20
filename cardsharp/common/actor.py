"""
This module contains the Actor abstract base class and a SimplePlayer concrete
class which extends from Actor.

Actor serves as a blueprint for any individual participating in a card game,
containing methods and attributes that allow the actor to perform actions and
manage their own state within the game. The module also includes a SimplePlayer
class that is a specific implementation of Actor, representing a simple player
in the game.

The classes and methods within this module can be utilized to create actors in
any card game, with the ability to reset their state, update their money,
display messages, and manage multiple hands

The Actor class is meant to be extended by other concrete classes to create more
complex players or dealer types. The SimplePlayer class can be used as is for
simple card games, or can serve as a starting point for creating more complex
player types.
"""

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
        self.current_hand_index = 0

    @property
    def current_hand(self):
        """
        The actor's current hand.
        """
        return self.hands[self.current_hand_index]

    @abstractmethod
    def reset(self):
        """
        Reset the actor's hands and money

        :return: None
        """

    @abstractmethod
    def update_money(self, amount: int):
        """
        Update the actor's money by a specified amount.

        :param amount: The amount to update the actor's money by
        :return: None
        """

    @abstractmethod
    async def display_message(self, message: str):
        """
        Display a message from the actor.

        :param message: The message to display
        :return: None
        """


class SimplePlayer(Actor):
    """
    A simple player in a card game, extending from the Actor abstract base class.
    """

    def reset(self):
        """
        Resets the player's hands and money

        :return: None
        """
        self.hands = [Hand()]
        self.current_hand_index = 0  # reset current hand index as well
        self.money = 1000

    def update_money(self, amount: int):
        """
        Update the player's money by a specified amount.

        :param amount: The amount to update the player's money by
        :return: None
        """
        self.money += amount

    def display_message(self, message: str):
        """
        Sends a message from the player to the IO interface.

        :param message: The message to send
        :return: None
        """
        self.io_interface.output(f"{self.name}: {message}")

    def next_hand(self):
        """
        Switch to the next hand.

        :return: None
        """
        self.current_hand_index = (self.current_hand_index + 1) % len(
            self.hands
        )  # wraps around if it's the last hand

    def receive_card(self, card):
        """
        Add a new card to the player's current hand.

        :param card: The card to add to the player's current hand
        :return: None
        """
        self.current_hand.add_card(card)
