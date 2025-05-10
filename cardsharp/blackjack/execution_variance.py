"""
Variance and deviation modeling for strategy execution.

This module provides implementations of strategy execution variance,
including counting errors for card counting strategies, bet sizing variation,
and decision timing effects.
"""

import random
import time
import math
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.strategy import Strategy, CountingStrategy
from cardsharp.common.card import Card, Rank


class CountingAccuracy(Enum):
    """Accuracy levels for card counting."""

    PERFECT = 1.0  # No errors
    EXCELLENT = 0.95  # 5% error rate
    GOOD = 0.9  # 10% error rate
    AVERAGE = 0.8  # 20% error rate
    FAIR = 0.7  # 30% error rate
    POOR = 0.5  # 50% error rate


class BettingStyle(Enum):
    """Betting styles for varying bet sizes."""

    CONSISTENT = auto()  # Consistent bet sizing based on count
    CONSERVATIVE = auto()  # More conservative bet ramps
    AGGRESSIVE = auto()  # More aggressive bet ramps
    STEALTH = auto()  # More random bet sizing to avoid detection
    FLAT = auto()  # Flat betting regardless of count


class ImperfectCountingStrategy(CountingStrategy):
    """
    A card counting strategy with errors and realistic execution variance.

    This strategy models the errors that a real card counter might make,
    including miscounting cards, miscalculating the true count, and
    making bet sizing errors.
    """

    def __init__(
        self,
        accuracy: CountingAccuracy = CountingAccuracy.GOOD,
        betting_style: BettingStyle = BettingStyle.CONSISTENT,
        bet_spread: int = 10,
    ):
        """
        Initialize an imperfect counting strategy.

        Args:
            accuracy: The accuracy of card counting
            betting_style: The betting style to use
            bet_spread: The maximum bet spread (1-10 means betting 1x to 10x the minimum)
        """
        super().__init__()
        self.accuracy = accuracy.value
        self.betting_style = betting_style
        self.bet_spread = max(1, bet_spread)

        # Tracking actual vs. perceived values
        self.true_count = 0
        self.perceived_count = 0
        self.true_count_history: List[float] = []
        self.perceived_count_history: List[float] = []

        # Error tracking
        self.counting_errors = 0
        self.total_cards_counted = 0

        # Timing tracking
        self.decision_times: List[float] = []

    def update_count(self, card: Card) -> None:
        """
        Update the count with possible errors.

        Args:
            card: The card to update the count with
        """
        # Track total cards counted
        self.total_cards_counted += 1

        # First, update the true count correctly (for tracking purposes)
        if card.rank in [Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX]:
            self.count += 1
        elif card.rank in [Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING, Rank.ACE]:
            self.count -= 1

        # Now, determine if we make a counting error
        if random.random() > self.accuracy:
            # Make a counting error
            self.counting_errors += 1

            # Different types of errors
            error_type = random.randint(1, 3)

            if error_type == 1:
                # Miss the card completely (do nothing to perceived count)
                pass
            elif error_type == 2:
                # Count the card with the wrong value
                if card.rank in [Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX]:
                    # Should be +1, but count as -1
                    self.perceived_count -= 1
                elif card.rank in [
                    Rank.TEN,
                    Rank.JACK,
                    Rank.QUEEN,
                    Rank.KING,
                    Rank.ACE,
                ]:
                    # Should be -1, but count as +1
                    self.perceived_count += 1
            elif error_type == 3:
                # Count a neutral card as something else
                if card.rank not in [
                    Rank.TWO,
                    Rank.THREE,
                    Rank.FOUR,
                    Rank.FIVE,
                    Rank.SIX,
                    Rank.TEN,
                    Rank.JACK,
                    Rank.QUEEN,
                    Rank.KING,
                    Rank.ACE,
                ]:
                    # Randomly count as +1 or -1
                    self.perceived_count += random.choice([1, -1])
        else:
            # Count correctly
            if card.rank in [Rank.TWO, Rank.THREE, Rank.FOUR, Rank.FIVE, Rank.SIX]:
                self.perceived_count += 1
            elif card.rank in [Rank.TEN, Rank.JACK, Rank.QUEEN, Rank.KING, Rank.ACE]:
                self.perceived_count -= 1

    def calculate_true_count(self) -> None:
        """
        Calculate the true count with possible errors.
        """
        # Calculate the true true count (for tracking)
        if self.decks_remaining > 0:
            self.true_count = self.count / self.decks_remaining
        else:
            self.true_count = 0

        # Calculate the perceived true count with possible errors
        if self.decks_remaining > 0:
            # Possible errors in estimating remaining decks
            perceived_decks = max(0.5, self.decks_remaining + random.uniform(-0.5, 0.5))
            self.perceived_count_true = self.perceived_count / perceived_decks
        else:
            self.perceived_count_true = 0

        # Track history for analysis
        self.true_count_history.append(self.true_count)
        self.perceived_count_history.append(self.perceived_count_true)

    def adjust_bet(self, player) -> None:
        """
        Adjust the bet size based on the perceived count and betting style.

        Args:
            player: The player to adjust the bet for
        """
        self.calculate_true_count()

        # Base bet is the player's current bet
        base_bet = player.bets[0] if player.bets else 10

        # Calculate the bet multiplier based on the betting style
        bet_multiplier = 1.0

        if self.betting_style == BettingStyle.FLAT:
            # Always bet the same amount
            bet_multiplier = 1.0
        else:
            # Adjust based on perceived true count
            perceived_count = self.perceived_count_true

            if self.betting_style == BettingStyle.CONSISTENT:
                # Linear progression based on count
                if perceived_count > 0:
                    bet_multiplier = 1.0 + min(perceived_count, self.bet_spread - 1)

            elif self.betting_style == BettingStyle.CONSERVATIVE:
                # More conservative progression
                if (
                    perceived_count > 1
                ):  # Only increase bet when count is clearly favorable
                    bet_multiplier = (
                        1.0 + min(perceived_count - 1, self.bet_spread - 1) * 0.75
                    )

            elif self.betting_style == BettingStyle.AGGRESSIVE:
                # More aggressive progression
                if perceived_count > 0:
                    bet_multiplier = 1.0 + min(
                        perceived_count * 1.5, self.bet_spread - 1
                    )

            elif self.betting_style == BettingStyle.STEALTH:
                # More random to avoid detection
                if perceived_count > 0:
                    # Base multiplier from count
                    base_multi = 1.0 + min(perceived_count, self.bet_spread - 1)
                    # Add randomness (-20% to +20%)
                    bet_multiplier = base_multi * random.uniform(0.8, 1.2)
                else:
                    # Add some random variation even with negative count
                    bet_multiplier = random.uniform(0.8, 1.2)

        # Calculate new bet with a minimum of the base bet
        new_bet = max(base_bet, int(base_bet * bet_multiplier))

        # Cap at maximum allowed bet and player's money
        max_bet = min(player.money, self.max_bet if hasattr(self, "max_bet") else 1000)
        player.bets[0] = min(new_bet, max_bet)

    def decide_action(self, player, dealer_up_card: Card, game) -> Action:
        """
        Decide which action to take with timing effects.

        Args:
            player: The player making the decision
            dealer_up_card: The dealer's up card
            game: The game instance

        Returns:
            The action to take
        """
        # Record start time for decision timing analysis
        start_time = time.time()

        # Update count for visible cards
        for card in game.visible_cards:
            self.update_count(card)

        # Calculate true count
        self.calculate_true_count()

        # Adjust bet size
        self.adjust_bet(player)

        # Get the action from the parent class
        action = super().decide_action(player, dealer_up_card, game)

        # Record decision time
        end_time = time.time()
        decision_time = end_time - start_time
        self.decision_times.append(decision_time)

        return action

    def decide_insurance(self, player) -> bool:
        """
        Decide whether to buy insurance based on the perceived count.

        Args:
            player: The player making the decision

        Returns:
            True if the player wants to buy insurance, False otherwise
        """
        # Perfect strategy only takes insurance when the true count is > 3
        threshold = 3.0

        # Take insurance if the perceived true count is high enough
        if self.perceived_count_true > threshold:
            return True

        return False

    def update_decks_remaining(self, cards_played: int) -> None:
        """
        Update the decks remaining estimate.

        Args:
            cards_played: The number of cards played so far
        """
        total_cards = 52 * 6  # Assuming 6 decks
        self.decks_remaining = (total_cards - cards_played) / 52

    def reset_count(self) -> None:
        """Reset the count and related statistics."""
        super().reset_count()
        self.perceived_count = 0
        self.perceived_count_true = 0
        # Keep the history for analysis

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the counting strategy's performance.

        Returns:
            A dictionary with counting statistics
        """
        error_rate = 0
        if self.total_cards_counted > 0:
            error_rate = self.counting_errors / self.total_cards_counted

        avg_decision_time = 0
        if self.decision_times:
            avg_decision_time = sum(self.decision_times) / len(self.decision_times)

        count_diff = 0
        if len(self.true_count_history) > 0 and len(self.perceived_count_history) > 0:
            # Average absolute difference between true and perceived counts
            diffs = [
                abs(t - p)
                for t, p in zip(self.true_count_history, self.perceived_count_history)
            ]
            count_diff = sum(diffs) / len(diffs) if diffs else 0

        return {
            "accuracy": self.accuracy,
            "betting_style": self.betting_style.name,
            "total_cards_counted": self.total_cards_counted,
            "counting_errors": self.counting_errors,
            "error_rate": error_rate,
            "avg_decision_time": avg_decision_time,
            "current_true_count": self.true_count,
            "current_perceived_count": self.perceived_count_true,
            "avg_count_difference": count_diff,
        }


class BetSizingVariation:
    """
    Adds natural variation to bet sizing.

    This class models the natural variations in bet sizing that occur
    even when following a fixed strategy, such as rounding to convenient
    chip denominations or random fluctuations.
    """

    def __init__(
        self, base_bet: int = 10, max_bet: int = 1000, variation_factor: float = 0.1
    ):
        """
        Initialize bet sizing variation.

        Args:
            base_bet: The base bet amount
            max_bet: The maximum bet allowed
            variation_factor: How much to vary bets (0.0 to 1.0)
        """
        self.base_bet = base_bet
        self.max_bet = max_bet
        self.variation_factor = max(0.0, min(1.0, variation_factor))

        # Common chip denominations for rounding
        self.chip_denominations = [1, 5, 10, 25, 100]

    def vary_bet(self, target_bet: int) -> int:
        """
        Apply variation to a target bet amount.

        Args:
            target_bet: The target bet amount from the strategy

        Returns:
            The varied bet amount
        """
        # Apply random variation
        variation_amount = target_bet * self.variation_factor
        varied_bet = target_bet + random.uniform(-variation_amount, variation_amount)

        # Round to nearest chip denomination for realism
        closest_chip = min(
            self.chip_denominations, key=lambda x: abs(x - varied_bet % 100)
        )
        rounded_bet = int(varied_bet // 100) * 100 + closest_chip

        # Ensure bet is within bounds
        return max(self.base_bet, min(rounded_bet, self.max_bet))


class TimingBasedQuality:
    """
    Affects decision quality based on timing pressure.

    This class models the effects of time pressure on decision quality,
    where decisions made quickly are more likely to deviate from optimal.
    """

    def __init__(self, time_limit: float = 0.0, quality_decay: float = 0.5):
        """
        Initialize timing-based quality.

        Args:
            time_limit: The time limit for decisions (0 for no limit)
            quality_decay: How quickly quality decays under time pressure
        """
        self.time_limit = time_limit
        self.quality_decay = max(0.0, min(1.0, quality_decay))

        # Tracking
        self.decision_start_time = 0.0
        self.time_pressure_errors = 0
        self.total_decisions = 0

    def start_decision(self) -> None:
        """Mark the start of a decision."""
        self.decision_start_time = time.time()
        self.total_decisions += 1

    def get_decision_quality(self) -> float:
        """
        Get the current decision quality based on time elapsed.

        Returns:
            A quality factor between 0.0 and 1.0
        """
        if self.time_limit <= 0:
            return 1.0  # No time limit, perfect quality

        elapsed_time = time.time() - self.decision_start_time
        time_ratio = elapsed_time / self.time_limit

        # Decision quality decreases as time pressure increases
        quality = 1.0 - (time_ratio * self.quality_decay)

        # If quality is low, count it as a time pressure error
        if quality < 0.7:  # Arbitrary threshold
            self.time_pressure_errors += 1

        return max(0.0, min(1.0, quality))

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about time pressure errors.

        Returns:
            A dictionary with time pressure statistics
        """
        error_rate = 0
        if self.total_decisions > 0:
            error_rate = self.time_pressure_errors / self.total_decisions

        return {
            "time_limit": self.time_limit,
            "quality_decay": self.quality_decay,
            "total_decisions": self.total_decisions,
            "time_pressure_errors": self.time_pressure_errors,
            "error_rate": error_rate,
        }


class ExecutionVarianceWrapper(Strategy):
    """
    A strategy wrapper that adds execution variance.

    This class combines multiple sources of execution variance,
    including counting errors, bet sizing variation, and timing effects.
    """

    def __init__(
        self,
        base_strategy: Strategy,
        bet_variation: Optional[BetSizingVariation] = None,
        timing_quality: Optional[TimingBasedQuality] = None,
    ):
        """
        Initialize an execution variance wrapper.

        Args:
            base_strategy: The base strategy to wrap
            bet_variation: The bet sizing variation to apply
            timing_quality: The timing-based quality effect to apply
        """
        self.base_strategy = base_strategy
        self.bet_variation = bet_variation or BetSizingVariation()
        self.timing_quality = timing_quality or TimingBasedQuality()

    def decide_action(self, player, dealer_up_card, game=None) -> Action:
        """
        Decide which action to take with execution variance.

        Args:
            player: The player making the decision
            dealer_up_card: The dealer's up card
            game: The game instance

        Returns:
            The action to take
        """
        # Start timing for decision quality
        self.timing_quality.start_decision()

        # Get the base action
        action = self.base_strategy.decide_action(player, dealer_up_card, game)

        # Apply timing-based quality
        quality = self.timing_quality.get_decision_quality()

        # If quality is low, consider deviating
        if quality < 1.0 and random.random() > quality:
            # Get available actions
            available_actions = player.valid_actions

            # If there are alternative actions, possibly choose a different one
            if len(available_actions) > 1:
                other_actions = [a for a in available_actions if a != action]
                action = random.choice(other_actions)

        return action

    def decide_insurance(self, player) -> bool:
        """
        Decide whether to buy insurance with execution variance.

        Args:
            player: The player making the decision

        Returns:
            True if the player wants to buy insurance, False otherwise
        """
        # Start timing for decision quality
        self.timing_quality.start_decision()

        # Get the base decision
        decision = self.base_strategy.decide_insurance(player)

        # Apply timing-based quality
        quality = self.timing_quality.get_decision_quality()

        # If quality is low, consider deviating
        if quality < 1.0 and random.random() > quality:
            decision = not decision

        return decision

    def adjust_bet(self, player) -> None:
        """
        Adjust the bet size with variation.

        Args:
            player: The player to adjust the bet for
        """
        # If the base strategy has an adjust_bet method, call it first
        if hasattr(self.base_strategy, "adjust_bet"):
            self.base_strategy.adjust_bet(player)

        # Apply bet variation
        if player.bets:
            player.bets[0] = self.bet_variation.vary_bet(player.bets[0])

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the execution variance.

        Returns:
            A dictionary with execution variance statistics
        """
        stats = {"timing_quality": self.timing_quality.get_stats()}

        # If base strategy has get_stats, include those
        if hasattr(self.base_strategy, "get_stats"):
            stats["base_strategy"] = self.base_strategy.get_stats()

        return stats
