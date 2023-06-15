from cardsharp.common.io_interface import IOInterface
from cardsharp.common.actor import SimplePlayer
from cardsharp.blackjack.hand import BlackjackHand


class Player(SimplePlayer):
    def __init__(self, name: str, io_interface: IOInterface, initial_money: int = 1000):
        super().__init__(name, io_interface, initial_money)
        self.bet = 0
        self.insurance = 0
        self.hands = [BlackjackHand()]
        self.done = False

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
        # For this example, we'll use a simple strategy where
        # the player hits if their hand value is less than 17 and stands otherwise
        if self.current_hand.value() < 17:
            return "hit"
        else:
            return "stand"

    def place_bet(self, amount: int):
        if amount <= self.money:
            self.bet = amount
            self.money -= amount

    def buy_insurance(self, amount: int):
        if amount <= self.money:
            self.insurance = amount
            self.money -= amount

    def payout(self, amount: int):
        self.money += amount

    def add_card(self, card):
        self.current_hand.add_card(card)


class Dealer(SimplePlayer):
    def __init__(self, name: str, io_interface: IOInterface):
        super().__init__(name, io_interface, initial_money=0)
        self.hands = [BlackjackHand()]

    @property
    def current_hand(self):
        return self.hands[0]

    def has_ace(self):
        if self.current_hand.cards[0].rank == "A":
            return True

    def add_card(self, card):
        self.current_hand.add_card(card)

    def should_hit(self):
        return self.current_hand.value() < 17
