import csv
import os

from abc import ABC, abstractmethod
from typing import Optional

from cardsharp.blackjack.action import Action
from cardsharp.common.card import Card, Rank


class Strategy(ABC):
    @abstractmethod
    def decide_action(self, player, dealer_up_card=None) -> Action:
        pass

    @abstractmethod
    def decide_insurance(self, player) -> bool:
        """Decide whether to buy insurance. Returns True if the player wants to buy insurance."""
        pass

class DealerStrategy(Strategy):
    def decide_action(self, player, dealer_up_card=None) -> Action:
        if player.is_busted():
            return Action.STAND
        if player.current_hand.value() < 17 or (
            player.current_hand.value() == 17 and player.current_hand.is_soft
        ):
            return Action.HIT
        else:
            return Action.STAND


class BasicStrategy(Strategy):
    def __init__(self, strategy_file=None):
        if strategy_file is None:
            strategy_file = os.path.join(
                os.path.dirname(__file__), "basic_strategy.csv"
            )
        self.strategy = self._load_strategy(strategy_file)
        self.dealer_indexes = {
            "2": 0,
            "3": 1,
            "4": 2,
            "5": 3,
            "6": 4,
            "7": 5,
            "8": 6,
            "9": 7,
            "10": 8,
            "A": 9,
        }

    def _load_strategy(self, strategy_file):
        strategy = {}
        with open(strategy_file, "r") as f:
            reader = csv.reader(f)
            headers = next(reader)
            for row in reader:
                hand_type = row[0]
                actions = [action.strip() for action in row[1:]]  # Strip whitespace
                strategy[hand_type] = actions
        return strategy

    def _get_hand_type(self, hand):
        if hand.can_split:
            rank = hand.cards[0].rank
            if rank == Rank.ACE:
                return "PairA"
            elif rank.rank_value == 10:
                return "Pair10"
            else:
                return f"Pair{rank.rank_value}"
        elif hand.is_soft:
            value = hand.value()
            return f"Soft{value}"
        else:
            value = hand.value()
            return f"Hard{value}"

    def _get_dealer_card(self, dealer_up_card):
        rank = dealer_up_card.rank
        if rank.rank_value >= 10:
            return "10"
        elif rank == Rank.ACE:
            return "A"
        else:
            return str(rank.rank_value)

    def _get_action_from_strategy(self, hand_type, dealer_card):
        dealer_index = self.dealer_indexes[dealer_card]
        actions = self.strategy.get(hand_type, [])
        if actions:
            if dealer_index < len(actions):
                return actions[dealer_index]
            else:
                return "H"  # Default to Hit if index out of bounds
        else:
            return "H"  # Default to Hit if hand type not found

    def _map_action_symbol(self, symbol):
        mapping = {
            "H": Action.HIT,
            "S": Action.STAND,
            "D": Action.DOUBLE,
            "DS": Action.DOUBLE,  # We'll handle the "else Stand" in decide_action
            "P": Action.SPLIT,
            "R": Action.SURRENDER,
        }
        return mapping[symbol]

    def decide_action(self, player, dealer_up_card: Card) -> Action:
        current_hand = player.current_hand
        hand_type = self._get_hand_type(current_hand)
        dealer_card = self._get_dealer_card(dealer_up_card)
        action_symbol = self._get_action_from_strategy(hand_type, dealer_card)

        try:
            action = self._map_action_symbol(action_symbol)
        except KeyError:
            action = Action.HIT  # Default to HIT if unknown symbol

        final_action = self._get_valid_action(player, action, action_symbol)

        return final_action

    def _get_valid_action(self, player, action, action_symbol):
        if action == Action.DOUBLE and not self._is_action_valid(player, Action.DOUBLE):
            return Action.HIT if action_symbol == "D" else Action.STAND
        elif action == Action.SPLIT and not self._is_action_valid(player, Action.SPLIT):
            return Action.HIT
        elif action == Action.SURRENDER and not self._is_action_valid(
            player, Action.SURRENDER
        ):
            return Action.HIT
        return action

    def _is_action_valid(self, player, action):
        if action == Action.DOUBLE:
            return player.current_hand.can_double
        elif action == Action.SPLIT:
            return player.current_hand.can_split
        elif action == Action.SURRENDER:
            return (
                len(player.current_hand.cards) == 2
            )  # Can only surrender with two cards
        else:
            # HIT and STAND are always valid
            return True

    def decide_insurance(self, player) -> bool:
        """Basic strategy does not recommend taking insurance."""
        return False

class CountingStrategy(BasicStrategy):
    def __init__(self):
        super().__init__()
        self.count = 0

    def update_count(self, card: Card):
        if card.rank in [Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX]:
            self.count += 1
        elif card.rank in [Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING, Rank.ACE]:
            self.count -= 1

    def decide_action(self, player, dealer_up_card: Card) -> Action:
        # Update count based on the visible cards (player's cards and dealer's up card)
        for card in player.current_hand.cards + [dealer_up_card]:
            self.update_count(card)

        if self.count > 2:  # Adjust this threshold as needed
            return self.aggressive_strategy(player, dealer_up_card)
        else:
            return super().decide_action(player, dealer_up_card)

    def aggressive_strategy(self, player, dealer_up_card: Card) -> Action:
        # More aggressive play decisions when the count is high
        if (
            self.count >= 4
        ):  # Strongly positive count indicates more high cards are present
            if player.current_hand.can_double and player.current_hand.value() in [
                9,
                10,
                11,
            ]:
                return Action.DOUBLE
            elif player.current_hand.value() <= 16:
                return Action.HIT
        return super().decide_action(
            player, dealer_up_card
        )  # Default to basic strategy otherwise


class MartingaleStrategy(BasicStrategy):
    def __init__(self, initial_bet=1, max_bet=100):
        super().__init__()
        self.initial_bet = initial_bet
        self.current_bet = initial_bet
        self.max_bet = max_bet
        self.consecutive_losses = 0

    def decide_action(self, player, dealer_up_card: Card) -> Action:
        # Use the BasicStrategy to decide the action
        return super().decide_action(player, dealer_up_card)

    def place_bet(self) -> int:
        return self.current_bet

    def update_bet(self, result: str):
        if result == "win":
            self.current_bet = self.initial_bet
            self.consecutive_losses = 0
        elif result == "lose":
            self.consecutive_losses += 1
            new_bet = self.current_bet * 2
            self.current_bet = min(new_bet, self.max_bet)
        # In case of a push (tie), the bet remains the same

    def reset_bet(self):
        self.current_bet = self.initial_bet
        self.consecutive_losses = 0


class AggressiveStrategy(BasicStrategy):
    """
    An aggressive blackjack strategy that takes more risks, hits more often,
    and doubles down more frequently.
    """

    def decide_action(self, player, dealer_up_card: Card) -> Action:
        """
        Decides the action to take based on the player's hand and the dealer's up card.

        Args:
            player: The player instance.
            dealer_up_card (Card): The dealer's up card.

        Returns:
            Action: The action to take.
        """
        current_hand = player.current_hand
        if current_hand.is_blackjack:
            return Action.STAND

        actions = [
            self._decide_on_split,
            self._decide_on_double,
            self._decide_on_surrender,
            self._decide_on_stand_or_hit,
        ]

        for action_method in actions:
            action = action_method(current_hand, dealer_up_card)
            if action is not None:
                return action

        # If no action was decided, default to hit
        return Action.HIT

    def _decide_on_split(self, current_hand, dealer_up_card: Card) -> Optional[Action]:
        if not current_hand.can_split:
            return None

        player_rank = current_hand.cards[0].rank
        dealer_rank = dealer_up_card.rank.rank_value

        # Always split Aces and 8s
        if player_rank in [Rank.ACE, Rank.EIGHT]:
            return Action.SPLIT

        # Split 2s, 3s, 6s, 7s against dealer 2-7
        if (
            player_rank in [Rank.TWO, Rank.THREE, Rank.SIX, Rank.SEVEN]
            and dealer_rank <= 7
        ):
            return Action.SPLIT

        # Split 9s against dealer 2-9, except 7
        if player_rank == Rank.NINE and dealer_rank <= 9 and dealer_rank != 7:
            return Action.SPLIT

        return None

    def _decide_on_double(self, current_hand, dealer_up_card: Card) -> Optional[Action]:
        if not current_hand.can_double:
            return None

        hand_value = current_hand.value()
        dealer_rank = dealer_up_card.rank.rank_value

        # Double down on hard 9-11 against dealer 2-9
        if 9 <= hand_value <= 11 and dealer_rank <= 9:
            return Action.DOUBLE

        # Double down on soft 13-18 against dealer 2-6
        if current_hand.is_soft and 13 <= hand_value <= 18 and dealer_rank <= 6:
            return Action.DOUBLE

        return None

    def _decide_on_surrender(
        self, current_hand, dealer_up_card: Card
    ) -> Optional[Action]:
        # Aggressive strategy rarely surrenders
        return None

    def _decide_on_stand_or_hit(self, current_hand, dealer_up_card: Card) -> Action:
        hand_value = current_hand.value()
        dealer_rank = dealer_up_card.rank.rank_value

        if current_hand.is_soft:
            # Always hit soft 17 or lower
            if hand_value <= 17:
                return Action.HIT
            # Hit soft 18 against dealer 9, 10, or Ace
            elif hand_value == 18 and dealer_rank >= 9:
                return Action.HIT
            else:
                return Action.STAND
        else:
            # Always hit 11 or lower
            if hand_value <= 11:
                return Action.HIT
            # Hit 12-16 against dealer 7 or higher
            elif 12 <= hand_value <= 16 and dealer_rank >= 7:
                return Action.HIT
            else:
                return Action.STAND
