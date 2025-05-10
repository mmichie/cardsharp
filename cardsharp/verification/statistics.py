"""
Statistical validation system for blackjack simulations.

This module provides tools for validating the statistical properties of blackjack simulations,
including expected value calculations, variance, and confidence intervals.
"""

import math
import json
import numpy as np
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
import scipy.stats as stats

from cardsharp.verification.storage import SQLiteEventStore


class AnalysisType(Enum):
    """Types of statistical analysis."""

    EXPECTED_VALUE = auto()
    WIN_RATE = auto()
    HAND_DISTRIBUTION = auto()
    BLACKJACK_FREQUENCY = auto()
    VARIANCE = auto()
    RISK_OF_RUIN = auto()
    BETTING_CORRELATION = auto()


@dataclass
class ConfidenceInterval:
    """
    Represents a confidence interval with lower and upper bounds.

    Attributes:
        lower: The lower bound of the confidence interval
        upper: The upper bound of the confidence interval
        confidence: The confidence level (e.g., 0.95 for 95% confidence)
    """

    lower: float
    upper: float
    confidence: float

    def contains(self, value: float) -> bool:
        """Check if the interval contains a value."""
        return self.lower <= value <= self.upper

    def to_dict(self) -> Dict[str, float]:
        """Convert to a dictionary."""
        return {"lower": self.lower, "upper": self.upper, "confidence": self.confidence}


class StatisticalValidator:
    """
    Validates the statistical properties of blackjack simulations.

    This class provides methods for calculating expected values, win rates,
    and other statistical properties of blackjack games, and comparing them
    to theoretical values.
    """

    def __init__(self, event_store: SQLiteEventStore):
        """
        Initialize the validator with an event store.

        Args:
            event_store: The event store containing game events
        """
        self.event_store = event_store

    def calculate_expected_value(self, session_id: int) -> Dict[str, Any]:
        """
        Calculate the expected value per hand for a session.

        The expected value is the average amount won or lost per hand,
        expressed as a percentage of the initial bet.

        Args:
            session_id: The ID of the session to analyze

        Returns:
            A dictionary with the expected value and confidence interval
        """
        # Get all player hands for the session
        cursor = self.event_store.conn.cursor()
        cursor.execute(
            """
            SELECT h.initial_bet, h.payout, h.result
            FROM player_hands h
            JOIN rounds r ON h.round_id = r.round_id
            WHERE r.session_id = ?
            """,
            (session_id,),
        )

        hands = cursor.fetchall()

        if not hands:
            return {
                "expected_value": 0.0,
                "confidence_interval": ConfidenceInterval(0.0, 0.0, 0.95).to_dict(),
                "sample_size": 0,
                "theoretical_value": -0.005,  # Approximate EV for basic strategy
                "deviation": 0.0,
            }

        # Calculate net profit for each hand
        ev_values = []
        for hand in hands:
            initial_bet = hand["initial_bet"]
            payout = hand["payout"]
            net_profit = payout - initial_bet

            # Express as percentage of initial bet
            ev_percentage = net_profit / initial_bet
            ev_values.append(ev_percentage)

        # Calculate expected value
        ev = sum(ev_values) / len(ev_values)

        # Calculate confidence interval
        ci = self._calculate_confidence_interval(ev_values)

        # Theoretical expected value for basic strategy is around -0.5%
        theoretical_ev = -0.005

        # Calculate deviation from theoretical value
        deviation = ev - theoretical_ev

        return {
            "expected_value": ev,
            "confidence_interval": ci.to_dict(),
            "sample_size": len(hands),
            "theoretical_value": theoretical_ev,
            "deviation": deviation,
        }

    def calculate_win_rate(self, session_id: int) -> Dict[str, Any]:
        """
        Calculate the win rate for a session.

        The win rate is the percentage of hands that result in a win.

        Args:
            session_id: The ID of the session to analyze

        Returns:
            A dictionary with the win rate and confidence interval
        """
        # Get all player hands for the session
        cursor = self.event_store.conn.cursor()
        cursor.execute(
            """
            SELECT h.result
            FROM player_hands h
            JOIN rounds r ON h.round_id = r.round_id
            WHERE r.session_id = ?
            """,
            (session_id,),
        )

        hands = cursor.fetchall()

        if not hands:
            return {
                "win_rate": 0.0,
                "push_rate": 0.0,
                "loss_rate": 0.0,
                "confidence_interval": ConfidenceInterval(0.0, 0.0, 0.95).to_dict(),
                "sample_size": 0,
                "theoretical_win_rate": 0.42,  # Approximate win rate for basic strategy
                "deviation": 0.0,
            }

        # Count wins, pushes, and losses
        wins = 0
        pushes = 0
        losses = 0

        for hand in hands:
            result = hand["result"]
            if result == "win" or result == "blackjack":
                wins += 1
            elif result == "push":
                pushes += 1
            else:  # 'lose' or 'surrender'
                losses += 1

        # Calculate rates
        total_hands = len(hands)
        win_rate = wins / total_hands
        push_rate = pushes / total_hands
        loss_rate = losses / total_hands

        # Calculate confidence interval for win rate
        binary_outcomes = [
            1 if hand["result"] in ("win", "blackjack") else 0 for hand in hands
        ]
        ci = self._calculate_confidence_interval(binary_outcomes)

        # Theoretical win rate for basic strategy is around 42%
        theoretical_win_rate = 0.42

        # Calculate deviation from theoretical win rate
        deviation = win_rate - theoretical_win_rate

        return {
            "win_rate": win_rate,
            "push_rate": push_rate,
            "loss_rate": loss_rate,
            "confidence_interval": ci.to_dict(),
            "sample_size": total_hands,
            "theoretical_win_rate": theoretical_win_rate,
            "deviation": deviation,
        }

    def calculate_hand_distribution(self, session_id: int) -> Dict[str, Any]:
        """
        Calculate the distribution of final hand values.

        Args:
            session_id: The ID of the session to analyze

        Returns:
            A dictionary with the distribution of hand values
        """
        # Get all player hands for the session
        cursor = self.event_store.conn.cursor()
        cursor.execute(
            """
            SELECT h.final_value, h.is_busted
            FROM player_hands h
            JOIN rounds r ON h.round_id = r.round_id
            WHERE r.session_id = ?
            """,
            (session_id,),
        )

        hands = cursor.fetchall()

        if not hands:
            return {
                "distribution": {},
                "sample_size": 0,
                "average_value": 0.0,
                "bust_rate": 0.0,
            }

        # Count occurrences of each hand value
        value_counts = {}
        bust_count = 0
        total_value = 0

        for hand in hands:
            value = hand["final_value"]
            is_busted = hand["is_busted"]

            if is_busted:
                bust_count += 1
                # Special case for busted hands
                value_key = "bust"
            else:
                value_key = str(value)
                total_value += value

            if value_key in value_counts:
                value_counts[value_key] += 1
            else:
                value_counts[value_key] = 1

        # Calculate distribution as percentages
        total_hands = len(hands)
        distribution = {
            value: count / total_hands for value, count in value_counts.items()
        }

        # Calculate average non-busted hand value
        non_busted_count = total_hands - bust_count
        average_value = total_value / non_busted_count if non_busted_count > 0 else 0

        # Calculate bust rate
        bust_rate = bust_count / total_hands

        return {
            "distribution": distribution,
            "sample_size": total_hands,
            "average_value": average_value,
            "bust_rate": bust_rate,
        }

    def calculate_blackjack_frequency(self, session_id: int) -> Dict[str, Any]:
        """
        Calculate the frequency of blackjacks.

        Args:
            session_id: The ID of the session to analyze

        Returns:
            A dictionary with the blackjack frequency and confidence interval
        """
        # Get all player hands for the session
        cursor = self.event_store.conn.cursor()
        cursor.execute(
            """
            SELECT h.is_blackjack
            FROM player_hands h
            JOIN rounds r ON h.round_id = r.round_id
            WHERE r.session_id = ?
            """,
            (session_id,),
        )

        hands = cursor.fetchall()

        if not hands:
            return {
                "blackjack_frequency": 0.0,
                "confidence_interval": ConfidenceInterval(0.0, 0.0, 0.95).to_dict(),
                "sample_size": 0,
                "theoretical_frequency": 0.048,  # 4.8% is the theoretical blackjack frequency
                "deviation": 0.0,
            }

        # Count blackjacks
        blackjack_count = sum(hand["is_blackjack"] for hand in hands)

        # Calculate frequency
        total_hands = len(hands)
        blackjack_frequency = blackjack_count / total_hands

        # Calculate confidence interval
        binary_outcomes = [1 if hand["is_blackjack"] else 0 for hand in hands]
        ci = self._calculate_confidence_interval(binary_outcomes)

        # Theoretical blackjack frequency is 4.8%
        theoretical_frequency = 0.048

        # Calculate deviation from theoretical frequency
        deviation = blackjack_frequency - theoretical_frequency

        return {
            "blackjack_frequency": blackjack_frequency,
            "confidence_interval": ci.to_dict(),
            "sample_size": total_hands,
            "theoretical_frequency": theoretical_frequency,
            "deviation": deviation,
        }

    def calculate_variance(self, session_id: int) -> Dict[str, Any]:
        """
        Calculate the variance and standard deviation of returns.

        Args:
            session_id: The ID of the session to analyze

        Returns:
            A dictionary with the variance and standard deviation
        """
        # Get all player hands for the session
        cursor = self.event_store.conn.cursor()
        cursor.execute(
            """
            SELECT h.initial_bet, h.payout
            FROM player_hands h
            JOIN rounds r ON h.round_id = r.round_id
            WHERE r.session_id = ?
            """,
            (session_id,),
        )

        hands = cursor.fetchall()

        if not hands:
            return {"variance": 0.0, "standard_deviation": 0.0, "sample_size": 0}

        # Calculate returns as percentage of initial bet
        returns = []
        for hand in hands:
            initial_bet = hand["initial_bet"]
            payout = hand["payout"]
            return_value = (payout - initial_bet) / initial_bet
            returns.append(return_value)

        # Calculate variance and standard deviation
        variance = np.var(returns)
        std_dev = np.std(returns)

        return {
            "variance": variance,
            "standard_deviation": std_dev,
            "sample_size": len(hands),
        }

    def calculate_risk_of_ruin(
        self, session_id: int, bankroll: float, ruin_threshold: float
    ) -> Dict[str, Any]:
        """
        Calculate the risk of ruin (probability of reaching a specified loss level).

        Args:
            session_id: The ID of the session to analyze
            bankroll: The initial bankroll
            ruin_threshold: The bankroll level considered 'ruin'

        Returns:
            A dictionary with the risk of ruin calculation
        """
        # Get variance calculation
        variance_result = self.calculate_variance(session_id)
        variance = variance_result["variance"]
        std_dev = variance_result["standard_deviation"]

        # Get expected value
        ev_result = self.calculate_expected_value(session_id)
        expected_value = ev_result["expected_value"]

        if variance == 0 or expected_value >= 0:
            # If variance is 0 or EV is positive, risk of ruin is effectively 0
            return {
                "risk_of_ruin": 0.0,
                "bankroll": bankroll,
                "ruin_threshold": ruin_threshold,
                "expected_value": expected_value,
                "standard_deviation": std_dev,
            }

        # Calculate risk of ruin based on bankroll, expected value, and variance
        # Using simplified formula for negative EV games
        risk_of_ruin = math.exp(
            -2 * abs(expected_value) * (bankroll - ruin_threshold) / variance
        )

        return {
            "risk_of_ruin": risk_of_ruin,
            "bankroll": bankroll,
            "ruin_threshold": ruin_threshold,
            "expected_value": expected_value,
            "standard_deviation": std_dev,
        }

    def _calculate_confidence_interval(
        self, values: List[float], confidence: float = 0.95
    ) -> ConfidenceInterval:
        """
        Calculate a confidence interval for a set of values.

        Args:
            values: The values to calculate the confidence interval for
            confidence: The confidence level (e.g., 0.95 for 95% confidence)

        Returns:
            A ConfidenceInterval object
        """
        mean = np.mean(values)
        std_err = stats.sem(values)

        # Calculate confidence interval
        margin = std_err * stats.t.ppf((1 + confidence) / 2, len(values) - 1)
        lower = mean - margin
        upper = mean + margin

        return ConfidenceInterval(lower, upper, confidence)

    def run_all_analyses(self, session_id: int) -> Dict[str, Any]:
        """
        Run all statistical analyses for a session.

        Args:
            session_id: The ID of the session to analyze

        Returns:
            A dictionary with all analysis results
        """
        # Run all analyses
        ev_result = self.calculate_expected_value(session_id)
        win_rate_result = self.calculate_win_rate(session_id)
        hand_dist_result = self.calculate_hand_distribution(session_id)
        blackjack_freq_result = self.calculate_blackjack_frequency(session_id)
        variance_result = self.calculate_variance(session_id)

        # Risk of ruin calculation with default parameters
        risk_result = self.calculate_risk_of_ruin(session_id, 1000.0, 0.0)

        # Combine results
        results = {
            "expected_value": ev_result,
            "win_rate": win_rate_result,
            "hand_distribution": hand_dist_result,
            "blackjack_frequency": blackjack_freq_result,
            "variance": variance_result,
            "risk_of_ruin": risk_result,
        }

        # Record results in the database
        self._record_analysis_results(session_id, results)

        return results

    def _record_analysis_results(
        self, session_id: int, results: Dict[str, Any]
    ) -> None:
        """
        Record analysis results in the database.

        Args:
            session_id: The ID of the session
            results: The analysis results
        """
        # Record each analysis type separately
        for analysis_type, result in results.items():
            # Determine whether the result matches theoretical expectations
            passed = True

            if analysis_type == "expected_value":
                # Check if theoretical value is within confidence interval
                ci = ConfidenceInterval(**result["confidence_interval"])
                passed = ci.contains(result["theoretical_value"])

            elif analysis_type == "win_rate":
                # Check if theoretical win rate is within confidence interval
                ci = ConfidenceInterval(**result["confidence_interval"])
                passed = ci.contains(result["theoretical_win_rate"])

            elif analysis_type == "blackjack_frequency":
                # Check if theoretical frequency is within confidence interval
                ci = ConfidenceInterval(**result["confidence_interval"])
                passed = ci.contains(result["theoretical_frequency"])

            # Record in database
            self.event_store.record_statistical_analysis(
                session_id=session_id,
                analysis_type=analysis_type,
                params={},  # No special parameters for these analyses
                result=result,
                confidence_interval=result.get("confidence_interval", {}),
                passed=passed,
            )
