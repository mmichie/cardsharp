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

    pass


class InvalidActionError(Exception):
    """Raised when a player attempts to perform an action that is not currently valid."""

    pass


class TableLimitError(Exception):
    """Raised when a bet would exceed table limits."""

    pass


class Player(SimplePlayer):
    """A player in a game of Blackjack."""

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
        self.game = None
        self.bets = []
        self.insurance = 0
        self.total_bets = 0
        self.total_winnings = 0
        self.hands = [BlackjackHand()]
        self.done = False
        self.blackjack = False
        self.winner = []
        self.current_hand_index = 0
        self.hand_done = [False]
        self.split_hands = [False]
        self.must_stand_after_hit = False
        self.action_history = [[]]

    @property
    def current_hand(self):
        """Returns the player's current hand."""
        return self.hands[self.current_hand_index]

    @property
    def valid_actions(self) -> list[Action]:
        """Returns a list of valid actions for the player."""
        # Fast path checks
        if self.hand_done[self.current_hand_index] or self.done:
            return []

        cards_len = len(self.current_hand.cards)

        if not cards_len:
            return []
        elif cards_len == 1:
            return [Action.HIT, Action.STAND]

        # Pre-allocate valid actions for most common case
        valid = [Action.HIT, Action.STAND]

        # Only do more expensive checks if we have exactly 2 cards
        if cards_len == 2:
            # Check for double down - common action, check first
            if self.game.rules.can_double_down(self.current_hand):
                doubled_bet = self.bets[self.current_hand_index] * 2
                if doubled_bet <= self.game.rules.max_bet:
                    valid.append(Action.DOUBLE)

            # Check for split - less common
            if self.current_hand.can_split and self.game.rules.can_split(
                self.current_hand
            ):
                if len(self.hands) < self.game.rules.get_max_splits() + 1:
                    valid.append(Action.SPLIT)

            # Check for surrender - least common action
            if not self.current_hand.is_split:
                valid.append(Action.SURRENDER)

        return valid

    def can_afford(self, amount: int) -> bool:
        """Check if player has enough money to afford a certain amount."""
        return self.money >= amount

    def has_bet(self) -> bool:
        """Check if player has placed a bet."""
        return any(bet > 0 for bet in self.bets)

    def is_done(self) -> bool:
        """Check if the player is done with all hands."""
        return all(self.hand_done)

    def split(self):
        """Attempts to split the player's hand into two hands."""
        if not self.current_hand.can_split:
            raise InvalidActionError(f"{self.name} cannot split at this time.")

        if len(self.hands) >= self.game.rules.get_max_splits() + 1:
            raise InvalidActionError(f"{self.name} has reached maximum splits.")

        bet_for_current_hand = self.bets[self.current_hand_index]

        if bet_for_current_hand > self.money:
            raise InsufficientFundsError(
                f"{self.name} does not have enough money to split."
            )

        # Check if splitting aces
        is_splitting_aces = self.current_hand.cards[0].rank == Rank.ACE

        # Process the split
        self.money -= bet_for_current_hand
        self.total_bets += bet_for_current_hand

        card_to_move = self.current_hand.cards.pop()
        new_hand = BlackjackHand(is_split=True)
        new_hand.add_card(card_to_move)

        self.hands.append(new_hand)
        self.hand_done.append(False)
        self.split_hands.append(True)
        self.bets.append(bet_for_current_hand)

        self.action_history.append([])

        if is_splitting_aces:
            self.must_stand_after_hit = True

    def surrender(self):
        """Player chooses to surrender, forfeiting half their bet."""
        if len(self.current_hand.cards) != 2:
            raise InvalidActionError(f"{self.name} can only surrender with two cards.")

        bet_for_current_hand = self.bets[self.current_hand_index]
        surrender_amount = (
            bet_for_current_hand / 2
        )  # Use floating-point division for exact half
        self.money += surrender_amount
        self.total_winnings -= bet_for_current_hand - surrender_amount
        self.bets[self.current_hand_index] = 0
        self.hand_done[self.current_hand_index] = True

    def hit(self, card):
        """Player chooses to take another card."""
        self.current_hand.add_card(card)
        if self.current_hand.value() > 21:
            self.hand_done[self.current_hand_index] = True
        elif self.must_stand_after_hit:
            self.hand_done[self.current_hand_index] = True
            self.must_stand_after_hit = False

    def stand(self):
        """Player chooses to stand."""
        self.hand_done[self.current_hand_index] = True

    def double_down(self):
        """Attempts to double the player's current bet."""
        if not self.has_bet():
            raise InvalidActionError(
                f"{self.name} must place a bet before doubling down."
            )

        if len(self.current_hand.cards) != 2:
            raise InvalidActionError(
                f"{self.name} can only double down with two cards."
            )

        if self.current_hand.is_split and not self.game.rules.allow_double_after_split:
            raise InvalidActionError(f"{self.name} cannot double down after splitting.")

        bet_for_current_hand = self.bets[self.current_hand_index]

        # Check insufficient funds first
        if bet_for_current_hand > self.money:
            raise InsufficientFundsError(
                f"{self.name} does not have enough money to double down."
            )

        doubled_bet = bet_for_current_hand * 2
        if doubled_bet > self.game.rules.max_bet:
            raise TableLimitError(
                f"Doubled bet would exceed table maximum of {self.game.rules.max_bet}"
            )

        if self.is_busted():
            raise InvalidActionError(f"{self.name} cannot double down after busting.")

        self.money -= bet_for_current_hand
        self.total_bets += bet_for_current_hand
        self.bets[self.current_hand_index] *= 2
        self.must_stand_after_hit = True

    def is_busted(self) -> bool:
        """Check if player's current hand value is over 21."""
        if not self.current_hand.cards:
            return False
        return self.current_hand.value() > 21

    def decide_action(self, dealer_up_card) -> Action:
        """Decides which action to take based on the player's strategy or IOInterface."""
        time_limit = self.game.rules.get_time_limit()

        if self.strategy is not None:
            return self.strategy.decide_action(self, dealer_up_card, self.game)
        else:
            # If there's a time limit, pass it to the IOInterface
            if time_limit > 0:
                self.io_interface.output(f"Time limit: {time_limit} seconds")
                action = self.io_interface.get_player_action(
                    self, self.valid_actions, time_limit
                )
            else:
                action = self.io_interface.get_player_action(self, self.valid_actions)

            if action is None:
                # If time limit expired or no valid action was chosen, default to STAND
                self.io_interface.output(
                    f"Time limit expired or no valid action chosen. {self.name} stands."
                )
                return Action.STAND

            return action

    def place_bet(self, amount, min_bet):
        """Place a bet for the player."""
        if amount < min_bet:
            raise ValueError(f"Bet amount must be at least {min_bet}.")

        # Check insufficient funds before table limits
        if amount > self.money:
            raise InsufficientFundsError(
                f"{self.name} does not have enough money to bet {amount}."
            )

        if amount > self.game.rules.max_bet:
            raise TableLimitError(
                f"Bet would exceed table maximum of {self.game.rules.max_bet}"
            )

        self.money -= amount
        self.bets = [amount]
        self.total_bets += amount

    def buy_insurance(self, amount: int):
        """Attempts to buy insurance."""
        # Insurance must be exactly half the original bet
        required_insurance = self.bets[0] / 2
        if amount != required_insurance:
            raise ValueError(
                f"Insurance must be exactly half the original bet ({required_insurance})"
            )
        if amount > self.money:
            raise InsufficientFundsError(
                f"{self.name} does not have enough money to buy insurance of {amount}"
            )
        self.insurance = amount
        self.money -= amount
        self.total_bets += amount

    def payout(self, hand_index: int, amount: int):
        """Handles payout to the player."""
        bet_for_hand = self.bets[hand_index]
        winnings = amount - bet_for_hand
        self.money += amount
        self.total_winnings += winnings
        self.bets[hand_index] = 0

    def payout_insurance(self, amount: int):
        """Handles insurance payout."""
        self.money += amount
        self.total_winnings += amount - self.insurance
        self.insurance = 0

    def add_card(self, card):
        """
        Adds a card to the player's current hand and checks for bust.
        """
        self.current_hand.add_card(card)
        # Check for bust after adding card
        if self.current_hand.value() > 21:
            self.hand_done[self.current_hand_index] = True
        self._cached_value = None

    def reset(self):
        """Resets the player's state."""
        self.hands = [BlackjackHand()]
        self.bets = []
        self.done = False
        self.blackjack = False
        self.winner = []
        self.total_bets = 0
        self.total_winnings = 0
        self.current_hand_index = 0
        self.hand_done = [False]
        self.split_hands = [False]
        self.must_stand_after_hit = False
        self.insurance = 0
        self.action_history = [[]]


class Dealer(SimplePlayer):
    """A dealer in a game of Blackjack."""

    def __init__(self, name: str, io_interface: IOInterface):
        super().__init__(name, io_interface, initial_money=0)
        self.hands = [BlackjackHand()]
        self.winner = None

    @property
    def current_hand(self):
        """Returns the dealer's current hand."""
        return self.hands[0]

    def has_ace(self):
        """Returns True if dealer's up card is an Ace."""
        return (
            bool(self.current_hand.cards)
            and self.current_hand.cards[0].rank == Rank.ACE
        )

    def add_card(self, card):
        """Adds a card to dealer's hand."""
        self.current_hand.add_card(card)

    def should_hit(self, rules):
        """Determine if dealer should hit."""
        if not self.current_hand.cards:
            return True

        # Use the rules implementation directly to avoid potential inconsistencies
        return rules.should_dealer_hit(self.current_hand)

    def reset(self):
        """Resets dealer's state."""
        self.hands = [BlackjackHand()]
        self.winner = None
