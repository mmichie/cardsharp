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
        """Decide whether to buy insurance."""
        pass

    def get_bet_amount(
        self, min_bet: float, max_bet: float, player_money: float
    ) -> float:
        """Determine bet amount for next hand. Called BEFORE cards are dealt."""
        return min_bet

    def receive_exposed_card_info(self, card: Card) -> None:
        """Receives information about a card that has been accidentally exposed."""
        pass

    def get_advantage(self, game_state=None) -> float:
        """Returns the player's estimated advantage as a decimal (e.g., 0.01 = 1%)."""
        return -0.005


class DealerStrategy(Strategy):
    """Dealer plays by fixed rules, respecting the game's dealer_hit_soft_17 setting.

    When a game reference is available, delegates to rules.should_dealer_hit().
    Otherwise falls back to hitting soft 17 (the most common house rule).
    """

    def decide_action(self, player, dealer_up_card=None, game=None) -> Action:
        if player.is_busted():
            return Action.STAND
        hand = player.current_hand
        if game is not None:
            return Action.HIT if game.rules.should_dealer_hit(hand) else Action.STAND
        # Fallback: hit below 17, hit soft 17
        if hand.value() < 17 or (hand.value() == 17 and hand.is_soft):
            return Action.HIT
        return Action.STAND

    def decide_insurance(self, player) -> bool:
        return False


class BasicStrategy(Strategy):
    """Basic strategy using integer-indexed lookup tables for speed.

    Loads the CSV once into three 2D arrays (hard/soft/pair) indexed by
    hand value and dealer upcard. All lookups are direct array access
    with no string operations or dict lookups in the hot path.

    The CSV is H17 (dealer hits soft 17). When S17 rules are detected,
    three cells are patched at runtime.
    """

    # Action constants for array storage (avoids repeated enum construction)
    _HIT = Action.HIT
    _STAND = Action.STAND
    _DOUBLE = Action.DOUBLE
    _DOUBLE_STAND = object()  # Sentinel: double if allowed, otherwise stand
    _SPLIT = Action.SPLIT
    _SURRENDER = Action.SURRENDER

    def __init__(self, strategy_file=None):
        if strategy_file is None:
            strategy_file = os.path.join(
                os.path.dirname(__file__), "basic_strategy.csv"
            )
        self._build_tables(strategy_file)
        self._s17_applied = False

    def _build_tables(self, strategy_file):
        """Build integer-indexed lookup tables from CSV."""
        action_map = {
            "H": self._HIT,
            "S": self._STAND,
            "D": self._DOUBLE,
            "DS": self._DOUBLE_STAND,
            "P": self._SPLIT,
            "R": self._SURRENDER,
        }

        # hard_table[0..17][0..9] = Hard 4-21 vs dealer 2-A
        self.hard_table = [[self._HIT] * 10 for _ in range(18)]
        # soft_table[0..8][0..9] = Soft 13-21 vs dealer 2-A
        self.soft_table = [[self._HIT] * 10 for _ in range(9)]
        # pair_table[0..10][0..9] = Pair 2-A vs dealer 2-A
        #   index 0=pair2, 1=pair3, ..., 8=pair10, 9=pairA
        self.pair_table = [[self._HIT] * 10 for _ in range(10)]

        with open(strategy_file, "r") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                hand_type = row[0].strip()
                actions = [action_map.get(a.strip(), self._HIT) for a in row[1:]]
                if hand_type.startswith("Hard"):
                    v = int(hand_type[4:])
                    if 4 <= v <= 21:
                        self.hard_table[v - 4] = actions
                elif hand_type.startswith("Soft"):
                    v = int(hand_type[4:])
                    if 13 <= v <= 21:
                        self.soft_table[v - 13] = actions
                elif hand_type.startswith("Pair"):
                    p = hand_type[4:]
                    if p == "A":
                        self.pair_table[9] = actions
                    elif p == "10":
                        self.pair_table[8] = actions
                    else:
                        self.pair_table[int(p) - 2] = actions

    @staticmethod
    def _dealer_index(dealer_up_card) -> int:
        """Dealer upcard to table column index (0-9)."""
        bj = dealer_up_card.bj_value
        if bj == 11:  # Ace
            return 9
        if bj >= 10:
            return 8
        return bj - 2

    def _lookup(self, hand, dealer_idx):
        """Look up raw action from the tables."""
        if hand.can_split:
            bj = hand.cards[0].bj_value
            if bj == 11:  # Ace pair
                return self.pair_table[9][dealer_idx]
            if bj == 10:
                return self.pair_table[8][dealer_idx]
            return self.pair_table[bj - 2][dealer_idx]

        v = hand.value()
        if hand.is_soft and 13 <= v <= 21:
            return self.soft_table[v - 13][dealer_idx]
        if 4 <= v <= 21:
            return self.hard_table[v - 4][dealer_idx]
        return self._HIT

    def _apply_s17_overrides(self):
        """Patch the 3 cells that differ between H17 and S17."""
        self.hard_table[11 - 4][9] = self._HIT       # Hard 11 vs A: D → H
        self.soft_table[18 - 13][0] = self._STAND     # Soft 18 vs 2: DS → S
        self.pair_table[8 - 2][9] = self._SPLIT       # Pair 8 vs A: R → P
        self._s17_applied = True

    def decide_action(self, player, dealer_up_card: Card, game=None) -> Action:
        if game is not None and not self._s17_applied:
            if not game.rules.dealer_hit_soft_17:
                self._apply_s17_overrides()
            self._s17_applied = True

        hand = player.current_hand
        dealer_idx = self._dealer_index(dealer_up_card)
        action = self._lookup(hand, dealer_idx)

        return self._get_valid_action(player, action, dealer_idx)

    def _get_valid_action(self, player, action, dealer_idx=None):
        valid_actions = player.valid_actions

        if action is self._DOUBLE_STAND:
            # DS = Double if allowed, otherwise Stand
            if Action.DOUBLE in valid_actions:
                return Action.DOUBLE
            return Action.STAND if Action.STAND in valid_actions else Action.HIT

        if action == Action.DOUBLE:
            if Action.DOUBLE in valid_actions:
                return Action.DOUBLE
            return Action.HIT if Action.HIT in valid_actions else Action.STAND

        if action == Action.SURRENDER:
            if Action.SURRENDER in valid_actions:
                return Action.SURRENDER
            # Surrender unavailable -- for pairs (e.g. 8,8 vs A), split is
            # the correct fallback before defaulting to hit.
            if Action.SPLIT in valid_actions:
                return Action.SPLIT
            return Action.HIT if Action.HIT in valid_actions else Action.STAND

        if action == Action.SPLIT:
            if Action.SPLIT in valid_actions:
                return Action.SPLIT
            # Can't split -- re-evaluate as the hard total.
            # E.g., 9,9 = Hard18 -> Stand, not Hit.
            if dealer_idx is not None:
                v = player.current_hand.value()
                if 4 <= v <= 21:
                    hard_action = self.hard_table[v - 4][dealer_idx]
                    if hard_action in valid_actions:
                        return hard_action
            return Action.HIT if Action.HIT in valid_actions else Action.STAND

        if action in valid_actions:
            return action

        # Last resort fallback
        if Action.HIT in valid_actions:
            return Action.HIT
        if Action.STAND in valid_actions:
            return Action.STAND
        return valid_actions[0]

    def decide_insurance(self, player) -> bool:
        """Basic strategy never takes insurance."""
        return False


# Illustrious 18 deviations for card counting.
# Format: (hand_value, is_soft, dealer_up_value, tc_threshold, action_above, action_below)
_COUNTING_DEVIATIONS = [
    (16, False, 10, 0, Action.STAND, Action.HIT),    # Stand 16 vs 10 at TC >= 0
    (15, False, 10, 4, Action.STAND, Action.HIT),    # Stand 15 vs 10 at TC >= 4
    (12, False, 3, 2, Action.STAND, Action.HIT),     # Stand 12 vs 3 at TC >= 2
    (12, False, 2, 3, Action.STAND, Action.HIT),     # Stand 12 vs 2 at TC >= 3
    (11, False, 11, 1, Action.DOUBLE, None),          # Double 11 vs A at TC >= 1
    (9, False, 2, 1, Action.DOUBLE, None),            # Double 9 vs 2 at TC >= 1
    (10, False, 10, 4, Action.DOUBLE, None),          # Double 10 vs 10 at TC >= 4
    (9, False, 7, 3, Action.DOUBLE, None),            # Double 9 vs 7 at TC >= 3
    (13, False, 2, -1, None, Action.HIT),             # Hit 13 vs 2 at TC < -1
    (12, False, 4, 0, None, Action.HIT),              # Hit 12 vs 4 at TC < 0
    (12, False, 5, -2, None, Action.HIT),             # Hit 12 vs 5 at TC < -2
    (12, False, 6, -1, None, Action.HIT),             # Hit 12 vs 6 at TC < -1
    (13, False, 3, -2, None, Action.HIT),             # Hit 13 vs 3 at TC < -2
]


class CountingStrategy(BasicStrategy):
    def __init__(self, num_decks=6):
        super().__init__()
        self.count = 0
        self.true_count: float = 0
        self.initial_decks = num_decks
        self.decks_remaining: float = num_decks
        self.exposed_cards: list = []
        self.advantage_factor = 0.0
        self.counted_cards: set = set()

    def update_count(self, card: Card):
        if card.rank in (Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX):
            self.count += 1
        elif card.rank in (Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING, Rank.ACE):
            self.count -= 1

    def calculate_true_count(self):
        self.true_count = self.count / max(0.5, self.decks_remaining)

    def receive_exposed_card_info(self, card: Card) -> None:
        self.exposed_cards.append(card)
        self.update_count(card)
        self.advantage_factor += 0.05

    def get_advantage(self, game_state=None) -> float:
        self.calculate_true_count()
        base_advantage = -0.005
        count_advantage = self.true_count * 0.005
        return base_advantage + count_advantage + self.advantage_factor

    def decide_action(self, player, dealer_up_card: Card, game=None) -> Action:
        if game is not None:
            for card in game.visible_cards:
                card_id = id(card)
                if card_id not in self.counted_cards:
                    self.update_count(card)
                    self.counted_cards.add(card_id)

        self.calculate_true_count()
        return self._count_based_decision(player, dealer_up_card, game)

    def _count_based_decision(self, player, dealer_up_card: Card, game) -> Action:
        """Apply the Illustrious 18 count-based play deviations."""
        hand_value = player.current_hand.value()
        is_soft = player.current_hand.is_soft
        dealer_value = get_blackjack_value(dealer_up_card.rank)

        for hand, soft, dealer, tc_threshold, action_above, action_below in _COUNTING_DEVIATIONS:
            if hand_value == hand and is_soft == soft and dealer_value == dealer:
                if action_above and self.true_count >= tc_threshold:
                    if action_above == Action.DOUBLE and not player.current_hand.can_double:
                        return Action.HIT
                    return action_above
                if action_below and self.true_count < tc_threshold:
                    return action_below

        # Default to basic strategy
        return super().decide_action(player, dealer_up_card, game)

    def get_bet_amount(
        self, min_bet: float, max_bet: float, player_money: float
    ) -> float:
        """Determine bet amount based on current true count.

        Standard bet ramp: minimum at TC <= +1 (house still has edge),
        escalate from TC +2 where the player edge begins. Each TC point
        is worth ~0.5% advantage.
        """
        self.calculate_true_count()

        # Truncate TC toward zero (standard Hi-Lo convention)
        tc = int(self.true_count) if self.true_count >= 0 else -int(-self.true_count)

        if tc <= 1:
            bet_multiplier = 1    # House edge or breakeven -- bet minimum
        elif tc == 2:
            bet_multiplier = 4    # ~0.5% player edge
        elif tc == 3:
            bet_multiplier = 8    # ~1.0% player edge
        elif tc == 4:
            bet_multiplier = 12   # ~1.5% player edge
        else:
            bet_multiplier = 20   # TC 5+ : ~2%+ player edge, max bet

        bet = min_bet * bet_multiplier
        return min(bet, max_bet, player_money)

    def decide_insurance(self, player) -> bool:
        """Take insurance when true count >= 3."""
        self.calculate_true_count()
        return self.true_count >= 3

    def notify_shuffle(self):
        """Called when the shoe is shuffled to reset the count."""
        self.reset_count()

    def update_decks_remaining(self, cards_played):
        total_cards = 52 * self.initial_decks
        self.decks_remaining = max(0.5, (total_cards - cards_played) / 52)

    def reset_count(self):
        """Reset the count at the start of a new shoe."""
        self.count = 0
        self.true_count = 0.0
        self.decks_remaining = float(self.initial_decks)
        self.counted_cards.clear()


class MartingaleStrategy(BasicStrategy):
    def __init__(self, initial_bet=10, max_bet_override=None):
        super().__init__()
        self.initial_bet = initial_bet
        self.current_bet = initial_bet
        self.max_bet_override = max_bet_override
        self.consecutive_losses = 0
        self.last_money = 1000
        self.last_bet = initial_bet

    def decide_action(self, player, dealer_up_card: Card, game=None) -> Action:
        if hasattr(player, 'money'):
            money_change = player.money - self.last_money

            if money_change > 0:
                self.current_bet = self.initial_bet
                self.consecutive_losses = 0
            elif money_change < -self.last_bet / 2:
                self.consecutive_losses += 1
                self.current_bet = self.current_bet * 2

            self.last_money = player.money

        return super().decide_action(player, dealer_up_card, game)

    def get_bet_amount(self, min_bet: float, max_bet: float, player_money: float) -> float:
        """Martingale: double bet after loss, reset to initial after win."""
        effective_max = self.max_bet_override if self.max_bet_override is not None else max_bet
        bet = max(min_bet, min(self.current_bet, effective_max, player_money))
        self.last_bet = bet
        self.last_money = player_money - bet
        return bet

    def reset_bet(self):
        self.current_bet = self.initial_bet
        self.consecutive_losses = 0


class AggressiveStrategy(BasicStrategy):
    """An aggressive strategy that hits more often and doubles down more frequently."""

    def decide_action(self, player, dealer_up_card: Card, game=None) -> Action:
        current_hand = player.current_hand
        if current_hand.is_blackjack:
            return Action.STAND

        for action_method in (
            self._decide_on_split,
            self._decide_on_double,
            self._decide_on_stand_or_hit,
        ):
            action = action_method(current_hand, dealer_up_card)
            if action is not None:
                return action

        return Action.HIT

    def _decide_on_split(self, current_hand, dealer_up_card: Card) -> Optional[Action]:
        if not current_hand.can_split:
            return None

        player_rank = current_hand.cards[0].rank
        dealer_rank = get_blackjack_value(dealer_up_card.rank)

        if player_rank in (Rank.ACE, Rank.EIGHT):
            return Action.SPLIT
        if player_rank in (Rank.TWO, Rank.THREE, Rank.SIX, Rank.SEVEN) and dealer_rank <= 7:
            return Action.SPLIT
        if player_rank == Rank.NINE and dealer_rank <= 9 and dealer_rank != 7:
            return Action.SPLIT
        return None

    def _decide_on_double(self, current_hand, dealer_up_card: Card) -> Optional[Action]:
        if not current_hand.can_double:
            return None

        hand_value = current_hand.value()
        dealer_rank = get_blackjack_value(dealer_up_card.rank)

        if 9 <= hand_value <= 11 and dealer_rank <= 9:
            return Action.DOUBLE
        if current_hand.is_soft and 13 <= hand_value <= 18 and dealer_rank <= 6:
            return Action.DOUBLE
        return None

    def _decide_on_stand_or_hit(self, current_hand, dealer_up_card: Card) -> Action:
        hand_value = current_hand.value()
        dealer_rank = get_blackjack_value(dealer_up_card.rank)

        if current_hand.is_soft:
            if hand_value <= 17:
                return Action.HIT
            if hand_value == 18 and dealer_rank >= 9:
                return Action.HIT
            return Action.STAND
        else:
            if hand_value <= 11:
                return Action.HIT
            if 12 <= hand_value <= 16 and dealer_rank >= 7:
                return Action.HIT
            return Action.STAND
