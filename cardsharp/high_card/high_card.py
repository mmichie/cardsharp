from cardsharp.common.deck import Deck
from cardsharp.common.actor import SimplePlayer


class HighCardGame:
    def __init__(self, *players):
        self.players = players
        self.deck = Deck()

    def play_round(self):
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
            player.display_message(f"drew {drawn_card}")

            if not high_card or drawn_card.rank > high_card.rank:
                high_card = drawn_card
                winner = player

        return winner


def main():
    player1 = SimplePlayer("Alice")
    player2 = SimplePlayer("Bob")

    game = HighCardGame(player1, player2)
    winner = game.play_round()

    print(f"The winner is {winner.name}!")


if __name__ == "__main__":
    main()
