"""
Casino environment modeling for blackjack simulation.

This module provides classes and functions for modeling realistic casino
environments, including table occupancy, dealer performance, and casino-specific
rule variations and conditions.
"""

import random
import time
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Callable, Union

from cardsharp.blackjack.rules import Rules

# Custom weighted choice function
def weighted_choice(weights_dict):
    """
    Select a random item from weights_dict where the probability of each item
    is determined by its value relative to the sum of all values.

    Args:
        weights_dict: Dictionary mapping choices to their weights.

    Returns:
        Selected item from the dictionary keys.
    """
    choices = list(weights_dict.keys())
    weights = list(weights_dict.values())
    total = sum(weights)
    r = random.random() * total
    upto = 0

    for choice, weight in zip(choices, weights):
        upto += weight
        if upto >= r:
            return choice

    # Fallback in case of rounding errors
    return choices[-1]


@dataclass
class DealerProfile:
    """
    Models a dealer's performance characteristics.

    Attributes:
        name: Identifier for the dealer
        speed: Average hands per hour (normalized, 1.0 = standard speed)
        error_rate: Probability of making a mistake in game execution
        error_types: Dictionary of error types and their relative frequencies
        shuffle_quality: How well the dealer shuffles (1.0 = perfect)
        personality: Dictionary of personality traits affecting gameplay
    """

    name: str
    speed: float = 1.0  # normalized speed (1.0 = standard ~80 hands/hr for 1-on-1)
    error_rate: float = 0.005  # probability of making a mistake
    error_types: Dict[str, float] = None
    shuffle_quality: float = 0.95  # how random the shuffle is (1.0 = perfect)
    personality: Dict[str, float] = None

    def __post_init__(self):
        if self.error_types is None:
            self.error_types = {
                "card_exposure": 0.4,  # showing cards accidentally
                "miscount": 0.3,  # miscounting hand value
                "payout": 0.2,  # incorrect payout
                "procedure": 0.1,  # procedural error (hitting when should stand)
            }

        if self.personality is None:
            self.personality = {
                "friendliness": random.uniform(0.3, 1.0),
                "attentiveness": random.uniform(0.7, 1.0),
                "consistency": random.uniform(0.8, 1.0),
                "pace_variance": random.uniform(
                    0.05, 0.2
                ),  # how much their pace varies
            }

    def get_hand_time(self) -> float:
        """
        Get the time in seconds it takes this dealer to complete a hand.
        Incorporates natural variance in dealing speed.

        Returns:
            Float representing seconds per hand
        """
        base_time = 45.0 / self.speed  # baseline seconds per hand
        variance_factor = random.uniform(
            1 - self.personality["pace_variance"], 1 + self.personality["pace_variance"]
        )
        return base_time * variance_factor

    def makes_error(self) -> Tuple[bool, Optional[str]]:
        """
        Determine if the dealer makes an error on this hand.

        Returns:
            Tuple of (error_made: bool, error_type: Optional[str])
        """
        if random.random() < self.error_rate:
            error_type = weighted_choice(self.error_types)
            return True, error_type
        return False, None

    def get_shuffle_effectiveness(self) -> float:
        """
        Returns a value indicating how effective the shuffle is.

        Returns:
            Float between 0-1 representing shuffle randomness
        """
        # Add some variance to the shuffle quality
        return min(1.0, max(0.7, self.shuffle_quality * random.uniform(0.95, 1.05)))


@dataclass
class TableConditions:
    """
    Models the physical and environmental conditions of a blackjack table.

    Attributes:
        table_id: Identifier for the table
        max_players: Maximum number of players at this table
        current_players: Current number of players at the table
        rules: Blackjack rules for this table
        penetration: Percentage of shoe dealt before reshuffling
        minimum_bet: Minimum bet allowed at this table
        maximum_bet: Maximum bet allowed at this table
        avg_player_skill: Average skill level of other players (0-1)
        noise_level: Ambient noise level affecting concentration (0-1)
        session_start_time: When the current dealing session started
    """

    table_id: str
    max_players: int = 7
    current_players: int = 0
    rules: Rules = None
    penetration: float = 0.75  # percentage of shoe dealt before reshuffling
    minimum_bet: int = 10
    maximum_bet: int = 1000
    avg_player_skill: float = 0.5
    noise_level: float = 0.3  # ambient noise (0-1)
    is_crowded: bool = False
    temperature: float = 70.0  # in Fahrenheit
    lighting_quality: float = 0.8  # how well lit the table is (0-1)
    session_start_time: float = None

    def __post_init__(self):
        if self.rules is None:
            self.rules = Rules()

        if self.session_start_time is None:
            self.session_start_time = time.time()

        # Set initial player count if not specified
        if self.current_players == 0:
            self.current_players = random.randint(1, self.max_players - 1)

        self.is_crowded = self.current_players >= (self.max_players * 0.8)

    def get_hands_per_hour(self, dealer_speed: float) -> int:
        """
        Calculate the actual hands per hour based on table conditions.

        Args:
            dealer_speed: The dealer's speed factor

        Returns:
            Integer representing expected hands per hour
        """
        # Base rates: ~80 hands/hr for 1-on-1, decreasing with more players
        base_rate = 80 * dealer_speed

        # Each player adds time - diminishing returns for experienced players
        player_factor = 1.0 - (
            0.08 * self.current_players * (1 - (0.2 * self.avg_player_skill))
        )

        # Crowded tables are slower due to chip handling, etc.
        if self.is_crowded:
            player_factor *= 0.92

        # Environmental factors
        env_factor = 1.0 - (self.noise_level * 0.1)  # noise slows down play

        return int(base_rate * player_factor * env_factor)

    def player_arrives(self) -> bool:
        """
        Simulate a new player arriving at the table.

        Returns:
            Success of the arrival (False if table is full)
        """
        if self.current_players < self.max_players:
            self.current_players += 1
            self.is_crowded = self.current_players >= (self.max_players * 0.8)
            return True
        return False

    def player_leaves(self) -> bool:
        """
        Simulate a player leaving the table.

        Returns:
            Success of the departure (False if no players to remove)
        """
        if self.current_players > 0:
            self.current_players -= 1
            self.is_crowded = self.current_players >= (self.max_players * 0.8)
            return True
        return False

    def get_distractions(self) -> float:
        """
        Calculate a distraction factor that might affect player performance.

        Returns:
            Float between 0-1 representing distraction level
        """
        # Multiple factors contribute to distractions
        distraction = 0.0

        # Noise contributes to distraction
        distraction += self.noise_level * 0.5

        # Crowded tables are more distracting
        if self.is_crowded:
            distraction += 0.15

        # Poor lighting makes it harder to concentrate
        distraction += (1 - self.lighting_quality) * 0.3

        # Uncomfortable temperature affects concentration
        temp_comfort = 1.0 - min(1.0, abs(self.temperature - 72) / 15)
        distraction += (1 - temp_comfort) * 0.2

        # Cap at 1.0
        return min(1.0, distraction)


class PlayerFlowModel:
    """
    Models the flow of players joining and leaving tables over time.
    """

    def __init__(
        self,
        time_of_day: str = "evening",
        weekday: bool = True,
        casino_occupancy: float = 0.5,
    ):
        """
        Initialize player flow model.

        Args:
            time_of_day: General time ('morning', 'afternoon', 'evening', 'late_night')
            weekday: Whether it's a weekday or weekend
            casino_occupancy: Overall casino occupancy factor (0-1)
        """
        self.time_of_day = time_of_day
        self.weekday = weekday
        self.casino_occupancy = casino_occupancy

        # Configure arrival and departure rates based on parameters
        self._configure_rates()

    def _configure_rates(self):
        """Set up arrival and departure rates based on parameters."""
        # Base rates - these are probabilities per minute
        if self.time_of_day == "morning":
            self.base_arrival_rate = 0.02
            self.base_departure_rate = 0.03
        elif self.time_of_day == "afternoon":
            self.base_arrival_rate = 0.04
            self.base_departure_rate = 0.03
        elif self.time_of_day == "evening":
            self.base_arrival_rate = 0.08
            self.base_departure_rate = 0.04
        else:  # late_night
            self.base_arrival_rate = 0.03
            self.base_departure_rate = 0.06

        # Weekends have more player flow
        if not self.weekday:
            self.base_arrival_rate *= 1.5
            self.base_departure_rate *= 0.9  # people stay longer

        # Adjust for casino occupancy
        self.base_arrival_rate *= self.casino_occupancy
        self.base_departure_rate *= 1.0 + (1.0 - self.casino_occupancy) * 0.5

    def get_next_event(
        self, elapsed_minutes: float, current_players: int, max_players: int
    ) -> Tuple[str, float]:
        """
        Calculate the next player arrival or departure event.

        Args:
            elapsed_minutes: Minutes elapsed since session start
            current_players: Current number of players at table
            max_players: Maximum number of players allowed

        Returns:
            Tuple of (event_type, minutes_until_event)
        """
        # Scale rates based on current table state
        arrival_rate = self.base_arrival_rate
        departure_rate = self.base_departure_rate

        # Tables that are emptier are less attractive
        if current_players < 3:
            arrival_rate *= 0.5 + (current_players * 0.25)

        # Prevent arrivals at full tables
        if current_players >= max_players:
            arrival_rate = 0

        # Empty tables don't have departures
        if current_players == 0:
            departure_rate = 0
        else:
            # More players means more potential departures
            departure_rate *= current_players / max_players

        # Time-dependent factors (e.g., people leave after several hours)
        hours_elapsed = elapsed_minutes / 60.0
        if hours_elapsed > 2.0:
            departure_rate *= 1.0 + (hours_elapsed - 2.0) * 0.2

        # Calculate event times using exponential distribution
        if arrival_rate > 0:
            arrival_time = random.expovariate(arrival_rate)
        else:
            arrival_time = float("inf")

        if departure_rate > 0:
            departure_time = random.expovariate(departure_rate)
        else:
            departure_time = float("inf")

        # Return the event that happens first
        if arrival_time < departure_time:
            return "arrival", arrival_time
        else:
            return "departure", departure_time


class CasinoEnvironment:
    """
    Main class for simulating a casino environment with tables, dealers, and players.
    """

    def __init__(
        self,
        casino_type: str = "standard",
        time_of_day: str = "evening",
        weekday: bool = True,
        table_count: int = 3,
    ):
        """
        Initialize a casino environment.

        Args:
            casino_type: Type of casino ('budget', 'standard', 'premium')
            time_of_day: Time of day ('morning', 'afternoon', 'evening', 'late_night')
            weekday: Whether it's a weekday
            table_count: Number of blackjack tables to simulate
        """
        self.casino_type = casino_type
        self.time_of_day = time_of_day
        self.weekday = weekday

        # Set baseline environment factors based on casino type
        self._configure_environment()

        # Create tables
        self.tables = {}
        for i in range(table_count):
            table_id = f"BJ-{i+1}"
            self.tables[table_id] = self._create_table(table_id)

        # Create dealers and assign to tables
        self.dealers = {}
        self.dealer_assignments = {}
        for table_id in self.tables:
            dealer = self._create_dealer(f"D-{table_id}")
            self.dealers[dealer.name] = dealer
            self.dealer_assignments[table_id] = dealer.name

        # Create player flow model for each table
        self.player_flows = {}
        casino_occupancy = self._get_occupancy_for_time()
        for table_id in self.tables:
            self.player_flows[table_id] = PlayerFlowModel(
                time_of_day=time_of_day,
                weekday=weekday,
                casino_occupancy=casino_occupancy,
            )

        # Simulation timekeeping
        self.simulation_time = 0.0  # in minutes
        self.next_events = {}
        for table_id in self.tables:
            self._schedule_next_player_event(table_id)

    def _configure_environment(self):
        """Configure environment parameters based on casino type."""
        if self.casino_type == "budget":
            self.min_bets = {"BJ": 5, "BJ-H": 10, "BJ-VIP": 25}
            self.max_bets = {"BJ": 200, "BJ-H": 500, "BJ-VIP": 1000}
            self.noise_level = 0.7
            self.avg_player_skill = 0.4
            self.temperature = random.uniform(68, 76)
            self.lighting_quality = 0.7
        elif self.casino_type == "premium":
            self.min_bets = {"BJ": 25, "BJ-H": 50, "BJ-VIP": 100}
            self.max_bets = {"BJ": 2000, "BJ-H": 5000, "BJ-VIP": 10000}
            self.noise_level = 0.3
            self.avg_player_skill = 0.7
            self.temperature = random.uniform(70, 72)
            self.lighting_quality = 0.9
        else:  # standard
            self.min_bets = {"BJ": 10, "BJ-H": 25, "BJ-VIP": 50}
            self.max_bets = {"BJ": 500, "BJ-H": 1000, "BJ-VIP": 5000}
            self.noise_level = 0.5
            self.avg_player_skill = 0.5
            self.temperature = random.uniform(69, 74)
            self.lighting_quality = 0.8

    def _get_occupancy_for_time(self) -> float:
        """Get the casino occupancy factor based on time and day."""
        base_occupancy = {
            "morning": 0.2,
            "afternoon": 0.4,
            "evening": 0.7,
            "late_night": 0.5,
        }

        occupancy = base_occupancy.get(self.time_of_day, 0.5)

        # Weekends are busier
        if not self.weekday:
            occupancy = min(1.0, occupancy * 1.5)

        # Add some randomness
        occupancy = min(1.0, max(0.1, occupancy * random.uniform(0.8, 1.2)))

        return occupancy

    def _create_table(self, table_id: str) -> TableConditions:
        """Create a new table with appropriate conditions."""
        table_type = "BJ"  # Standard BJ table
        if "-H" in table_id:
            table_type = "BJ-H"  # High limit
        elif "-VIP" in table_id:
            table_type = "BJ-VIP"  # VIP table

        # Determine table rules
        rules = Rules()

        # Adjust rules based on table type and casino
        if self.casino_type == "budget":
            rules.blackjack_payout = 6 / 5  # Budget casinos often have worse payouts
            rules.dealer_hit_soft_17 = True
        elif table_type in ["BJ-H", "BJ-VIP"] and self.casino_type == "premium":
            rules.blackjack_payout = 2 / 1  # Better odds at premium high limit
            rules.dealer_hit_soft_17 = False

        # Create the table
        return TableConditions(
            table_id=table_id,
            rules=rules,
            minimum_bet=self.min_bets[table_type],
            maximum_bet=self.max_bets[table_type],
            avg_player_skill=self.avg_player_skill,
            noise_level=self.noise_level,
            temperature=self.temperature,
            lighting_quality=self.lighting_quality,
            penetration=random.uniform(0.65, 0.8),
        )

    def _create_dealer(self, name: str) -> DealerProfile:
        """Create a dealer with appropriate characteristics."""
        # Skill varies by casino type
        if self.casino_type == "budget":
            speed = random.uniform(0.8, 1.0)
            error_rate = random.uniform(0.01, 0.03)
            shuffle_quality = random.uniform(0.85, 0.95)
        elif self.casino_type == "premium":
            speed = random.uniform(1.0, 1.2)
            error_rate = random.uniform(0.001, 0.005)
            shuffle_quality = random.uniform(0.95, 1.0)
        else:  # standard
            speed = random.uniform(0.9, 1.1)
            error_rate = random.uniform(0.005, 0.015)
            shuffle_quality = random.uniform(0.9, 0.98)

        return DealerProfile(
            name=name,
            speed=speed,
            error_rate=error_rate,
            shuffle_quality=shuffle_quality,
        )

    def _schedule_next_player_event(self, table_id: str):
        """Schedule the next player arrival or departure at a table."""
        table = self.tables[table_id]
        player_flow = self.player_flows[table_id]

        event_type, time_until_event = player_flow.get_next_event(
            elapsed_minutes=self.simulation_time,
            current_players=table.current_players,
            max_players=table.max_players,
        )

        self.next_events[table_id] = (
            event_type,
            self.simulation_time + time_until_event,
        )

    def advance_time(self, minutes: float):
        """
        Advance the simulation by a specified number of minutes.

        Args:
            minutes: Minutes to advance simulation
        """
        target_time = self.simulation_time + minutes

        # Process events until we reach target time
        while self.simulation_time < target_time:
            # Find the next event across all tables
            next_event_time = target_time
            next_event_table = None
            next_event_type = None

            for table_id, (event_type, event_time) in self.next_events.items():
                if event_time < next_event_time:
                    next_event_time = event_time
                    next_event_table = table_id
                    next_event_type = event_type

            # If there's an event before target_time, process it
            if next_event_table and next_event_time < target_time:
                # Advance time to the event
                self.simulation_time = next_event_time

                # Process the event
                table = self.tables[next_event_table]
                if (
                    next_event_type == "arrival"
                    and table.current_players < table.max_players
                ):
                    table.player_arrives()
                elif next_event_type == "departure" and table.current_players > 0:
                    table.player_leaves()

                # Schedule the next event for this table
                self._schedule_next_player_event(next_event_table)
            else:
                # No more events before target time, so jump ahead
                self.simulation_time = target_time

    def get_table_conditions(self, table_id: str) -> TableConditions:
        """
        Get the current conditions at a specific table.

        Args:
            table_id: ID of the table to check

        Returns:
            TableConditions object for the specified table
        """
        return self.tables.get(table_id)

    def get_dealer(self, table_id: str) -> DealerProfile:
        """
        Get the dealer assigned to a specific table.

        Args:
            table_id: ID of the table

        Returns:
            DealerProfile for the dealer at the specified table
        """
        dealer_name = self.dealer_assignments.get(table_id)
        return self.dealers.get(dealer_name)

    def get_play_quality_modifier(self, table_id: str) -> float:
        """
        Get a modifier that affects player strategy execution quality.

        Args:
            table_id: ID of the table

        Returns:
            Float factor representing environmental effects on play quality
        """
        table = self.tables.get(table_id)
        if not table:
            return 1.0

        # Start with distraction factor
        distraction = table.get_distractions()

        # Dealer can affect play quality
        dealer = self.get_dealer(table_id)
        dealer_factor = 1.0
        if dealer:
            # Friendly dealers improve play quality slightly
            dealer_factor += (dealer.personality.get("friendliness", 0.5) - 0.5) * 0.1

            # Attentive dealers catch more mistakes
            dealer_factor += (dealer.personality.get("attentiveness", 0.5) - 0.5) * 0.05

        # Final quality modifier - higher means better play quality
        quality_modifier = 1.0 - (distraction * 0.3) + (dealer_factor - 1.0)

        # Ensure reasonable bounds
        return max(0.7, min(1.2, quality_modifier))

    def get_casino_stats(self) -> Dict:
        """
        Get current statistics about the casino environment.

        Returns:
            Dictionary of casino statistics
        """
        total_players = sum(table.current_players for table in self.tables.values())
        total_capacity = sum(table.max_players for table in self.tables.values())
        occupancy_rate = total_players / total_capacity if total_capacity > 0 else 0

        stats = {
            "time_elapsed_minutes": self.simulation_time,
            "total_players": total_players,
            "total_capacity": total_capacity,
            "occupancy_rate": occupancy_rate,
            "table_stats": {
                table_id: {
                    "players": table.current_players,
                    "max_players": table.max_players,
                    "min_bet": table.minimum_bet,
                    "is_crowded": table.is_crowded,
                    "dealer": self.dealer_assignments.get(table_id),
                }
                for table_id, table in self.tables.items()
            },
        }

        return stats


class EnvironmentAwareBankrollManager:
    """
    Bankroll management strategy that adapts to casino environment.
    """

    def __init__(
        self,
        initial_bankroll: float,
        risk_tolerance: float = 0.5,
        target_session_length: float = 4.0,  # hours
        loss_stop_pct: float = 0.5,
        win_stop_pct: float = 1.0,
    ):
        """
        Initialize a bankroll manager.

        Args:
            initial_bankroll: Starting bankroll amount
            risk_tolerance: How much risk the player is willing to take (0-1)
            target_session_length: Target session length in hours
            loss_stop_pct: Stop playing when this percentage of bankroll is lost
            win_stop_pct: Stop playing when this percentage of bankroll is won
        """
        self.initial_bankroll = initial_bankroll
        self.current_bankroll = initial_bankroll
        self.risk_tolerance = risk_tolerance
        self.target_session_length = target_session_length
        self.loss_stop_pct = loss_stop_pct
        self.win_stop_pct = win_stop_pct

        # Session tracking
        self.session_start_bankroll = initial_bankroll
        self.session_start_time = time.time()
        self.hands_played = 0
        self.total_wagered = 0.0
        self.session_high = initial_bankroll
        self.session_low = initial_bankroll

    def calculate_optimal_bet(
        self, table: TableConditions, edge: float, variance: float
    ) -> float:
        """
        Calculate optimal bet size given current conditions.

        Args:
            table: Current table conditions
            edge: Estimated player edge as a decimal (-0.02 = 2% house edge)
            variance: Estimated variance of returns

        Returns:
            Recommended bet amount
        """
        # Kelly criterion with adjustments
        if edge <= 0:
            kelly_fraction = 0
        else:
            kelly_fraction = edge / variance

        # Apply risk tolerance as a fraction of full Kelly
        bet_fraction = kelly_fraction * self.risk_tolerance

        # Cap the bet fraction for safety
        bet_fraction = min(0.05, bet_fraction)

        # Calculate raw bet
        raw_bet = self.current_bankroll * bet_fraction

        # Adjust for table limits
        bet = max(table.minimum_bet, min(table.maximum_bet, raw_bet))

        # Round to appropriate betting unit
        if bet < 25:
            return round(bet / 5) * 5  # Round to nearest $5
        elif bet < 100:
            return round(bet / 25) * 25  # Round to nearest $25
        else:
            return round(bet / 100) * 100  # Round to nearest $100

    def should_continue_session(
        self, elapsed_hours: float, cumulative_fatigue: float = 0.0
    ) -> bool:
        """
        Determine if the player should continue the session.

        Args:
            elapsed_hours: Hours played in this session
            cumulative_fatigue: Fatigue factor (0-1)

        Returns:
            Boolean indicating whether to continue playing
        """
        # Check time-based stop
        if elapsed_hours >= self.target_session_length:
            return False

        # Check win-based stop
        if self.current_bankroll >= (
            self.session_start_bankroll * (1 + self.win_stop_pct)
        ):
            return False

        # Check loss-based stop
        if self.current_bankroll <= (
            self.session_start_bankroll * (1 - self.loss_stop_pct)
        ):
            return False

        # Fatigue-based decision - more likely to quit when tired
        if cumulative_fatigue > 0.7 and random.random() < cumulative_fatigue * 0.5:
            return False

        return True

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

    def get_session_stats(self) -> Dict:
        """
        Get current session statistics.

        Returns:
            Dictionary of session statistics
        """
        elapsed_hours = (time.time() - self.session_start_time) / 3600.0
        net_result = self.current_bankroll - self.session_start_bankroll
        roi = (
            net_result / self.session_start_bankroll
            if self.session_start_bankroll > 0
            else 0
        )

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
        }
