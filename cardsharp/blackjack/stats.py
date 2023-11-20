"""
This module contains the SimulationStats class which is responsible for
tracking and updating the statistics of the blackjack game simulation.
"""


class SimulationStats:
    """
    A class that holds the statistics of the simulation.
    """

    def __init__(self):
        """
        Initializes the SimulationStats with default values.
        """
        self.games_played = 0
        self.player_wins = 0
        self.dealer_wins = 0
        self.draws = 0

    def update(self, game):
        """
        Updates the statistics based on the current state of the game.
        """
        self.games_played += 1

        game.io_interface.output("Updating statistics...")
        player_win = any(player.winner == "player" for player in game.players)
        dealer_win = any(player.winner == "dealer" for player in game.players)
        draw = any(player.winner == "draw" for player in game.players)

        if player_win:
            self.player_wins += 1
        if dealer_win:
            self.dealer_wins += 1
        if draw:
            self.draws += 1

        # Reset the winners for next game
        for player in game.players:
            player.winner = None

    def report(self):
        """
        Returns a dictionary containing the current statistics.
        """
        return {
            "games_played": self.games_played,
            "player_wins": self.player_wins,
            "dealer_wins": self.dealer_wins,
            "draws": self.draws,
        }
