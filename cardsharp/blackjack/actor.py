from cardsharp.common.io_interface import IOInterface
from cardsharp.common.actor import SimplePlayer
from cardsharp.blackjack.hand import BlackjackHand
from cardsharp.common.card import Rank


class InsufficientFundsError(Exception):
    pass


class Player(SimplePlayer):
    current_hand: BlackjackHand

    def __init__(self, name: str, io_interface: IOInterface, initial_money: int = 1000):
        super().__init__(name, io_interface, initial_money)
        self.bet = 0
        self.insurance = 0
        self.hands = [BlackjackHand()]
        self.done = False
        self.blackjack = False
        self.winner = None

    def has_bet(self) -> bool:
        return self.bet > 0

    def is_done(self) -> bool:
        """Check if player has finished their turn."""
        return self.done

    def stand(self):
        """Player chooses to stop taking more cards."""
        self.done = True

    def is_busted(self) -> bool:
        """Check if player's hand value is over 21."""
        return self.current_hand.value() > 21

    def decide_action(self):
        # If the player has busted, they should stand
        if self.is_busted():
            return "stand"

        # If the player's hand value is less than 17, or is a soft 17, they should hit
        if self.current_hand.value() < 17 or (
            self.current_hand.value() == 17 and self.current_hand.is_soft()
        ):
            return "hit"

        # In all other cases, the player should stand
        else:
            return "stand"

    def place_bet(self, amount: int):
        if amount > self.money:
            raise InsufficientFundsError(
                f"{self.name} does not have enough money to place a bet of {amount}"
            )
        else:
            self.bet = amount
            self.money -= amount
            self.done = False

    def buy_insurance(self, amount: int):
        if amount <= self.money:
            self.insurance = amount
            self.money -= amount

    def payout(self, amount: int):
        self.money += amount + self.bet
        self.bet = 0
        self.insurance = 0
        self.done = True
        self.blackjack = False

    def add_card(self, card):
        self.current_hand.add_card(card)

    def reset(self):
        self.hands = [BlackjackHand()]
        self.done = False
        self.blackjack = False
        self.winner = None
        self.money = 1000
        self.bet = 0


class Dealer(SimplePlayer):
    def __init__(self, name: str, io_interface: IOInterface):
        super().__init__(name, io_interface, initial_money=0)
        self.hands = [BlackjackHand()]
        self.winner = None

    @property
    def current_hand(self):
        return self.hands[0]

    def has_ace(self):
        return self.current_hand.cards[0].rank == Rank.ACE

    def add_card(self, card):
        self.current_hand.add_card(card)

    def should_hit(self):
        return self.current_hand.value() < 17 or (
            self.current_hand.value() == 17 and self.current_hand.is_soft()
        )
