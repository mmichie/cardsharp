"""
Bankroll management simulation for blackjack.

This module provides classes and functions for realistic bankroll management
strategies, including risk-based betting, win/loss goals, and session management.
"""

import random
import time
import math
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Callable, Union

from cardsharp.blackjack.casino import TableConditions

# Import weighted_choice from casino.py
from cardsharp.blackjack.casino import weighted_choice


@dataclass
class BankrollParameters:
    """
    Parameters for bankroll management strategy.

    Attributes:
        risk_tolerance: How aggressively to bet (0-1)
        bet_spread: Max bet as multiple of min bet for counting systems
        target_roi: Target return on investment (0.2 = 20%)
        stop_loss: Stop loss as fraction of bankroll (0.5 = 50%)
        stop_win: Stop win as fraction of bankroll (1.0 = 100%)
        rebuy_threshold: Rebuy when bankroll drops below this fraction
        rebuy_amount: Amount to rebuy as fraction of initial bankroll
        session_time_target: Target session length in hours
        kelly_fraction: Fraction of Kelly criterion to use (0-1)
    """

    risk_tolerance: float = 0.5
    bet_spread: float = 8.0  # max bet as multiple of min bet
    target_roi: float = 0.2  # target 20% ROI
    stop_loss: float = 0.5  # stop after losing 50% of bankroll
    stop_win: float = 1.0  # stop after doubling bankroll
    rebuy_threshold: float = 0.2  # rebuy when below 20% of initial
    rebuy_amount: float = 0.5  # rebuy 50% of initial bankroll
    session_time_target: float = 4.0  # 4 hours
    kelly_fraction: float = 0.5  # use half Kelly


class BasicBankrollManager:
    """
    Basic bankroll management strategy with fixed betting.
    """

    def __init__(self, initial_bankroll: float, params: BankrollParameters = None):
        """
        Initialize a basic bankroll manager.

        Args:
            initial_bankroll: Starting bankroll amount
            params: BankrollParameters object or None to use defaults
        """
        self.initial_bankroll = initial_bankroll
        self.current_bankroll = initial_bankroll
        self.params = params or BankrollParameters()

        # Session tracking
        self.session_start_bankroll = initial_bankroll
        self.session_start_time = time.time()
        self.hands_played = 0
        self.total_wagered = 0.0
        self.session_high = initial_bankroll
        self.session_low = initial_bankroll
        self.rebuy_count = 0
        self.total_rebuy_amount = 0.0

        # Betting strategy
        self.base_bet = None

    def calculate_bet(self, table: TableConditions, advantage: float = 0.0) -> float:
        """
        Calculate bet amount based on bankroll and table conditions.

        Args:
            table: Current table conditions
            advantage: Current player advantage (0.01 = 1% player edge)

        Returns:
            Bet amount
        """
        # If base bet isn't set, initialize it
        if self.base_bet is None:
            # Target having enough for ~100 bets at the table minimum
            target_bankroll_fraction = 0.01  # aim for 1% of bankroll per hand
            target_bet = self.initial_bankroll * target_bankroll_fraction

            # But respect table minimums
            self.base_bet = max(table.minimum_bet, target_bet)
            self.base_bet = min(self.base_bet, table.maximum_bet)

            # Round to appropriate chip denomination
            if self.base_bet < 25:
                self.base_bet = round(self.base_bet / 5) * 5  # nearest $5
            elif self.base_bet < 100:
                self.base_bet = round(self.base_bet / 25) * 25  # nearest $25
            else:
                self.base_bet = round(self.base_bet / 100) * 100  # nearest $100

        # Start with base bet
        bet = self.base_bet

        # If we have an advantage, scale up the bet based on the advantage
        if advantage > 0:
            # Scale between 1x and bet_spread based on advantage
            # Typical advantage rarely exceeds 2% even with perfect counting
            scale_factor = 1.0 + min(1.0, advantage / 0.02) * (
                self.params.bet_spread - 1.0
            )
            bet *= scale_factor

        # Protect against overbetting
        max_safe_bet = (
            self.current_bankroll * 0.1
        )  # don't bet more than 10% of bankroll
        bet = min(bet, max_safe_bet)

        # Respect table limits
        bet = max(table.minimum_bet, min(table.maximum_bet, bet))

        # Round to appropriate chip denomination
        if bet < 25:
            return round(bet / 5) * 5  # nearest $5
        elif bet < 100:
            return round(bet / 25) * 25  # nearest $25
        else:
            return round(bet / 100) * 100  # nearest $100

    def should_continue_session(self) -> bool:
        """
        Determine if the player should continue the session.

        Returns:
            Boolean indicating whether to continue playing
        """
        elapsed_hours = (time.time() - self.session_start_time) / 3600.0
        net_result = self.current_bankroll - self.session_start_bankroll
        roi = (
            net_result / self.session_start_bankroll
            if self.session_start_bankroll > 0
            else 0
        )

        # Check time-based stop
        if elapsed_hours >= self.params.session_time_target:
            return False

        # Check win-based stop
        if roi >= self.params.stop_win:
            return False

        # Check loss-based stop
        if roi <= -self.params.stop_loss:
            return False

        # Don't play if we can't afford the typical minimum bet
        if self.current_bankroll < 10 and self.rebuy_count >= 3:
            return False

        return True

    def consider_rebuy(self) -> Tuple[bool, float]:
        """
        Consider whether to rebuy based on current bankroll.

        Returns:
            Tuple of (should_rebuy, rebuy_amount)
        """
        rebuy_threshold = self.initial_bankroll * self.params.rebuy_threshold

        if self.current_bankroll < rebuy_threshold and self.rebuy_count < 3:
            rebuy_amount = self.initial_bankroll * self.params.rebuy_amount
            return True, rebuy_amount

        return False, 0

    def perform_rebuy(self, amount: float):
        """
        Add funds to the bankroll through a rebuy.

        Args:
            amount: Amount to add to bankroll
        """
        self.current_bankroll += amount
        self.rebuy_count += 1
        self.total_rebuy_amount += amount

    def update_bankroll(self, result: float, bet_amount: float):
        """
        Update bankroll after a hand result.

        Args:
            result: Net win/loss amount
            bet_amount: Amount bet on this hand
        """
        self.current_bankroll += result
        self.hands_played += 1
        self.total_wagered += bet_amount

        # Update session highs and lows
        self.session_high = max(self.session_high, self.current_bankroll)
        self.session_low = min(self.session_low, self.current_bankroll)

        # Check if we need to rebuy
        should_rebuy, rebuy_amount = self.consider_rebuy()
        if should_rebuy:
            self.perform_rebuy(rebuy_amount)

    def get_session_stats(self) -> Dict:
        """
        Get current session statistics.

        Returns:
            Dictionary of session statistics
        """
        elapsed_hours = (time.time() - self.session_start_time) / 3600.0
        net_result = (
            self.current_bankroll
            - self.session_start_bankroll
            - self.total_rebuy_amount
        )
        initial_plus_rebuys = self.session_start_bankroll + self.total_rebuy_amount
        roi = net_result / initial_plus_rebuys if initial_plus_rebuys > 0 else 0

        return {
            "hands_played": self.hands_played,
            "elapsed_hours": elapsed_hours,
            "hands_per_hour": self.hands_played / elapsed_hours
            if elapsed_hours > 0
            else 0,
            "starting_bankroll": self.session_start_bankroll,
            "current_bankroll": self.current_bankroll,
            "net_result": net_result,
            "roi_percentage": roi * 100,
            "total_wagered": self.total_wagered,
            "session_high": self.session_high,
            "session_low": self.session_low,
            "drawdown_percentage": (self.session_high - self.session_low)
            / self.session_high
            * 100
            if self.session_high > 0
            else 0,
            "rebuy_count": self.rebuy_count,
            "total_rebuy_amount": self.total_rebuy_amount,
        }


class KellyBankrollManager(BasicBankrollManager):
    """
    Bankroll manager that uses the Kelly Criterion for bet sizing.
    """

    def calculate_bet(self, table: TableConditions, advantage: float = 0.0) -> float:
        """
        Calculate bet amount using Kelly Criterion.

        Args:
            table: Current table conditions
            advantage: Current player advantage (0.01 = 1% player edge)

        Returns:
            Bet amount
        """
        # If we have no advantage or disadvantage, bet the minimum
        if advantage <= 0:
            return table.minimum_bet

        # Kelly formula: f* = edge / variance
        # For blackjack, variance is approximately 1.3
        variance = 1.3
        kelly_bet_fraction = advantage / variance

        # Apply the Kelly fraction to reduce volatility
        kelly_bet_fraction *= self.params.kelly_fraction

        # Calculate the bet amount
        kelly_bet = self.current_bankroll * kelly_bet_fraction

        # Cap the bet as a percentage of bankroll for safety
        max_bet_pct = 0.05  # never bet more than 5% of bankroll
        max_safe_bet = self.current_bankroll * max_bet_pct
        bet = min(kelly_bet, max_safe_bet)

        # Respect table limits
        bet = max(table.minimum_bet, min(table.maximum_bet, bet))

        # Round to appropriate chip denomination
        if bet < 25:
            return round(bet / 5) * 5  # nearest $5
        elif bet < 100:
            return round(bet / 25) * 25  # nearest $25
        else:
            return round(bet / 100) * 100  # nearest $100


class ProgressiveBankrollManager(BasicBankrollManager):
    """
    Bankroll manager that implements progressive betting strategies.
    """

    def __init__(
        self,
        initial_bankroll: float,
        params: BankrollParameters = None,
        progression_type: str = "martingale",
        progression_limit: int = 4,
    ):
        """
        Initialize a progressive bankroll manager.

        Args:
            initial_bankroll: Starting bankroll amount
            params: BankrollParameters object or None to use defaults
            progression_type: Type of progression ('martingale', 'paroli', etc.)
            progression_limit: Maximum number of progression steps
        """
        super().__init__(initial_bankroll, params)
        self.progression_type = progression_type
        self.progression_limit = progression_limit

        # Progression state
        self.current_progression = 0
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.progression_active = False
        self.last_bet = None
        self.last_result = None

    def calculate_bet(self, table: TableConditions, advantage: float = 0.0) -> float:
        """
        Calculate bet amount using the selected progression strategy.

        Args:
            table: Current table conditions
            advantage: Current player advantage (0.01 = 1% player edge)

        Returns:
            Bet amount
        """
        # If we don't have a base bet yet, calculate it
        if self.base_bet is None:
            # Set a conservative base bet
            target_bankroll_fraction = 0.005  # 0.5% of bankroll as base bet
            self.base_bet = self.initial_bankroll * target_bankroll_fraction

            # Respect table limits
            self.base_bet = max(table.minimum_bet, self.base_bet)
            self.base_bet = min(table.maximum_bet, self.base_bet)

            # Round to appropriate chip denomination
            if self.base_bet < 25:
                self.base_bet = round(self.base_bet / 5) * 5  # nearest $5
            elif self.base_bet < 100:
                self.base_bet = round(self.base_bet / 25) * 25  # nearest $25
            else:
                self.base_bet = round(self.base_bet / 100) * 100  # nearest $100

        # Calculate progression bet
        bet = self.base_bet

        if self.progression_type == "martingale":
            # Double bet after each loss, reset after win
            if self.last_result is not None:
                if self.last_result < 0:  # loss
                    self.consecutive_losses += 1
                    if self.consecutive_losses <= self.progression_limit:
                        bet = self.base_bet * (2**self.consecutive_losses)
                    else:
                        # Reset if we hit the progression limit
                        self.consecutive_losses = 0
                        bet = self.base_bet
                else:  # win or push
                    self.consecutive_losses = 0
                    bet = self.base_bet

        elif self.progression_type == "paroli":
            # Increase bet after wins, reset after loss or hitting limit
            if self.last_result is not None:
                if self.last_result > 0:  # win
                    self.consecutive_wins += 1
                    if self.consecutive_wins <= self.progression_limit:
                        bet = self.base_bet * (2**self.consecutive_wins)
                    else:
                        # Reset if we hit the progression limit
                        self.consecutive_wins = 0
                        bet = self.base_bet
                else:  # loss or push
                    self.consecutive_wins = 0
                    bet = self.base_bet

        elif self.progression_type == "oscar":
            # Oscar's Grind: Increase bet by one unit after a win,
            # bet to win one unit overall
            if (
                not self.progression_active
                and self.last_result is not None
                and self.last_result < 0
            ):
                # Start progression after a loss
                self.progression_active = True
                self.current_progression = 1
                bet = self.base_bet
            elif self.progression_active:
                if self.last_result is not None:
                    if self.last_result > 0:  # win
                        # If we've reached our goal (1 unit profit), reset
                        if self.current_progression <= 0:
                            self.progression_active = False
                            bet = self.base_bet
                        else:
                            # Otherwise increase bet by one unit (capped at progression limit)
                            self.current_progression = min(
                                self.current_progression + 1, self.progression_limit
                            )
                            bet = self.base_bet * self.current_progression
                    else:  # loss or push
                        # Keep same bet
                        bet = self.base_bet * self.current_progression

        # Apply advantage adjustment
        if advantage > 0:
            advantage_factor = 1.0 + (
                advantage * 10.0
            )  # scale up linearly with advantage
            bet *= advantage_factor

        # Protect against overbetting
        max_safe_bet = (
            self.current_bankroll * 0.2
        )  # don't bet more than 20% of bankroll
        bet = min(bet, max_safe_bet)

        # Respect table limits
        bet = max(table.minimum_bet, min(table.maximum_bet, bet))

        # Round to appropriate chip denomination
        if bet < 25:
            bet = round(bet / 5) * 5  # nearest $5
        elif bet < 100:
            bet = round(bet / 25) * 25  # nearest $25
        else:
            bet = round(bet / 100) * 100  # nearest $100

        self.last_bet = bet
        return bet

    def update_bankroll(self, result: float, bet_amount: float):
        """
        Update bankroll and progression state after a hand result.

        Args:
            result: Net win/loss amount
            bet_amount: Amount bet on this hand
        """
        super().update_bankroll(result, bet_amount)

        # Record result for progression tracking
        self.last_result = result

        # Update current progression for Oscar's Grind
        if self.progression_type == "oscar" and self.progression_active:
            self.current_progression -= result / bet_amount


class AdaptiveBankrollManager(BasicBankrollManager):
    """
    Bankroll manager that adapts to changing conditions and results.
    """

    def __init__(self, initial_bankroll: float, params: BankrollParameters = None):
        """
        Initialize an adaptive bankroll manager.

        Args:
            initial_bankroll: Starting bankroll amount
            params: BankrollParameters object or None to use defaults
        """
        super().__init__(initial_bankroll, params)

        # Performance tracking
        self.win_rate = 0.5  # estimated win rate, start at 50%
        self.win_history = []  # recent win/loss history
        self.history_window = 20  # how many hands to use for adaptation
        self.confidence_factor = 0.0  # how confident we are in our edge

        # Adaptation parameters
        self.adaptation_rate = 0.1  # how quickly to adapt (0-1)
        self.risk_adjustment = 0.0  # current risk adjustment factor

    def _update_win_rate(self, won: bool):
        """Update the estimated win rate based on recent results."""
        # Add result to history
        self.win_history.append(1 if won else 0)

        # Trim history to window size
        if len(self.win_history) > self.history_window:
            self.win_history = self.win_history[-self.history_window :]

        # Update win rate as moving average
        if self.win_history:
            self.win_rate = sum(self.win_history) / len(self.win_history)

        # Update confidence factor based on sample size
        self.confidence_factor = min(1.0, len(self.win_history) / self.history_window)

    def _update_risk_adjustment(self):
        """Update risk adjustment factor based on performance."""
        # Baseline win rate for blackjack is around 43-49% depending on rules
        baseline_win_rate = 0.46

        # Calculate performance vs baseline
        win_rate_edge = self.win_rate - baseline_win_rate

        # Adjust risk based on performance and confidence
        target_adjustment = win_rate_edge * 2.0 * self.confidence_factor

        # Gradually move toward target adjustment
        self.risk_adjustment += (
            target_adjustment - self.risk_adjustment
        ) * self.adaptation_rate

        # Limit the adjustment range
        self.risk_adjustment = max(-0.5, min(0.5, self.risk_adjustment))

    def calculate_bet(self, table: TableConditions, advantage: float = 0.0) -> float:
        """
        Calculate bet amount using adaptive strategy.

        Args:
            table: Current table conditions
            advantage: Current player advantage (0.01 = 1% player edge)

        Returns:
            Bet amount
        """
        # Update risk adjustment
        self._update_risk_adjustment()

        # Start with basic calculation
        bet = super().calculate_bet(table, advantage)

        # Apply risk adjustment
        if self.risk_adjustment > 0:
            # Increase bet when we appear to have an edge
            bet *= 1.0 + self.risk_adjustment
        elif self.risk_adjustment < 0:
            # Decrease bet when we appear to be at a disadvantage
            bet *= 1.0 + self.risk_adjustment  # Note: risk_adjustment is negative here

        # Respect table limits
        bet = max(table.minimum_bet, min(table.maximum_bet, bet))

        # Round to appropriate chip denomination
        if bet < 25:
            return round(bet / 5) * 5  # nearest $5
        elif bet < 100:
            return round(bet / 25) * 25  # nearest $25
        else:
            return round(bet / 100) * 100  # nearest $100

    def update_bankroll(self, result: float, bet_amount: float):
        """
        Update bankroll and adaptation state after a hand result.

        Args:
            result: Net win/loss amount
            bet_amount: Amount bet on this hand
        """
        super().update_bankroll(result, bet_amount)

        # Update win rate
        self._update_win_rate(result > 0)


class RiskOfRuinCalculator:
    """
    Utility class for calculating risk of ruin statistics.
    """

    @staticmethod
    def calculate_risk_of_ruin(
        bankroll: float,
        bet_size: float,
        edge: float,
        std_dev: float = 1.15,
        target_profit: float = None,
    ) -> Dict:
        """
        Calculate the risk of ruin (probability of losing entire bankroll).

        Args:
            bankroll: Current bankroll
            bet_size: Bet size (fixed)
            edge: Player edge per hand (e.g., 0.01 for 1%)
            std_dev: Standard deviation of one hand (default 1.15 for blackjack)
            target_profit: Optional target profit (for risk of not reaching target)

        Returns:
            Dictionary with risk statistics
        """
        variance = std_dev**2

        # Gambler's Ruin formula: q^n where q = (1-edge)/(1+edge), n = bankroll/bet
        if edge <= 0:
            # With negative edge, ruin is certain in the long run
            risk_of_ruin = 1.0
        else:
            # Simplified risk of ruin formula
            q = (1 - edge) / (1 + edge)
            n = bankroll / bet_size
            risk_of_ruin = q**n if q < 1 else 1.0

            # Cap to reasonable values
            risk_of_ruin = min(1.0, max(0.0, risk_of_ruin))

        # Optional calculation for risk of not reaching target
        risk_of_not_reaching_target = None
        if target_profit is not None and edge > 0:
            m = target_profit / bet_size
            if q < 1:
                risk_of_not_reaching_target = (1 - q**n) / (1 - q**m)
            else:
                risk_of_not_reaching_target = 1.0

            # Cap to reasonable values
            risk_of_not_reaching_target = min(
                1.0, max(0.0, risk_of_not_reaching_target)
            )

        # Expected number of hands to ruin
        expected_hands_to_ruin = float("inf")  # default for positive edge
        if edge < 0:
            expected_hands_to_ruin = bankroll / (bet_size * abs(edge))

        return {
            "risk_of_ruin": risk_of_ruin,
            "risk_of_not_reaching_target": risk_of_not_reaching_target,
            "expected_hands_to_ruin": expected_hands_to_ruin,
            "edge_per_hand": edge,
            "bankroll_to_bet_ratio": bankroll / bet_size
            if bet_size > 0
            else float("inf"),
        }
