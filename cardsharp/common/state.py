"""
This module contains the GameState class, which is an abstract base class
representing the state of a game.
"""
from abc import ABC, abstractmethod


class GameState(ABC):
    """
    An abstract base class representing the state of a game.
    """

    @abstractmethod
    def get_state(self):
        """
        Return a dictionary representing the current state of the game.
        """

    @abstractmethod
    def update_state(self, new_state):
        """
        Update the game state with new information.
        """

    @abstractmethod
    def display_stats(self):
        """
        Print out the game statistics.
        """
