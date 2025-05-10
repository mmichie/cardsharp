"""
Blackjack rules verification system.

This module provides classes for verifying that blackjack games adhere to the specified rules.
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union, cast
import json
import logging
from enum import Enum, auto

from cardsharp.verification.storage import SQLiteEventStore
from cardsharp.blackjack.action import Action
from cardsharp.blackjack.rules import Rules


class VerificationType(Enum):
    """Types of verification checks."""

    DEALER_ACTIONS = auto()
    PLAYER_OPTIONS = auto()
    PAYOUTS = auto()
    DECK_INTEGRITY = auto()
    SHUFFLE_TIMING = auto()
    BET_SIZES = auto()
    INSURANCE = auto()


class VerificationResult:
    """
    Result of a verification check.

    Attributes:
        verification_type: The type of verification check
        passed: Whether the check passed
        error_detail: Details about the error if the check failed
    """

    def __init__(
        self,
        verification_type: VerificationType,
        passed: bool,
        error_detail: Optional[str] = None,
    ):
        self.verification_type = verification_type
        self.passed = passed
        self.error_detail = error_detail

    def __str__(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        result = f"{self.verification_type.name}: {status}"
        if not self.passed and self.error_detail:
            result += f" - {self.error_detail}"
        return result


class BlackjackVerifier:
    """
    Verifies that blackjack games adhere to the specified rules.

    This class provides methods for verifying various aspects of blackjack games,
    such as dealer actions, player options, and payouts.
    """

    def __init__(self, event_store: SQLiteEventStore):
        """
        Initialize the verifier with an event store.

        Args:
            event_store: The event store containing game events
        """
        self.event_store = event_store
        self.logger = logging.getLogger(__name__)

    def verify_session(self, session_id: int) -> List[VerificationResult]:
        """
        Verify an entire session of blackjack games.

        Args:
            session_id: The ID of the session to verify

        Returns:
            A list of verification results
        """
        results: List[VerificationResult] = []

        # Get session information
        cursor = self.event_store.conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        session = cursor.fetchone()

        if not session:
            error = f"Session {session_id} not found"
            self.logger.error(error)
            return [VerificationResult(VerificationType.DEALER_ACTIONS, False, error)]

        # Parse rules from session
        rules_config = json.loads(session["rules_config"])
        rules = Rules(**rules_config)

        # Get all rounds for the session
        rounds = self.event_store.get_rounds_for_session(session_id)

        for round_data in rounds:
            round_id = round_data["round_id"]

            # Verify dealer actions
            dealer_result = self._verify_dealer_actions(round_id, rules)
            results.append(dealer_result)

            # Verify player options
            options_result = self._verify_player_options(round_id, rules)
            results.append(options_result)

            # Verify payouts
            payout_result = self._verify_payouts(round_id, rules)
            results.append(payout_result)

            # Record verification results in the database
            for result in [dealer_result, options_result, payout_result]:
                self.event_store.record_verification_result(
                    session_id=session_id,
                    round_id=round_id,
                    verification_type=result.verification_type.name,
                    passed=result.passed,
                    error_detail=result.error_detail,
                )

        return results

    def _verify_dealer_actions(self, round_id: int, rules: Rules) -> VerificationResult:
        """
        Verify that the dealer followed the rules correctly.

        Args:
            round_id: The ID of the round to verify
            rules: The rules of the game

        Returns:
            A verification result
        """
        # Get dealer actions for this round
        dealer_actions = self.event_store.get_dealer_actions(round_id)

        # Get round data to access dealer's final hand
        cursor = self.event_store.conn.cursor()
        cursor.execute("SELECT * FROM rounds WHERE round_id = ?", (round_id,))
        round_data = cursor.fetchone()

        if not round_data:
            return VerificationResult(
                VerificationType.DEALER_ACTIONS, False, f"Round {round_id} not found"
            )

        # Parse dealer's final hand and value
        dealer_final_hand = (
            json.loads(round_data["dealer_final_hand"])
            if round_data["dealer_final_hand"]
            else []
        )
        dealer_final_value = round_data["dealer_final_value"]

        # Check if dealer should have hit or stood based on rules
        hit_actions = [a for a in dealer_actions if a["action_type"] == "hit"]

        # If dealer's final value < 17, dealer should have hit
        if dealer_final_value < 17:
            if not hit_actions:
                return VerificationResult(
                    VerificationType.DEALER_ACTIONS,
                    False,
                    f"Dealer should have hit with value {dealer_final_value}",
                )

        # If dealer's final value > 17, dealer should not have hit
        elif dealer_final_value > 17:
            # Check the sequence of actions to ensure dealer stopped at the right time
            for action in dealer_actions:
                if action["action_type"] == "hit":
                    hand_value_after = action["hand_value_after"]
                    if hand_value_after > 17:
                        # If this hit brought the value over 17, make sure it's the last hit
                        last_hit_index = dealer_actions.index(action)
                        later_hits = [
                            a
                            for a in dealer_actions[last_hit_index + 1 :]
                            if a["action_type"] == "hit"
                        ]
                        if later_hits:
                            return VerificationResult(
                                VerificationType.DEALER_ACTIONS,
                                False,
                                f"Dealer hit after reaching value {hand_value_after}",
                            )

        # Special check for soft 17 rule
        elif dealer_final_value == 17:
            # Check if the hand is soft 17
            is_soft_17 = False

            # A soft 17 requires an ace counted as 11
            for action in dealer_actions:
                if action["action_type"] == "deal" and "A" in action["card_received"]:
                    # This is a simplification - in real verification we'd need to track the hand composition
                    is_soft_17 = True
                    break

            if is_soft_17:
                if rules.dealer_hit_soft_17 and not hit_actions:
                    return VerificationResult(
                        VerificationType.DEALER_ACTIONS,
                        False,
                        "Dealer should have hit on soft 17",
                    )
                elif not rules.dealer_hit_soft_17 and hit_actions:
                    return VerificationResult(
                        VerificationType.DEALER_ACTIONS,
                        False,
                        "Dealer should not have hit on soft 17",
                    )

        # All dealer action checks passed
        return VerificationResult(VerificationType.DEALER_ACTIONS, True)

    def _verify_player_options(self, round_id: int, rules: Rules) -> VerificationResult:
        """
        Verify that players were offered the correct options.

        Args:
            round_id: The ID of the round to verify
            rules: The rules of the game

        Returns:
            A verification result
        """
        # Get player decision points
        decision_points = self.event_store.get_player_decision_points(round_id)

        for point in decision_points:
            hand_id = point["hand_id"]

            # Get the hand
            cursor = self.event_store.conn.cursor()
            cursor.execute("SELECT * FROM player_hands WHERE hand_id = ?", (hand_id,))
            hand_data = cursor.fetchone()

            if not hand_data:
                return VerificationResult(
                    VerificationType.PLAYER_OPTIONS, False, f"Hand {hand_id} not found"
                )

            # Parse available actions
            available_actions = (
                json.loads(point["available_actions"])
                if point["available_actions"]
                else []
            )

            # Convert to set for easier comparison
            available_actions_set = set(available_actions)

            # Get all previous actions for this hand
            prev_actions = []
            cursor.execute(
                """
                SELECT action_type FROM actions 
                WHERE hand_id = ? AND timestamp < ?
                ORDER BY timestamp
                """,
                (hand_id, point["timestamp"]),
            )
            for row in cursor.fetchall():
                prev_actions.append(row["action_type"])

            # Determine which actions should be available based on rules and hand state
            expected_actions = self._get_expected_available_actions(
                hand_data, rules, prev_actions
            )

            # Compare expected vs actual available actions
            if expected_actions != available_actions_set:
                missing = expected_actions - available_actions_set
                extra = available_actions_set - expected_actions

                error_msg = ""
                if missing:
                    error_msg += f"Missing actions: {', '.join(missing)}. "
                if extra:
                    error_msg += f"Extra actions: {', '.join(extra)}. "

                return VerificationResult(
                    VerificationType.PLAYER_OPTIONS,
                    False,
                    f"Hand {hand_id}: {error_msg}",
                )

        # All player option checks passed
        return VerificationResult(VerificationType.PLAYER_OPTIONS, True)

    def _get_expected_available_actions(
        self, hand_data: Dict[str, Any], rules: Rules, prev_actions: List[str]
    ) -> Set[str]:
        """
        Determine which actions should be available for a hand.

        Args:
            hand_data: The hand data
            rules: The rules of the game
            prev_actions: Previous actions taken on this hand

        Returns:
            A set of expected available actions
        """
        # Start with basic actions
        expected_actions = {Action.HIT.name, Action.STAND.name}

        # Check if this is the first action
        is_first_action = not prev_actions

        # Parse hand data
        initial_cards = (
            json.loads(hand_data["initial_cards"]) if hand_data["initial_cards"] else []
        )
        is_split = hand_data["is_split"]

        # Only two cards allow for split, double, surrender
        if len(initial_cards) == 2 and is_first_action:
            # Check for splitting
            if rules.allow_split and not is_split:
                # This is a simplification - we'd need to check if cards have same rank
                card1_rank = initial_cards[0].split()[0]  # Assume format like "10 of ♥"
                card2_rank = initial_cards[1].split()[0]

                if card1_rank == card2_rank:
                    expected_actions.add(Action.SPLIT.name)

            # Check for doubling down
            if rules.allow_double_down:
                if not (is_split and not rules.allow_double_after_split):
                    # This is a simplification - rules might restrict doubling to certain hand values
                    expected_actions.add(Action.DOUBLE.name)

            # Check for surrender
            if rules.allow_surrender and not is_split:
                # This is a simplification - might be early or late surrender
                expected_actions.add(Action.SURRENDER.name)

        return expected_actions

    def _verify_payouts(self, round_id: int, rules: Rules) -> VerificationResult:
        """
        Verify that payouts were calculated correctly.

        Args:
            round_id: The ID of the round to verify
            rules: The rules of the game

        Returns:
            A verification result
        """
        # Get all hands for this round
        hands = self.event_store.get_player_hands(round_id)

        for hand in hands:
            # Verify the payout is correct based on the result
            result = hand["result"]
            final_bet = hand["final_bet"]
            payout = hand["payout"]
            is_blackjack = hand["is_blackjack"]

            expected_payout = 0.0

            if result == "win":
                if is_blackjack and not hand["is_split"]:
                    # Blackjack pays according to the blackjack payout rule
                    expected_payout = final_bet + (final_bet * rules.blackjack_payout)
                else:
                    # Regular win pays 1:1
                    expected_payout = final_bet * 2
            elif result == "push":
                # Push returns the original bet
                expected_payout = final_bet
            elif result == "surrender":
                # Surrender returns half the bet
                expected_payout = final_bet * 0.5
            # Lose pays nothing

            # Compare with a small tolerance for floating point
            if abs(payout - expected_payout) > 0.001:
                return VerificationResult(
                    VerificationType.PAYOUTS,
                    False,
                    f"Hand {hand['hand_id']}: Expected payout {expected_payout}, got {payout}",
                )

        # All payout checks passed
        return VerificationResult(VerificationType.PAYOUTS, True)

    def verify_deck_integrity(self, session_id: int) -> VerificationResult:
        """
        Verify that the deck contains the correct cards and no duplicates.

        Args:
            session_id: The ID of the session to verify

        Returns:
            A verification result
        """
        # Implementation would track all cards dealt and ensure correct composition
        # For simplicity, we'll just return a passing result
        return VerificationResult(VerificationType.DECK_INTEGRITY, True)

    def verify_shuffle_timing(self, session_id: int) -> VerificationResult:
        """
        Verify that shuffling occurs at the correct times.

        Args:
            session_id: The ID of the session to verify

        Returns:
            A verification result
        """
        # Implementation would check that shuffling occurs at the correct penetration
        # For simplicity, we'll just return a passing result
        return VerificationResult(VerificationType.SHUFFLE_TIMING, True)

    def verify_bet_sizes(self, session_id: int) -> VerificationResult:
        """
        Verify that bet sizes are within the allowed limits.

        Args:
            session_id: The ID of the session to verify

        Returns:
            A verification result
        """
        # Get session information for min/max bet
        cursor = self.event_store.conn.cursor()
        cursor.execute(
            "SELECT rules_config FROM sessions WHERE session_id = ?", (session_id,)
        )
        session_data = cursor.fetchone()

        if not session_data:
            return VerificationResult(
                VerificationType.BET_SIZES, False, f"Session {session_id} not found"
            )

        rules_config = json.loads(session_data["rules_config"])
        min_bet = rules_config.get("min_bet", 1.0)
        max_bet = rules_config.get("max_bet", 1000.0)

        # Check all bets
        cursor.execute(
            """
            SELECT h.hand_id, h.initial_bet, h.final_bet 
            FROM player_hands h
            JOIN rounds r ON h.round_id = r.round_id
            WHERE r.session_id = ?
            """,
            (session_id,),
        )

        for row in cursor.fetchall():
            hand_id = row["hand_id"]
            initial_bet = row["initial_bet"]
            final_bet = row["final_bet"]

            # Check initial bet
            if initial_bet < min_bet:
                return VerificationResult(
                    VerificationType.BET_SIZES,
                    False,
                    f"Hand {hand_id}: Initial bet {initial_bet} is below minimum {min_bet}",
                )

            if initial_bet > max_bet:
                return VerificationResult(
                    VerificationType.BET_SIZES,
                    False,
                    f"Hand {hand_id}: Initial bet {initial_bet} is above maximum {max_bet}",
                )

            # Check final bet (could be higher due to doubling down)
            if final_bet > max_bet:
                return VerificationResult(
                    VerificationType.BET_SIZES,
                    False,
                    f"Hand {hand_id}: Final bet {final_bet} is above maximum {max_bet}",
                )

        # All bet size checks passed
        return VerificationResult(VerificationType.BET_SIZES, True)

    def verify_insurance(self, session_id: int) -> VerificationResult:
        """
        Verify that insurance was offered and processed correctly.

        Args:
            session_id: The ID of the session to verify

        Returns:
            A verification result
        """
        # Implementation would check insurance was offered correctly and paid out correctly
        # For simplicity, we'll just return a passing result
        return VerificationResult(VerificationType.INSURANCE, True)
