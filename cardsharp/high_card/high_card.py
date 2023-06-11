import asyncio
from cardsharp.common.deck import Deck
from cardsharp.common.actor import SimplePlayer
from cardsharp.common.io_interface import ConsoleIOInterface

class HighCardGame:
    def __init__(self, *players):
        self.players = players
        self.deck = Deck()

    async def play_round(self):
        """
        Plays a round of High Card.

        Returns the player who drew the highest card.
        """
        self.deck.shuffle()
        high_card = None
        winner = None

        for player in self.players:
            player.reset_hands()
            drawn_card = self.deck.deal()
            player.hands[0].add_card(drawn_card)
            await player.display_message(f"drew {drawn_card}")

            if not high_card or drawn_card.rank > high_card.rank:
                high_card = drawn_card
                winner = player

        return winner


async def main():
    io_interface1 = ConsoleIOInterface()
    io_interface2 = ConsoleIOInterface()

    player1 = SimplePlayer("Alice", io_interface1)
    player2 = SimplePlayer("Bob", io_interface2)

    game = HighCardGame(player1, player2)
    winner = await game.play_round()

    print(f"The winner is {winner.name}!")


if __name__ == "__main__":
    asyncio.run(main())

