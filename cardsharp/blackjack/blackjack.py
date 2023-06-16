import argparse
from cardsharp.blackjack.actor import Dealer, Player
from cardsharp.blackjack.state import (
    EndRoundState,
    PlacingBetsState,
    WaitingForPlayersState,
    SimulationStats,
)
from cardsharp.common.deck import Deck
from cardsharp.common.io_interface import ConsoleIOInterface, DummyIOInterface


class BlackjackGame:
    def __init__(self, rules, io_interface):
        self.players = []
        self.io_interface = io_interface
        self.dealer = Dealer("Dealer", io_interface)
        self.rules = rules
        self.deck = Deck()
        self.current_state = WaitingForPlayersState()
        self.stats = SimulationStats()

    def set_state(self, state):
        self.current_state = state

    def add_player(self, player):
        if player is None:
            self.io_interface.output("Invalid player.")
            return

        if len(self.players) >= self.rules["max_players"]:
            self.io_interface.output("Game is full.")
            return

        if not isinstance(self.current_state, WaitingForPlayersState):
            self.io_interface.output("Game has already started.")
            return

        if self.current_state is not None:
            self.current_state.add_player(self, player)

    def play_round(self):
        while not isinstance(self.current_state, EndRoundState):
            self.current_state.handle(self)

        self.io_interface.output("Calculating winner...")
        self.current_state.calculate_winner(self)
        self.set_state(PlacingBetsState())


def main():
    # Add this block at the start of your main() function
    parser = argparse.ArgumentParser(description="Run a Blackjack game.")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run the game in simulation mode with no output.",
        default=False,
    )
    parser.add_argument(
        "--num_games", type=int, default=1, help="Number of games to simulate"
    )
    args = parser.parse_args()

    if args.simulate:
        io_interface = DummyIOInterface()
    else:
        io_interface = ConsoleIOInterface()

    # Define your rules TODO: make this use rules class
    rules = {
        "blackjack_payout": 1.5,
        "allow_insurance": True,
        "min_players": 1,
        "min_bet": 10,
        "max_players": 6,
    }

    players = [
        Player("Alice", io_interface),
        Player("Bob", io_interface),
    ]

    # Create a game
    game = BlackjackGame(rules, io_interface)

    # Add players
    for player in players:
        game.add_player(player)

    # Change state to PlacingBetsState after all players have been added
    game.set_state(PlacingBetsState())

    # Play games
    for _ in range(args.num_games):
        game.play_round()

    # Get and print the statistics after all games have been played
    stats = game.stats.report()
    print(f"Games played: {stats['games_played']}")
    print(f"Player wins: {stats['player_wins']}")
    print(f"Dealer wins: {stats['dealer_wins']}")
    print(f"Draws: {stats['draws']}")


if __name__ == "__main__":
    main()
