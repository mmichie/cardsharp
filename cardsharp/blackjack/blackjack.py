import asyncio

from cardsharp.blackjack.actor import Dealer, Player
from cardsharp.blackjack.state import (
    DealersTurnState,
    DealingState,
    EndRoundState,
    OfferInsuranceState,
    PlacingBetsState,
    PlayersTurnState,
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

    async def add_player(self, player):
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
            await self.current_state.add_player(self, player)

    def play_round(self):
        while not isinstance(self.current_state, EndRoundState):
            if isinstance(self.current_state, PlacingBetsState):
                for player in self.players:
                    self.current_state.place_bet(self, player, 10)
            elif isinstance(self.current_state, DealingState):
                self.io_interface.output("Dealing cards...")
                self.current_state.deal(self)
            elif isinstance(self.current_state, OfferInsuranceState):
                self.io_interface.output("Checking for and offering insurance...")
                for player in self.players:
                    if isinstance(self.current_state, OfferInsuranceState):
                        self.current_state.offer_insurance(self, player)
            elif isinstance(self.current_state, PlayersTurnState):
                for player in self.players:
                    while not player.is_done() and not player.is_busted():
                        action = player.decide_action()
                        self.current_state.player_action(self, player, action)
                        self.io_interface.output(f"{player.name}'s turn...")
                        if player.is_busted():
                            self.io_interface.output(f"{player.name} has busted.")
                            player.stand()

                    if player.is_done():
                        self.io_interface.output(
                            f"{player.name} has finished their turn."
                        )

                self.set_state(
                    DealersTurnState()
                )  # Move to the dealer's turn once all players are done
            elif isinstance(self.current_state, DealersTurnState):
                self.current_state.dealer_action(self)
                self.io_interface.output("Dealer's turn...")

        self.io_interface.output("Calculating winner...")
        self.current_state.calculate_winner(self)
        self.current_state = PlacingBetsState()


async def main():
    # Create IO Interface
    io_interface = ConsoleIOInterface()

    # Define your rules
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
        await game.add_player(player)

    # Change state to PlacingBetsState after all players have been added
    game.set_state(PlacingBetsState())

    # Play a round
    game.play_round()


if __name__ == "__main__":
    asyncio.run(main())
