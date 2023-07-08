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
        pass

    @abstractmethod
    def update_state(self, new_state):
        """
        Update the game state with new information.
        """
        pass

    @abstractmethod
    def display_stats(self):
        """
        Print out the game statistics.
        """
        pass
