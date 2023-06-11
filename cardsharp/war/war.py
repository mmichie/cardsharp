import asyncio

from cardsharp.common.actor import SimplePlayer
from cardsharp.common.deck import Deck
from cardsharp.common.io_interface import ConsoleIOInterface


class WarGame:
    def __init__(self, player1: SimplePlayer, player2: SimplePlayer):
        self.deck = Deck()
        self.deck.shuffle()
        self.player1 = player1
        self.player2 = player2

    async def start_game(self):
        while True:
            if self.deck.size == 0:
                break

            await self.player1.display_message("Your turn to draw a card.")
            card1 = self.deck.deal()

            await self.player2.display_message("Your turn to draw a card.")
            card2 = self.deck.deal()

            # Compare the rank of the cards
            if card1.rank > card2.rank:
                await self.player1.display_message("You win this round!")
                self.player1.update_money(100)  # Alice wins and gains 100
                self.player2.update_money(-100)  # Bob loses and loses 100
            elif card2.rank > card1.rank:
                await self.player2.display_message("You win this round!")
                self.player2.update_money(100)  # Bob wins and gains 100
                self.player1.update_money(-100)  # Alice loses and loses 100
            else:
                await self.player1.display_message("It's a tie!")

        if self.player1.money > self.player2.money:
            winner = self.player1
        else:
            winner = self.player2

        await winner.display_message("You won the game!")


def main():
    # Create a single IO interface for console interaction
    io_interface = ConsoleIOInterface()

    player1 = SimplePlayer("Alice", io_interface)
    player2 = SimplePlayer("Bob", io_interface)

    game = WarGame(player1, player2)

    asyncio.run(game.start_game())


if __name__ == "__main__":
    main()
