"""
Realistic player behavior modeling for blackjack simulations.

This module provides implementations of player strategies that exhibit realistic
behavior such as skill level variation, decision fatigue, and psychological factors.
"""

import random
import time
import math
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.strategy import Strategy, BasicStrategy


class SkillLevel(Enum):
    """Player skill levels for realistic behavior modeling."""

    NOVICE = auto()  # Makes many mistakes (40-60% deviation)
    BEGINNER = auto()  # Makes frequent mistakes (25-40% deviation)
    INTERMEDIATE = auto()  # Makes occasional mistakes (10-25% deviation)
    ADVANCED = auto()  # Makes rare mistakes (5-10% deviation)
    EXPERT = auto()  # Makes very rare mistakes (1-5% deviation)
    PERFECT = auto()  # Makes no mistakes (0% deviation)


class PsychologicalProfile:
    """
    Psychological profile for a player.

    This class represents various psychological factors that affect a player's
    decision making, such as risk aversion, tilt, and fatigue.

    Attributes:
        risk_aversion: How risk-averse the player is (0.0 to 1.0)
        tilt_factor: How easily the player is affected by losses (0.0 to 1.0)
        fatigue_rate: How quickly the player becomes fatigued (0.0 to 1.0)
    """

    def __init__(
        self,
        risk_aversion: float = 0.5,
        tilt_factor: float = 0.2,
        fatigue_rate: float = 0.01,
    ):
        """
        Initialize a psychological profile.

        Args:
            risk_aversion: How risk-averse the player is (0.0 to 1.0)
            tilt_factor: How easily the player is affected by losses (0.0 to 1.0)
            fatigue_rate: How quickly the player becomes fatigued (0.0 to 1.0)
        """
        self.risk_aversion = max(0.0, min(1.0, risk_aversion))
        self.tilt_factor = max(0.0, min(1.0, tilt_factor))
        self.fatigue_rate = max(0.0, min(1.0, fatigue_rate))

        # Dynamic state
        self.current_tilt = 0.0
        self.current_fatigue = 0.0
        self.consecutive_losses = 0

    def update_tilt(self, result: str) -> None:
        """
        Update the tilt level based on a hand result.

        Args:
            result: The result of the hand ('win', 'lose', 'push', etc.)
        """
        if result == "lose":
            self.consecutive_losses += 1
            # Tilt increases with consecutive losses
            self.current_tilt = min(
                1.0,
                self.current_tilt + (self.tilt_factor * self.consecutive_losses / 5),
            )
        else:
            # Tilt decreases with wins or pushes
            self.consecutive_losses = 0
            self.current_tilt = max(0.0, self.current_tilt - (self.tilt_factor * 0.5))

    def update_fatigue(self, hands_played: int) -> None:
        """
        Update the fatigue level based on the number of hands played.

        Args:
            hands_played: The number of hands played so far
        """
        # Fatigue increases with each hand played
        self.current_fatigue = min(1.0, hands_played * self.fatigue_rate)

    def get_decision_quality(self) -> float:
        """
        Get the current decision quality factor.

        Returns:
            A factor between 0.0 and 1.0, where 1.0 is perfect decision quality
        """
        # Decision quality is reduced by tilt and fatigue
        return max(0.0, 1.0 - (self.current_tilt * 0.5) - (self.current_fatigue * 0.5))

    def reset(self) -> None:
        """Reset dynamic state."""
        self.current_tilt = 0.0
        self.current_fatigue = 0.0
        self.consecutive_losses = 0


class RealisticPlayerStrategy(Strategy):
    """
    A strategy that models realistic player behavior.

    This strategy wraps another strategy and introduces deviations based on
    the player's skill level and psychological profile.
    """

    def __init__(
        self,
        base_strategy: Strategy,
        skill_level: SkillLevel,
        psychological_profile: Optional[PsychologicalProfile] = None,
    ):
        """
        Initialize a realistic player strategy.

        Args:
            base_strategy: The base strategy to follow (e.g., BasicStrategy)
            skill_level: The player's skill level
            psychological_profile: The player's psychological profile
        """
        self.base_strategy = base_strategy
        self.skill_level = skill_level
        self.profile = psychological_profile or PsychologicalProfile()

        # State tracking
        self.hands_played = 0
        self.deviation_log: List[Dict[str, Any]] = []

        # Set deviation probability based on skill level
        self.base_deviation_prob = self._get_deviation_probability()

    def _get_deviation_probability(self) -> float:
        """
        Get the base deviation probability based on skill level.

        Returns:
            The base probability of deviating from optimal strategy
        """
        if self.skill_level == SkillLevel.NOVICE:
            return random.uniform(0.4, 0.6)  # 40-60% deviation
        elif self.skill_level == SkillLevel.BEGINNER:
            return random.uniform(0.25, 0.4)  # 25-40% deviation
        elif self.skill_level == SkillLevel.INTERMEDIATE:
            return random.uniform(0.1, 0.25)  # 10-25% deviation
        elif self.skill_level == SkillLevel.ADVANCED:
            return random.uniform(0.05, 0.1)  # 5-10% deviation
        elif self.skill_level == SkillLevel.EXPERT:
            return random.uniform(0.01, 0.05)  # 1-5% deviation
        else:  # PERFECT
            return 0.0  # No deviation

    def _get_current_deviation_probability(self) -> float:
        """
        Get the current deviation probability, accounting for psychological factors.

        Returns:
            The current probability of deviating from optimal strategy
        """
        decision_quality = self.profile.get_decision_quality()

        # Deviation probability increases as decision quality decreases
        return self.base_deviation_prob + (1.0 - decision_quality) * 0.3

    def _choose_deviation_action(
        self, optimal_action: Action, available_actions: List[Action]
    ) -> Action:
        """
        Choose a suboptimal action to deviate to.

        Args:
            optimal_action: The optimal action according to the base strategy
            available_actions: The list of available actions

        Returns:
            A suboptimal action to take
        """
        # Remove the optimal action from available actions
        deviation_actions = [a for a in available_actions if a != optimal_action]

        if not deviation_actions:
            # If no other actions are available, stick with the optimal action
            return optimal_action

        # Choose a deviation action based on psychological profile

        # More conservative actions (STAND, SURRENDER) are preferred when risk-averse
        if self.profile.risk_aversion > 0.7:
            # Prefer STAND over other actions
            if Action.STAND in deviation_actions:
                return Action.STAND
            # Prefer SURRENDER if available
            elif Action.SURRENDER in deviation_actions:
                return Action.SURRENDER

        # More aggressive actions (HIT, DOUBLE, SPLIT) are preferred when on tilt
        elif self.profile.current_tilt > 0.7:
            # Prefer DOUBLE over other actions
            if Action.DOUBLE in deviation_actions:
                return Action.DOUBLE
            # Prefer SPLIT if available
            elif Action.SPLIT in deviation_actions:
                return Action.SPLIT
            # Prefer HIT if available
            elif Action.HIT in deviation_actions:
                return Action.HIT

        # Otherwise, choose randomly
        return random.choice(deviation_actions)

    def decide_action(self, player, dealer_up_card, game=None) -> Action:
        """
        Decide which action to take with realistic behavior.

        Args:
            player: The player making the decision
            dealer_up_card: The dealer's up card
            game: The game instance

        Returns:
            The action to take
        """
        # Update hands played and fatigue
        self.hands_played += 1
        self.profile.update_fatigue(self.hands_played)

        # Get the optimal action from the base strategy
        optimal_action = self.base_strategy.decide_action(player, dealer_up_card, game)

        # Get valid actions
        valid_actions = player.valid_actions

        # Determine if we should deviate from optimal strategy
        deviation_prob = self._get_current_deviation_probability()
        should_deviate = random.random() < deviation_prob

        # If we should deviate and have alternative actions, choose a different action
        if should_deviate and len(valid_actions) > 1:
            action = self._choose_deviation_action(optimal_action, valid_actions)

            # Log the deviation
            self.deviation_log.append(
                {
                    "hand_index": player.current_hand_index,
                    "hand_value": player.current_hand.value(),
                    "is_soft": player.current_hand.is_soft,
                    "dealer_up_card": str(dealer_up_card),
                    "optimal_action": optimal_action.name,
                    "actual_action": action.name,
                    "deviation_prob": deviation_prob,
                    "tilt": self.profile.current_tilt,
                    "fatigue": self.profile.current_fatigue,
                }
            )

            return action

        # Otherwise, follow optimal strategy
        return optimal_action

    def decide_insurance(self, player) -> bool:
        """
        Decide whether to buy insurance with realistic behavior.

        Args:
            player: The player making the decision

        Returns:
            True if the player wants to buy insurance, False otherwise
        """
        # Get the optimal decision from the base strategy
        optimal_decision = self.base_strategy.decide_insurance(player)

        # Determine if we should deviate from optimal strategy
        deviation_prob = self._get_current_deviation_probability()
        should_deviate = random.random() < deviation_prob

        if should_deviate:
            # Deviate from optimal decision
            decision = not optimal_decision

            # Log the deviation
            self.deviation_log.append(
                {
                    "type": "insurance",
                    "optimal_decision": optimal_decision,
                    "actual_decision": decision,
                    "deviation_prob": deviation_prob,
                    "tilt": self.profile.current_tilt,
                    "fatigue": self.profile.current_fatigue,
                }
            )

            return decision

        # Otherwise, follow optimal strategy
        return optimal_decision

    def update_result(self, result: str) -> None:
        """
        Update the psychological profile based on a hand result.

        Args:
            result: The result of the hand ('win', 'lose', 'push', etc.)
        """
        self.profile.update_tilt(result)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the strategy's behavior.

        Returns:
            A dictionary with strategy statistics
        """
        total_decisions = self.hands_played
        total_deviations = len(self.deviation_log)

        deviation_rate = 0.0
        if total_decisions > 0:
            deviation_rate = total_deviations / total_decisions

        return {
            "skill_level": self.skill_level.name,
            "hands_played": self.hands_played,
            "total_deviations": total_deviations,
            "deviation_rate": deviation_rate,
            "current_tilt": self.profile.current_tilt,
            "current_fatigue": self.profile.current_fatigue,
            "risk_aversion": self.profile.risk_aversion,
            "tilt_factor": self.profile.tilt_factor,
            "fatigue_rate": self.profile.fatigue_rate,
        }

    def reset(self) -> None:
        """Reset the strategy's state."""
        self.hands_played = 0
        self.deviation_log = []
        self.profile.reset()


class SkillLevelBasicStrategy(RealisticPlayerStrategy):
    """
    A realistic implementation of basic strategy with skill level variations.

    This class provides a convenient way to create a realistic player strategy
    that follows basic strategy with deviations based on skill level.
    """

    def __init__(
        self,
        skill_level: SkillLevel = SkillLevel.INTERMEDIATE,
        psychological_profile: Optional[PsychologicalProfile] = None,
    ):
        """
        Initialize a skill-level basic strategy.

        Args:
            skill_level: The player's skill level
            psychological_profile: The player's psychological profile
        """
        base_strategy = BasicStrategy()
        super().__init__(base_strategy, skill_level, psychological_profile)


class PersonalityType(Enum):
    """Personality types for players with different risk profiles."""

    CONSERVATIVE = auto()  # Avoids risk, prefers safer actions
    BALANCED = auto()  # Follows optimal strategy closely
    AGGRESSIVE = auto()  # Takes more risks, prefers aggressive actions
    ERRATIC = auto()  # Highly variable, unpredictable behavior


def create_profile_from_personality(
    personality: PersonalityType,
) -> PsychologicalProfile:
    """
    Create a psychological profile based on a personality type.

    Args:
        personality: The personality type

    Returns:
        A psychological profile that matches the personality type
    """
    if personality == PersonalityType.CONSERVATIVE:
        return PsychologicalProfile(
            risk_aversion=random.uniform(0.7, 0.9),
            tilt_factor=random.uniform(0.1, 0.3),
            fatigue_rate=random.uniform(0.005, 0.015),
        )
    elif personality == PersonalityType.BALANCED:
        return PsychologicalProfile(
            risk_aversion=random.uniform(0.4, 0.6),
            tilt_factor=random.uniform(0.2, 0.4),
            fatigue_rate=random.uniform(0.01, 0.02),
        )
    elif personality == PersonalityType.AGGRESSIVE:
        return PsychologicalProfile(
            risk_aversion=random.uniform(0.1, 0.3),
            tilt_factor=random.uniform(0.5, 0.7),
            fatigue_rate=random.uniform(0.01, 0.03),
        )
    else:  # ERRATIC
        return PsychologicalProfile(
            risk_aversion=random.uniform(0.2, 0.8),
            tilt_factor=random.uniform(0.4, 0.9),
            fatigue_rate=random.uniform(0.01, 0.04),
        )


def create_realistic_player_strategy(
    base_strategy: Optional[Strategy] = None,
    skill_level: Optional[SkillLevel] = None,
    personality: Optional[PersonalityType] = None,
) -> Strategy:
    """
    Create a realistic player strategy with the given parameters.

    Args:
        base_strategy: The base strategy to use (defaults to BasicStrategy)
        skill_level: The player's skill level (defaults to random)
        personality: The player's personality type (defaults to random)

    Returns:
        A realistic player strategy
    """
    # Default to basic strategy
    if base_strategy is None:
        base_strategy = BasicStrategy()

    # Default to random skill level
    if skill_level is None:
        skill_level = random.choice(list(SkillLevel))

    # Default to random personality
    if personality is None:
        personality = random.choice(list(PersonalityType))

    # Create a profile based on personality
    profile = create_profile_from_personality(personality)

    # Create and return the strategy
    return RealisticPlayerStrategy(base_strategy, skill_level, profile)
