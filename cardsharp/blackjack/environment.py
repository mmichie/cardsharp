"""
Casino environment integration for blackjack simulation.

This module connects the casino environment modeling with the blackjack game
simulation to create a full-fidelity integrated environment.
"""

import random
import time
from typing import Dict, List, Optional, Tuple, Callable, Any

from cardsharp.blackjack.casino import CasinoEnvironment, TableConditions, DealerProfile
from cardsharp.blackjack.bankroll import BasicBankrollManager, KellyBankrollManager
from cardsharp.blackjack.execution_variance import ExecutionVarianceWrapper
from cardsharp.blackjack.strategy import Strategy
from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.realistic_strategy import RealisticPlayerStrategy, SkillLevel
from cardsharp.blackjack.state import GameState
from cardsharp.verification.events import EventEmitter, EventRecorder
from cardsharp.verification.storage import SQLiteEventStore
from cardsharp.verification.verifier import BlackjackVerifier


class EnvironmentIntegrator:
    """
    Integrates casino environment factors with blackjack simulation.
    """

    def __init__(
        self,
        casino_env: CasinoEnvironment,
        table_id: str,
        event_store: Optional[SQLiteEventStore] = None,
        session_id: Optional[str] = None,
    ):
        """
        Initialize environment integrator.

        Args:
            casino_env: Casino environment instance
            table_id: ID of the table to play at
            event_store: Optional SQLiteEventStore for recording events
            session_id: Optional session ID for event recording
        """
        self.casino_env = casino_env
        self.table_id = table_id
        self.table = casino_env.get_table_conditions(table_id)
        self.dealer_profile = casino_env.get_dealer(table_id)

        # Set up event recording if provided
        self.event_store = event_store
        self.session_id = session_id or f"session_{int(time.time())}"
        self.event_recorder = None
        if event_store:
            self.event_recorder = EventRecorder()
            # We'll need to use the event_store directly when recording events

        # Game instance will be created when needed
        self.game = None
        self.player_actor = None
        self.current_round_id = None
        self.hands_played = 0
        self.hands_per_hour = 0
        self.simulation_start_time = time.time()

        # Environment factors
        self.fatigue = 0.0
        self.time_pressure = 0.0
        self.distraction_level = 0.0
        self.last_shuffle_time = self.simulation_start_time

        # Performance metrics
        self.correct_decisions = 0
        self.total_decisions = 0
        self.dealer_errors = 0
        self.shuffle_quality_samples = []

    def create_game(self, rules=None, decks=None):
        """
        Create or refresh a blackjack game instance with current casino parameters.

        Args:
            rules: Optional rules override
            decks: Optional deck count override

        Returns:
            BlackjackGame instance
        """
        # Use table rules if not overridden
        if rules is None:
            rules = self.table.rules

        # Default to 6 decks if not specified
        if decks is None:
            decks = 6

        # Create a game instance
        self.game = BlackjackGame(rules=rules, num_decks=decks)

        # Set penetration based on dealer profile
        penetration = self.table.penetration
        self.game.set_penetration(penetration)

        # Add event emission if we have a recorder
        if self.event_recorder:
            self.game.state.attach_event_emitter(
                EventEmitter(recorder=self.event_recorder)
            )

        return self.game

    def add_player(
        self,
        strategy: Strategy,
        bankroll_manager: BasicBankrollManager,
        skill_level: SkillLevel = None,
    ) -> Player:
        """
        Add a player to the game with environment-aware execution.

        Args:
            strategy: Base strategy for the player
            bankroll_manager: Bankroll management strategy
            skill_level: Optional skill level for realistic play

        Returns:
            Player instance for the player
        """
        if self.game is None:
            self.create_game()

        # Create a realistic player strategy if skill level is provided
        if skill_level is not None:
            strategy = RealisticPlayerStrategy(
                base_strategy=strategy, skill_level=skill_level
            )

        # Apply execution variance based on environment
        play_quality = self.casino_env.get_play_quality_modifier(self.table_id)
        strategy = ExecutionVarianceWrapper(
            strategy=strategy,
            error_rate=self._calculate_error_rate(),
            time_pressure=self.time_pressure,
            fatigue=self.fatigue,
            play_quality_modifier=play_quality,
        )

        # Create a minimal IO interface
        class DummyIOInterface:
            def output(self, message):
                pass

            def get_player_action(self, player, valid_actions, time_limit=None):
                # Always return the first action from the strategy
                if player.strategy:
                    # Pass in a mock dealer_up_card and game
                    return player.strategy.decide_action(player, None, None)
                return valid_actions[0] if valid_actions else None

        io_interface = DummyIOInterface()

        # Create the player
        name = "Player"
        self.player_actor = Player(
            name=name, strategy=strategy, io_interface=io_interface
        )
        self.game.add_player(self.player_actor)

        # Store bankroll manager reference
        self.player_actor.bankroll_manager = bankroll_manager

        return self.player_actor

    def _calculate_error_rate(self) -> float:
        """
        Calculate current error rate based on environment factors.

        Returns:
            Float representing probability of error
        """
        # Base error rate
        base_rate = 0.01  # 1% chance of error in ideal conditions

        # Fatigue increases errors
        fatigue_factor = 1.0 + (self.fatigue * 5.0)

        # Time pressure increases errors
        time_factor = 1.0 + (self.time_pressure * 4.0)

        # Distractions increase errors
        distraction_factor = 1.0 + (self.distraction_level * 3.0)

        # Combined error rate
        error_rate = base_rate * fatigue_factor * time_factor * distraction_factor

        # Cap at reasonable values
        return min(0.5, error_rate)

    def _update_environmental_factors(self, elapsed_hours: float):
        """
        Update environmental factors based on elapsed time.

        Args:
            elapsed_hours: Hours elapsed in the current session
        """
        # Fatigue increases with time
        self.fatigue = min(1.0, elapsed_hours / 8.0)

        # Get table distractions
        self.distraction_level = self.table.get_distractions()

        # Time pressure depends on dealer speed and table conditions
        dealer_speed = self.dealer_profile.speed
        self.hands_per_hour = self.table.get_hands_per_hour(dealer_speed)
        self.time_pressure = max(0.0, min(1.0, (dealer_speed - 0.8) / 0.6))

        # Apply random fluctuations to make it more realistic
        self.fatigue *= random.uniform(0.9, 1.1)
        self.distraction_level *= random.uniform(0.8, 1.2)
        self.time_pressure *= random.uniform(0.9, 1.1)

    def _handle_dealer_errors(self) -> Tuple[bool, str]:
        """
        Check if dealer makes an error and apply it.

        Returns:
            Tuple of (error_made, error_type)
        """
        # Check if dealer makes an error
        error_made, error_type = self.dealer_profile.makes_error()

        if error_made:
            self.dealer_errors += 1

            # Record error event if we have a recorder and event store
            if self.event_recorder and self.event_store and self.current_round_id:
                # Create a GameEvent using EventType enum
                from cardsharp.verification.events import EventType, GameEvent

                event = GameEvent(
                    event_type=EventType.DEALER_ACTION,  # Using the proper event type from enum
                    game_id=self.session_id,
                    round_id=self.current_round_id,
                    data={
                        "error_type": error_type,
                        "dealer": self.dealer_profile.name,
                        "has_error": True,
                        "dealer_profile": self.dealer_profile.__dict__,
                    },
                )
                # Record the event in our recorder
                self.event_recorder.record_event(event)
                # Store it using the event store
                self.event_store.store_event(event)

            # TODO: Actually implement the error effects in the game
            # This would require modifying game state to simulate dealer errors

        return error_made, error_type

    def _evaluate_decision_quality(
        self, decision: str, optimal_decision: str, state
    ) -> bool:
        """
        Evaluate if player made the correct decision.

        Args:
            decision: Decision the player made
            optimal_decision: Optimal decision for the situation
            state: Current game state

        Returns:
            Boolean indicating if decision was correct
        """
        self.total_decisions += 1

        if decision == optimal_decision:
            self.correct_decisions += 1
            return True

        # Record error event if we have a recorder
        if self.event_recorder and self.current_round_id:
            from cardsharp.verification.events import EventType, GameEvent

            # Create a proper GameEvent
            event = GameEvent(
                event_type=EventType.PLAYER_ACTION,
                game_id=self.session_id,
                round_id=self.current_round_id,
                data={
                    "player_decision": decision,
                    "optimal_decision": optimal_decision,
                    "player_hand": str(state.current_player_hand),
                    "dealer_upcard": str(state.dealer_hand.cards[0]),
                    "is_error": True,
                    "player": self.player_actor.name
                    if self.player_actor
                    else "Unknown",
                    "fatigue": self.fatigue,
                    "distraction": self.distraction_level,
                    "time_pressure": self.time_pressure,
                },
            )

            # Record the event
            self.event_recorder.record_event(event)

            # Store it in the database if we have an event store
            if self.event_store and hasattr(self.event_store, "store_event"):
                self.event_store.store_event(event)

        return False

    def _simulate_hand_timing(self) -> float:
        """
        Simulate the time it takes to complete one hand.

        Returns:
            Float representing simulated seconds per hand
        """
        # Get base timing from dealer profile
        base_time = self.dealer_profile.get_hand_time()

        # Adjust for player decision time
        if self.player_actor:
            # More complex decisions take longer
            complexity_factor = 1.0
            if hasattr(self.player_actor.strategy, "get_complexity"):
                complexity_factor = getattr(
                    self.player_actor.strategy, "get_complexity"
                )()

            # Add decision time (typically 2-5 seconds per decision)
            decisions_per_hand = 1.5  # average decisions per hand
            decision_time = decisions_per_hand * (2 + (3 * complexity_factor))
            base_time += decision_time

        # Adjust for table conditions
        if self.table.is_crowded:
            base_time *= 1.2  # crowded tables are slower

        # Add small random variation
        time_factor = random.uniform(0.9, 1.1)

        return base_time * time_factor

    def _verify_game_state(self) -> Dict:
        """
        Verify the current game state for errors.

        Returns:
            Dictionary with verification results
        """
        if not self.game or not hasattr(self.game, "state"):
            return {"verified": False, "reason": "No game state available"}

        # Create a verifier if we have an event store
        if self.event_store:
            verifier = BlackjackVerifier(self.event_store)

            # Verify current round if available
            if self.current_round_id:
                try:
                    results = verifier.verify_round(self.current_round_id)

                    # Record verification result if it failed
                    if not results.get("verified", True) and self.event_store:
                        self.event_store.record_verification_result(
                            session_id=self.session_id,
                            round_id=self.current_round_id,
                            verification_type="game_state",
                            passed=False,
                            error_detail=results.get(
                                "reason", "Unknown verification error"
                            ),
                        )

                    return results
                except Exception as e:
                    error_message = f"Verification error: {str(e)}"

                    # Record the error if we have an event store
                    if self.event_store:
                        self.event_store.record_verification_result(
                            session_id=self.session_id,
                            round_id=self.current_round_id,
                            verification_type="game_state",
                            passed=False,
                            error_detail=error_message,
                        )

                    return {"verified": False, "reason": error_message}

        return {"verified": True, "reason": "No verification performed"}

    def simulate_session(
        self, hours: float = 4.0, max_hands: int = None, verify: bool = True
    ) -> Dict:
        """
        Simulate a playing session with realistic environment factors.

        Args:
            hours: Hours to simulate
            max_hands: Maximum hands to simulate
            verify: Whether to verify the game state

        Returns:
            Dictionary with session results
        """
        # Create a game if we don't have one
        if self.game is None:
            self.create_game()

        # Make sure we have a player
        if self.player_actor is None:
            raise ValueError("Must add a player before simulating a session")

        # Reset session stats
        self.hands_played = 0
        self.correct_decisions = 0
        self.total_decisions = 0
        self.dealer_errors = 0
        self.shuffle_quality_samples = []

        # Initialize session in event store if available
        if self.event_store:
            table_info = {
                "table_id": self.table_id,
                "min_bet": self.table.minimum_bet,
                "max_bet": self.table.maximum_bet,
                "rules": self.table.rules.to_dict(),
                "players": self.table.current_players,
                "dealer": self.dealer_profile.name,
            }
            self.event_store.record_session(self.session_id, table_info)

        # Time tracking
        start_time = time.time()
        simulated_time = 0.0  # in seconds
        target_session_time = hours * 3600  # convert to seconds

        # Play hands until time or max hands reached
        while simulated_time < target_session_time and (
            max_hands is None or self.hands_played < max_hands
        ):

            # Check if player should continue
            if hasattr(self.player_actor, "bankroll_manager"):
                if not self.player_actor.bankroll_manager.should_continue_session():
                    break

            # Update environment factors
            elapsed_hours = simulated_time / 3600.0
            self._update_environmental_factors(elapsed_hours)

            # Check for casino environment changes
            self.casino_env.advance_time(1 / 60)  # advance casino time by 1 minute
            self.table = self.casino_env.get_table_conditions(self.table_id)

            # Check if we need to shuffle based on penetration
            if self.game.should_shuffle():
                # Get shuffle quality
                shuffle_quality = self.dealer_profile.get_shuffle_effectiveness()
                self.shuffle_quality_samples.append(shuffle_quality)

                # Apply shuffle quality (1.0 = perfect shuffle, lower = less random)
                self.game.shuffle(quality=shuffle_quality)
                self.last_shuffle_time = time.time()

                # Record shuffle event if we have a recorder
                if self.event_recorder:
                    self.event_recorder.record_event(
                        event_type="shuffle",
                        details={
                            "quality": shuffle_quality,
                            "penetration": self.table.penetration,
                            "cards_dealt": self.game.cards_dealt_since_shuffle,
                        },
                    )

            # Create a round ID for this hand
            self.current_round_id = f"round_{self.session_id}_{self.hands_played}"

            # Record round start if we have a recorder
            if self.event_recorder:
                self.event_recorder.set_current_round(self.current_round_id)
                self.event_recorder.record_event(
                    event_type="round_start",
                    round_id=self.current_round_id,
                    details={
                        "hand_number": self.hands_played,
                        "elapsed_hours": elapsed_hours,
                        "fatigue": self.fatigue,
                        "distraction": self.distraction_level,
                        "time_pressure": self.time_pressure,
                    },
                )

            # Get betting decision from player
            if hasattr(self.player_actor, "bankroll_manager"):
                player_advantage = 0.0
                # Get advantage if strategy supports it
                if hasattr(self.player_actor.strategy, "get_advantage"):
                    player_advantage = self.player_actor.strategy.get_advantage(
                        self.game.state
                    )

                bet_amount = self.player_actor.bankroll_manager.calculate_bet(
                    table=self.table, advantage=player_advantage
                )

                # Record bet event if we have a recorder
                if self.event_recorder:
                    self.event_recorder.record_event(
                        event_type="bet",
                        round_id=self.current_round_id,
                        details={
                            "player": self.player_actor.name,
                            "amount": bet_amount,
                            "advantage": player_advantage,
                            "bankroll": self.player_actor.bankroll_manager.current_bankroll,
                        },
                    )
            else:
                bet_amount = self.table.minimum_bet

            # Play a hand
            self.game.place_bet(self.player_actor, bet_amount)
            hand_result = self.game.play_round()

            # Record hand outcome
            self.hands_played += 1

            # Check for dealer errors (after hand is played)
            self._handle_dealer_errors()

            # Update bankroll based on result
            if hasattr(self.player_actor, "bankroll_manager"):
                # Calculate net result for this player
                player_result = sum(
                    outcome[1]
                    for outcome in hand_result
                    if outcome[0] == self.player_actor
                )

                # Update bankroll
                self.player_actor.bankroll_manager.update_bankroll(
                    result=player_result, bet_amount=bet_amount
                )

                # Record result event if we have a recorder
                if self.event_recorder:
                    bankroll_stats = (
                        self.player_actor.bankroll_manager.get_session_stats()
                    )
                    self.event_recorder.record_event(
                        event_type="hand_result",
                        round_id=self.current_round_id,
                        details={
                            "player": self.player_actor.name,
                            "result": player_result,
                            "bet_amount": bet_amount,
                            "current_bankroll": self.player_actor.bankroll_manager.current_bankroll,
                            "hands_played": bankroll_stats["hands_played"],
                            "roi_percentage": bankroll_stats["roi_percentage"],
                        },
                    )

            # Simulate time passing based on hand timing
            hand_time = self._simulate_hand_timing()
            simulated_time += hand_time

            # Verify game state if requested and we have verification capability
            if verify and self.event_store:
                verification_results = self._verify_game_state()

                # If verification failed, record it
                if not verification_results.get("verified", True):
                    if self.event_recorder:
                        self.event_recorder.record_event(
                            event_type="verification_failure",
                            round_id=self.current_round_id,
                            details=verification_results,
                        )

            # Record round end if we have a recorder
            if self.event_recorder:
                self.event_recorder.record_event(
                    event_type="round_end",
                    round_id=self.current_round_id,
                    details={"result": hand_result, "elapsed_time": hand_time},
                )

        # Calculate session results
        actual_elapsed_time = time.time() - start_time

        # Get bankroll stats if available
        bankroll_stats = {}
        if hasattr(self.player_actor, "bankroll_manager"):
            bankroll_stats = self.player_actor.bankroll_manager.get_session_stats()

        # Calculate decision quality
        decision_accuracy = self.correct_decisions / max(1, self.total_decisions)

        # Calculate average shuffle quality
        avg_shuffle_quality = (
            sum(self.shuffle_quality_samples) / len(self.shuffle_quality_samples)
            if self.shuffle_quality_samples
            else 0.0
        )

        # Prepare session results
        session_results = {
            "session_id": self.session_id,
            "table_id": self.table_id,
            "hands_played": self.hands_played,
            "simulated_time_hours": simulated_time / 3600.0,
            "actual_time_seconds": actual_elapsed_time,
            "simulation_speed_factor": simulated_time / max(1, actual_elapsed_time),
            "hands_per_hour": self.hands_per_hour,
            "decision_accuracy": decision_accuracy,
            "dealer_errors": self.dealer_errors,
            "avg_shuffle_quality": avg_shuffle_quality,
            "environment_factors": {
                "fatigue": self.fatigue,
                "distraction_level": self.distraction_level,
                "time_pressure": self.time_pressure,
            },
            "bankroll_stats": bankroll_stats,
        }

        # Record session stats if we have a recorder
        if self.event_recorder:
            self.event_recorder.record_event(
                event_type="session_summary", details=session_results
            )

        return session_results
