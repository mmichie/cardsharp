import asyncio

from cardsharp.blackjack.actor import Dealer, Player
from cardsharp.blackjack.state import (
    EndRoundState,
    PlacingBetsState,
    WaitingForPlayersState,
)
from cardsharp.common.deck import Deck
from cardsharp.common.io_interface import ConsoleIOInterface


class BlackjackGame:
    def __init__(self, rules, io_interface):
        self.players = []
        self.io_interface = io_interface
        self.dealer = Dealer("Dealer", io_interface)
        self.rules = rules
        self.deck = Deck()
        self.current_state = WaitingForPlayersState()

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


async def main():
    # Create IO Interface
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

    # Play a round
    game.play_round()


if __name__ == "__main__":
    asyncio.run(main())
