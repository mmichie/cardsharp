import abc
import argparse
import asyncio
import random

from cardsharp.common.actor import SimplePlayer
from cardsharp.common.deck import Deck
from cardsharp.common.io_interface import DummyIOInterface, IOInterface


class GameState(abc.ABC):
    @abc.abstractmethod
    def get_state(self):
        pass


class HighCardGame(GameState):
    def __init__(self, *players, io_interface: IOInterface):
        self.players = players
        self.deck = Deck()
        self.io_interface = io_interface

    def get_state(self):
        """
        Return a dictionary representing the current game state.
        """
        state = {
            "players": [player.name for player in self.players],
            "deck": str(self.deck),
        }
        return state

    async def play_round(self):
        """
        Plays a round of High Card.

        Returns the player who drew the highest card.
        """
        self.deck.reset()
        high_card = None
        winner = None

        # Randomize player order
        player_list = list(self.players)  # convert tuple to list
        random.shuffle(player_list)

        for player in player_list:
            player.reset_hands()
            drawn_card = self.deck.deal()
            player.hands[0].add_card(drawn_card)
            await self.io_interface.send_message(f"{player.name} drew {drawn_card}")

            if not high_card or drawn_card.rank > high_card.rank:
                high_card = drawn_card
                winner = player

        return winner


def parse_args():
    parser = argparse.ArgumentParser(description="Play a simulation of High Card.")
    parser.add_argument(
        "-r",
        "--rounds",
        type=int,
        default=100,
        help="number of rounds to play (default: 1000000)",
    )
    parser.add_argument(
        "-p", "--players", type=int, default=2, help="number of players (default: 2)"
    )
    parser.add_argument(
        "-n",
        "--names",
        nargs="+",
        default=["Alice", "Bob"],
        help="names of the players (default: Alice Bob)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    io_interface = DummyIOInterface()

    players = [SimplePlayer(name, io_interface) for name in args.names[: args.players]]
    game = HighCardGame(*players, io_interface=io_interface)

    winners = []
    for _ in range(args.rounds):
        winner = await game.play_round()
        if winner is not None:
            winners.append(winner.name)

    print(f"Finished playing {args.rounds} rounds.")
    for name in args.names[: args.players]:
        wins = winners.count(name)
        win_percentage = (wins / args.rounds) * 100
        print(f"{name} won {wins} times ({win_percentage:.2f}%).")


if __name__ == "__main__":
    asyncio.run(main())
