import csv
import os

from abc import ABC, abstractmethod
from typing import Optional

from cardsharp.blackjack.action import Action
from cardsharp.common.card import Card, Rank
from cardsharp.blackjack.constants import get_blackjack_value
from cardsharp.blackjack.decision_logger import decision_logger


class Strategy(ABC):
    @abstractmethod
    def decide_action(self, player, dealer_up_card, game=None) -> Action:
        pass

    @abstractmethod
    def decide_insurance(self, player) -> bool:
        """Decide whether to buy insurance. Returns True if the player wants to buy insurance."""
        pass
    
    def get_bet_amount(self, min_bet: float, max_bet: float, player_money: float) -> float:
        """
        Determine bet amount for next hand. Called BEFORE cards are dealt.
        Default implementation returns minimum bet.
        """
        return min_bet

    def receive_exposed_card_info(self, card: Card) -> None:
        """
        Receives information about a card that has been accidentally exposed.

        This method can be overridden by strategies that can take advantage of exposed card information.

        Args:
            card: The Card object that was exposed

        Returns:
            None
        """
        # Default implementation does nothing with the exposed card
        pass

    def get_advantage(self, game_state=None) -> float:
        """
        Returns the player's estimated advantage in the current situation.

        This method can be overridden by strategies that can calculate their edge.

        Args:
            game_state: Current game state (optional)

        Returns:
            Float representing player advantage as a decimal (e.g., 0.01 = 1% advantage)
        """
        # Default implementation assumes slight house edge
        return -0.005


class DealerStrategy(Strategy):
    def decide_action(self, player, dealer_up_card=None, game=None) -> Action:
        if player.is_busted():
            return Action.STAND
        if player.current_hand.value() < 17 or (
            player.current_hand.value() == 17 and player.current_hand.is_soft
        ):
            return Action.HIT
        else:
            return Action.STAND

    def decide_insurance(self, player):
        return False


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
            _ = next(reader)  # Skip header row
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
            elif get_blackjack_value(rank) == 10:
                return "Pair10"
            else:
                return f"Pair{get_blackjack_value(rank)}"
        elif hand.is_soft:
            value = hand.value()
            return f"Soft{value}"
        else:
            value = hand.value()
            return f"Hard{value}"

    def _get_dealer_card(self, dealer_up_card):
        rank = dealer_up_card.rank
        if rank == Rank.ACE:
            return "A"
        elif get_blackjack_value(rank) >= 10:
            return "10"
        else:
            return str(get_blackjack_value(rank))

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
            "DS": Action.DOUBLE,
            "P": Action.SPLIT,
            "R": Action.SURRENDER,
        }
        return mapping[symbol]

    def decide_action(self, player, dealer_up_card: Card, game=None) -> Action:
        current_hand = player.current_hand
        hand_type = self._get_hand_type(current_hand)
        dealer_card = self._get_dealer_card(dealer_up_card)
        action_symbol = self._get_action_from_strategy(hand_type, dealer_card)

        decision_logger.log_strategy_lookup(hand_type, dealer_card, action_symbol)

        try:
            action = self._map_action_symbol(action_symbol)
        except KeyError:
            decision_logger.logger.warning(
                f"Unknown action symbol: {action_symbol}, defaulting to HIT"
            )
            action = Action.HIT  # Default to HIT if unknown symbol

        final_action = self._get_valid_action(player, action, action_symbol)

        if final_action != action:
            decision_logger.logger.info(
                f"Action adjusted from {action.value} to {final_action.value} based on valid actions"
            )

        return final_action

    def _get_valid_action(self, player, action, action_symbol):
        valid_actions = player.valid_actions

        if action == Action.DOUBLE:
            if Action.DOUBLE in valid_actions:
                return Action.DOUBLE
            else:
                if action_symbol == "DS":
                    if Action.STAND in valid_actions:
                        return Action.STAND
                    else:
                        return Action.HIT  # Fallback to HIT if STAND not possible
                else:
                    if Action.HIT in valid_actions:
                        return Action.HIT
                    else:
                        return Action.STAND  # Fallback if HIT is not valid

        elif action == Action.SURRENDER:
            if Action.SURRENDER in valid_actions:
                return Action.SURRENDER
            else:
                if Action.HIT in valid_actions:
                    return Action.HIT
                else:
                    return Action.STAND  # Fallback if HIT is not valid

        elif action == Action.SPLIT:
            if Action.SPLIT in valid_actions:
                return Action.SPLIT
            else:
                if Action.HIT in valid_actions:
                    return Action.HIT
                else:
                    return Action.STAND  # Fallback if HIT is not valid

        elif action in valid_actions:
            return action

        else:
            # If the recommended action is not valid, default to HIT or STAND
            if Action.HIT in valid_actions:
                return Action.HIT
            elif Action.STAND in valid_actions:
                return Action.STAND
            else:
                # As a last resort, return any available action
                return valid_actions[0]

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
        self.true_count: float = 0
        self.decks_remaining = 6  # Assume 6 decks by default
        self.exposed_cards = []  # Track cards that have been accidentally exposed
        self.advantage_factor = 0.0  # Additional advantage from exposed cards
        self.counted_cards = set()  # Track which cards we've already counted

    def update_count(self, card: Card):
        if card.rank in [Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX]:
            self.count += 1
        elif card.rank in [Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING, Rank.ACE]:
            self.count -= 1

    def calculate_true_count(self):
        self.true_count = self.count / max(1, self.decks_remaining)

    def receive_exposed_card_info(self, card: Card) -> None:
        """
        Adjust strategy based on exposed card information.

        Args:
            card: The Card object that was exposed
        """
        # Add to exposed cards list
        self.exposed_cards.append(card)

        # Update count
        self.update_count(card)

        # Increase advantage factor - seeing dealer hole card is a huge advantage
        self.advantage_factor += 0.05  # 5% advantage from seeing a key card

    def get_advantage(self, game_state=None) -> float:
        """
        Calculate player advantage based on card counting.

        Returns:
            Float representing player advantage
        """
        # Calculate advantage from card counting
        self.calculate_true_count()

        # Base advantage starts with house edge
        base_advantage = -0.005  # 0.5% house edge

        # Adjust based on count - each true count point is worth ~0.5% in player advantage
        count_advantage = self.true_count * 0.005

        # Add advantage from exposed cards
        total_advantage = base_advantage + count_advantage + self.advantage_factor

        return total_advantage

    def decide_action(self, player, dealer_up_card: Card, game) -> Action:
        # Update count based on NEW visible cards only
        for card in game.visible_cards:
            card_id = id(card)
            if card_id not in self.counted_cards:
                self.update_count(card)
                self.counted_cards.add(card_id)

        # Calculate true count
        self.calculate_true_count()

        # DO NOT adjust bet here - bets must be placed before cards are dealt!

        if self.true_count > 2:  # Adjust this threshold as needed
            return self.aggressive_strategy(player, dealer_up_card, game)
        else:
            return super().decide_action(player, dealer_up_card, game)

    def aggressive_strategy(self, player, dealer_up_card: Card, game) -> Action:
        # More aggressive play decisions when the count is high
        if (
            self.true_count >= 4
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
            player, dealer_up_card, game
        )  # Default to basic strategy otherwise

    def get_bet_amount(self, min_bet: float, max_bet: float, player_money: float) -> float:
        """
        Determine bet amount based on current count.
        This is called BEFORE cards are dealt.
        
        With CSM, the count is meaningless but the strategy doesn't know this,
        so it will bet high on false signals and lose more.
        """
        # Calculate true count before betting
        self.calculate_true_count()
        
        # Base bet is minimum
        bet = min_bet
        
        # Increase bet when count is favorable (or appears to be with CSM)
        if self.true_count > 2:
            bet_multiplier = min(self.true_count, 5)  # Cap the multiplier at 5
            bet = min_bet * bet_multiplier
        elif self.true_count < -2:
            # Bet less when count is negative (more low cards remaining)
            bet = min_bet  # Stay at minimum
        
        # Ensure bet doesn't exceed limits
        bet = min(bet, max_bet, player_money)
        
        return bet
    
    def notify_shuffle(self):
        """Called when the shoe is shuffled to reset the count."""
        self.reset_count()

    def update_decks_remaining(self, cards_played):
        total_cards = 52 * 6  # Assuming 6 decks
        self.decks_remaining = (total_cards - cards_played) / 52

    def reset_count(self):
        """Reset the count at the start of a new shoe."""
        self.count = 0
        self.true_count = 0.0
        self.decks_remaining = 6  # Reset to initial number of decks
        self.counted_cards.clear()  # Clear counted cards tracking


class MartingaleStrategy(BasicStrategy):
    def __init__(self, initial_bet=1, max_bet=100):
        super().__init__()
        self.initial_bet = initial_bet
        self.current_bet = initial_bet
        self.max_bet = max_bet
        self.consecutive_losses = 0

    def decide_action(self, player, dealer_up_card: Card, game=None) -> Action:
        # Use the BasicStrategy to decide the action
        return super().decide_action(player, dealer_up_card, game)

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

    def decide_action(self, player, dealer_up_card: Card, game=None) -> Action:
        """
        Decides the action to take based on the player's hand and the dealer's up card.

        Args:
            player: The player instance.
            dealer_up_card (Card): The dealer's up card.
            game: The game instance (optional).

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
        dealer_rank = get_blackjack_value(dealer_up_card.rank)

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
        dealer_rank = get_blackjack_value(dealer_up_card.rank)

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
        dealer_rank = get_blackjack_value(dealer_up_card.rank)

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
