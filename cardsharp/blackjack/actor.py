"""
This module provides the `Player` and `Dealer` classes for a game of Blackjack.

The `Player` class represents a player in the game. It maintains the state of the player's current hand,
the amount of money the player has, the player's current bet, and whether the player's turn is done. The
`Player` class also provides methods for the player to perform various actions, like hitting, standing,
splitting, and doubling down.

The `Dealer` class represents the dealer in the game. It is a subclass of `Player`, but with its own
logic for deciding whether to hit or stand.

Exceptions:
    - `InsufficientFundsError`: Raised when a player does not have enough money to perform an action.
    - `InvalidActionError`: Raised when a player attempts to perform an action that is not currently valid.

This module is part of the `cardsharp` package, a framework for creating and playing card games.
"""


from typing import Optional

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.hand import BlackjackHand
from cardsharp.blackjack.strategy import Strategy
from cardsharp.common.actor import SimplePlayer
from cardsharp.common.card import Rank
from cardsharp.common.io_interface import IOInterface


class InsufficientFundsError(Exception):
    """Raised when a player does not have enough money to perform an action."""


class InvalidActionError(Exception):
    """Raised when a player attempts to perform an action that is not currently valid."""


class Player(SimplePlayer):
    """A player in a game of Blackjack.

    Attributes:
        current_hand: The current hand of the player.
    """

    current_hand: BlackjackHand

    def __init__(
        self,
        name: str,
        io_interface: IOInterface,
        strategy: Optional[Strategy] = None,
        initial_money: int = 1000,
    ):
        """Creates a new player with the given parameters."""
        super().__init__(name, io_interface, initial_money)
        if strategy is None and not isinstance(io_interface, IOInterface):
            raise InvalidActionError(
                f"{self.name} must have a valid strategy or IOInterface."
            )
        self.strategy = strategy
        self.bet = 0
        self.insurance = 0
        self.hands = [BlackjackHand()]
        self.done = False
        self.blackjack = False
        self.winner = None

    @property
    def valid_actions(self) -> list[Action]:
        """Returns a list of valid actions for the player."""
        if self.done:  # No actions are valid after the player stands
            return []
        elif not self.current_hand.cards:  # Player can't hit or stand without cards
            return []
        elif (
            len(self.current_hand.cards) == 1
        ):  # Player can only hit or stand with one card
            return [Action.HIT, Action.STAND]
        elif (
            self.current_hand.can_split
        ):  # Player can split if they have two cards of the same rank
            return list(Action)
        else:
            return [
                Action.HIT,
                Action.STAND,
                Action.DOUBLE,
                Action.SPLIT,
                Action.SURRENDER,
                Action.INSURANCE,
            ]

    def can_afford(self, amount: int) -> bool:
        """Check if player has enough money to afford a certain amount."""
        return self.money >= amount

    def has_bet(self) -> bool:
        """Check if player has placed a bet."""
        return self.bet > 0

    def is_done(self) -> bool:
        """Check if player has finished their turn."""
        return self.done

    def split(self):
        """Attempts to split the player's hand into two hands."""

        if not self.current_hand.can_split:
            raise InvalidActionError(f"{self.name} cannot split at this time.")

        if self.bet >= self.money:
            raise InsufficientFundsError(
                f"{self.name} does not have enough money to split."
            )

        self.money -= self.bet
        new_hand = BlackjackHand()
        new_hand.add_card(self.current_hand.cards.pop())
        self.hands.append(new_hand)

    def hit(self, card):
        """Player chooses to take another card."""
        self.current_hand.add_card(card)
        if self.is_busted():
            self.done = True

    def stand(self):
        """Player chooses to stop taking more cards."""
        self.done = True

    def double_down(self):
        """Attempts to double the player's current bet."""

        if not self.has_bet():
            raise InvalidActionError(
                f"{self.name} must place a bet before they can double down."
            )

        if self.is_busted():
            raise InvalidActionError(f"{self.name} cannot double down after busting.")

        if self.bet > self.money:
            raise InsufficientFundsError(
                f"{self.name} does not have enough money to double down."
            )

        self.money -= self.bet
        self.bet *= 2
        self.done = True

    def is_busted(self) -> bool:
        """Check if player's hand value is over 21."""
        return self.current_hand.value() > 21

    def decide_action(self, dealer_up_card) -> Action:
        """Decides which action to take based on the player's strategy or IOInterface."""
        if self.strategy is not None:
            return self.strategy.decide_action(self, dealer_up_card)
        else:  # if strategy is None, then io_interface must be a valid IOInterface
            action = self.io_interface.get_player_action(self, self.valid_actions)
            if action is None:
                raise InvalidActionError(f"{self.name} did not choose a valid action.")
            return action

    def place_bet(self, amount: int):
        """Attempts to place a bet of the given amount."""
        if amount > self.money:
            raise InsufficientFundsError(
                f"{self.name} does not have enough money to place a bet of {amount}"
            )
        else:
            self.bet = amount
            self.money -= amount
            self.done = False

    def buy_insurance(self, amount: int):
        """Attempts to buy insurance for the given amount."""
        if amount > self.money:
            raise InsufficientFundsError(
                f"{self.name} does not have enough money to buy insurance of {amount}"
            )
        else:
            self.insurance = amount
            self.money -= amount

    def payout(self, amount: int):
        """Gives the player a payout of the given amount."""
        self.money += amount + self.bet
        self.bet = 0
        self.insurance = 0
        self.done = True
        self.blackjack = False

    def add_card(self, card):
        """Adds a card to the player's current hand."""
        self.current_hand.add_card(card)

    def reset(self):
        """Resets the player's state to the initial state."""
        self.hands = [BlackjackHand()]
        self.done = False
        self.blackjack = False
        self.winner = None
        self.money = 1000
        self.bet = 0


class Dealer(SimplePlayer):
    """A dealer in a game of Blackjack."""

    def __init__(self, name: str, io_interface: IOInterface):
        """Creates a new dealer with the given parameters."""

        super().__init__(name, io_interface, initial_money=0)
        self.hands = [BlackjackHand()]
        self.winner = None

    @property
    def current_hand(self):
        """Returns the dealer's current hand."""
        return self.hands[0]

    def has_ace(self):
        """Returns True if the dealer's face-up card is an Ace, False otherwise."""
        return self.current_hand.cards[0].rank == Rank.ACE

    def add_card(self, card):
        """Adds a card to the dealer's hand."""
        self.current_hand.add_card(card)

    def should_hit(self):
        """Returns True if the dealer should hit based on their current hand, False otherwise."""

        return self.current_hand.value() < 17 or (
            self.current_hand.value() == 17 and self.current_hand.is_soft
        )

    def reset(self):
        """Resets the dealer's state to the initial state."""
        self.hands = [BlackjackHand()]
        self.winner = None
