"""
Comprehensive logging system for blackjack decision paths.
Tracks all decisions, rule evaluations, and game state changes.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import os
from ..common.card import Card
from .action import Action
from .hand import BlackjackHand


@dataclass
class DecisionContext:
    """Context for a single decision point."""

    timestamp: datetime
    player_name: str
    hand_index: int
    hand_cards: List[Card]
    hand_value: int
    is_soft: bool
    is_pair: bool
    is_split_hand: bool
    dealer_upcard: Card
    valid_actions: List[Action]
    chosen_action: Optional[Action] = None
    strategy_reason: Optional[str] = None
    rule_constraints: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "player": self.player_name,
            "hand_index": self.hand_index,
            "cards": [str(c) for c in self.hand_cards],
            "value": self.hand_value,
            "soft": self.is_soft,
            "pair": self.is_pair,
            "split_hand": self.is_split_hand,
            "dealer_up": str(self.dealer_upcard),
            "valid_actions": [a.value for a in self.valid_actions],
            "chosen": self.chosen_action.value if self.chosen_action else None,
            "reason": self.strategy_reason,
            "constraints": self.rule_constraints,
        }


class DecisionLogger:
    """Logs all decision-making processes in blackjack."""

    def __init__(self, log_level=logging.DEBUG):
        self.logger = logging.getLogger("blackjack.decisions")
        # Check environment variable to disable logging in simulation mode
        if os.environ.get("BLACKJACK_DISABLE_LOGGING", "").lower() in (
            "1",
            "true",
            "yes",
        ):
            self.logger.setLevel(logging.ERROR)
        else:
            self.logger.setLevel(log_level)

        # Add console handler if none exists
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.decision_history: List[DecisionContext] = []
        self.current_round_decisions: List[DecisionContext] = []

    def set_level(self, level):
        """Set the logging level."""
        self.logger.setLevel(level)

    def log_decision_point(self, context: DecisionContext):
        """Log a decision point with full context."""
        # Only store decisions if we're actually logging
        if self.logger.isEnabledFor(logging.DEBUG):
            self.current_round_decisions.append(context)
            self.logger.debug(
                f"Decision for {context.player_name} hand {context.hand_index}: "
                f"{[str(c) for c in context.hand_cards]} (value={context.hand_value}, "
                f"soft={context.is_soft}) vs dealer {context.dealer_upcard}"
            )
            self.logger.debug(
                f"Valid actions: {[a.value for a in context.valid_actions]}"
            )

        if context.chosen_action and self.logger.isEnabledFor(logging.INFO):
            self.logger.info(
                f"{context.player_name} chose {context.chosen_action.value} "
                f"(reason: {context.strategy_reason or 'unknown'})"
            )

    def log_rule_evaluation(self, rule_name: str, result: bool, reason: str = ""):
        """Log a rule evaluation."""
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"Rule '{rule_name}': {result} {reason}")

    def log_split_decision(
        self, player_name: str, hand: BlackjackHand, can_split: bool, reason: str
    ):
        """Log split possibility evaluation."""
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                f"Split evaluation for {player_name}: "
                f"{[str(c) for c in hand.cards]} - "
                f"Can split: {can_split} ({reason})"
            )

    def log_resplit_check(
        self, player_name: str, current_hands: int, max_hands: int, allowed: bool
    ):
        """Log resplit possibility check."""
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                f"Resplit check for {player_name}: "
                f"{current_hands} hands (max {max_hands}) - "
                f"Allowed: {allowed}"
            )

    def log_strategy_lookup(
        self, hand_type: str, dealer_card: str, action: str, fallback_used: bool = False
    ):
        """Log basic strategy table lookup."""
        if self.logger.isEnabledFor(logging.DEBUG):
            msg = f"Strategy lookup: {hand_type} vs {dealer_card} -> {action}"
            if fallback_used:
                msg += " (using fallback)"
            self.logger.debug(msg)

    def log_hand_transition(
        self,
        player_name: str,
        hand_index: int,
        from_state: str,
        to_state: str,
        reason: str,
    ):
        """Log hand state transitions."""
        if self.logger.isEnabledFor(logging.INFO):
            self.logger.info(
                f"{player_name} hand {hand_index}: {from_state} -> {to_state} "
                f"({reason})"
            )

    def log_round_start(self, round_num: int, players: List[str]):
        """Log the start of a new round."""
        if self.logger.isEnabledFor(logging.INFO):
            self.logger.info(
                f"=== Round {round_num} starting with players: {players} ==="
            )
        self.current_round_decisions = []

    def log_round_end(self, outcomes: Dict[str, Any]):
        """Log the end of a round with outcomes."""
        if self.logger.isEnabledFor(logging.INFO):
            self.logger.info(f"=== Round ended ===")
            for player, outcome in outcomes.items():
                self.logger.info(f"{player}: {outcome}")

        # Archive current round decisions
        self.decision_history.extend(self.current_round_decisions)
        self.current_round_decisions = []

    def get_decision_summary(self) -> Dict[str, Any]:
        """Get a summary of all decisions made."""
        summary: Dict[str, Any] = {
            "total_decisions": len(self.decision_history),
            "by_action": {},
            "by_player": {},
            "split_count": 0,
            "surrender_count": 0,
        }

        for decision in self.decision_history:
            # Count by action
            action = decision.chosen_action.value if decision.chosen_action else "none"
            summary["by_action"][action] = summary["by_action"].get(action, 0) + 1

            # Count by player
            player = decision.player_name
            summary["by_player"][player] = summary["by_player"].get(player, 0) + 1

            # Count special actions
            if decision.chosen_action == Action.SPLIT:
                summary["split_count"] += 1
            elif decision.chosen_action == Action.SURRENDER:
                summary["surrender_count"] += 1

        return summary

    def export_decisions(self, filepath: str):
        """Export decision history to a file."""
        import json

        data = {
            "decisions": [d.to_dict() for d in self.decision_history],
            "summary": self.get_decision_summary(),
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        self.logger.info(
            f"Exported {len(self.decision_history)} decisions to {filepath}"
        )


# Global logger instance
decision_logger = DecisionLogger()
