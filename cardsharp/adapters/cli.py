"""
Command-line interface adapter for the Cardsharp engine.

This module provides an adapter for console-based interactions with the
Cardsharp engine, enabling backward compatibility with the current interface.
"""

import asyncio
import sys
from typing import List, Dict, Any, Optional, Union, Awaitable, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from asyncio import Task

from cardsharp.adapters.base import PlatformAdapter

# Import Action from base which will handle the import or mock it
from cardsharp.adapters.base import Action

# Import IOInterface if available, otherwise define a mock
try:
    from cardsharp.common.io_interface import IOInterface, ConsoleIOInterface
except ImportError:
    # Define a simple mock IOInterface
    class IOInterface:
        """Mock IOInterface for when common module is not available."""

        def input(self, prompt):
            return input(prompt)

        def output(self, text):
            print(text)

    class ConsoleIOInterface(IOInterface):
        """Mock ConsoleIOInterface."""

        pass


class CLIAdapter(PlatformAdapter):
    """
    Command-line interface adapter for the Cardsharp engine.

    This adapter uses the standard console for input/output, providing a
    simple text-based interface to the game.
    """

    def __init__(self, io_interface: Optional[IOInterface] = None):
        """
        Initialize the CLI adapter.

        Args:
            io_interface: Optional IOInterface to use for I/O. If None, a default
                          console IOInterface will be created.
        """
        self.io_interface = io_interface

        # If no IOInterface is provided, we'll create one on initialize()
        if self.io_interface is None:
            from cardsharp.common.io_interface import ConsoleIOInterface

            self.io_interface = ConsoleIOInterface()

        # Event queue for asynchronous operation
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._input_event: asyncio.Event = asyncio.Event()

        # Flag to track if we're using the async input loop
        self._async_input_running: bool = False
        self._input_task: Optional[asyncio.Task[None]] = None

    async def initialize(self) -> None:
        """Initialize the CLI adapter."""
        # Start the async input loop if not already running
        if not self._async_input_running:
            self._async_input_running = True
            self._input_task = asyncio.create_task(self._input_loop())

    async def shutdown(self) -> None:
        """Shutdown the CLI adapter."""
        # Stop the async input loop if running
        if self._async_input_running:
            self._async_input_running = False
            if self._input_task:
                self._input_task.cancel()
                try:
                    await self._input_task
                except asyncio.CancelledError:
                    pass

    async def _input_loop(self) -> None:
        """Background task to handle input asynchronously."""
        try:
            while self._async_input_running:
                # Wait for input to be requested
                await self._input_event.wait()

                # Get input from the console (blocking)
                user_input = self.io_interface.input("> ")

                # Put the input in the queue
                await self._input_queue.put(user_input)

                # Reset the event
                self._input_event.clear()
        except asyncio.CancelledError:
            # Task was cancelled, just exit
            return
        except Exception as e:
            # Log any other exceptions
            print(f"Error in input loop: {e}", file=sys.stderr)

    async def render_game_state(self, state: Dict[str, Any]) -> None:
        """
        Render the current game state to the console.

        Args:
            state: The current game state
        """
        # Print a header
        self.io_interface.output("\n=== Current Game State ===")

        # Print dealer information
        dealer = state.get("dealer", {})
        dealer_hand = dealer.get("hand", [])
        dealer_value = dealer.get("value", 0)

        if dealer.get("hide_second_card", False) and len(dealer_hand) > 1:
            # Only show the first card if the second card should be hidden
            visible_hand = [dealer_hand[0], "?"]
            self.io_interface.output(f"Dealer: {visible_hand[0]}, ???")
        else:
            # Show the full hand
            self.io_interface.output(
                f"Dealer: {', '.join(map(str, dealer_hand))} ({dealer_value})"
            )

        # Print player information
        players = state.get("players", [])
        for i, player in enumerate(players):
            player_name = player.get("name", f"Player {i+1}")

            # Print each hand for the player
            hands = player.get("hands", [])
            for j, hand in enumerate(hands):
                hand_str = ", ".join(map(str, hand.get("cards", [])))
                hand_value = hand.get("value", 0)
                bet = hand.get("bet", 0)

                if len(hands) > 1:
                    self.io_interface.output(
                        f"{player_name} - Hand {j+1}: {hand_str} ({hand_value}) - Bet: ${bet}"
                    )
                else:
                    self.io_interface.output(
                        f"{player_name}: {hand_str} ({hand_value}) - Bet: ${bet}"
                    )

            # Print player's money
            self.io_interface.output(
                f"{player_name}'s Balance: ${player.get('balance', 0)}"
            )

        # Print footer
        self.io_interface.output("===========================\n")

    async def request_player_action(
        self,
        player_id: str,
        player_name: str,
        valid_actions: List[Action],
        timeout_seconds: Optional[float] = None,
    ) -> Action:
        """
        Request an action from a player via the console.

        Args:
            player_id: Unique identifier for the player
            player_name: Display name of the player
            valid_actions: List of valid actions the player can take
            timeout_seconds: Optional timeout for the player's decision

        Returns:
            The player's chosen action

        Raises:
            TimeoutError: If the player doesn't respond within the timeout period
        """
        # Map numbers to actions for easier input
        action_map = {str(i + 1): action for i, action in enumerate(valid_actions)}

        # Also map action names to actions
        for action in valid_actions:
            action_map[action.name.lower()] = action

        # Display the options
        self.io_interface.output(f"\n{player_name}'s turn. Valid actions:")
        for i, action in enumerate(valid_actions):
            self.io_interface.output(f"{i+1}: {action.name}")

        # If using async input, use the queue
        if self._async_input_running:
            # Signal that we need input
            self._input_event.set()

            # Wait for input with optional timeout
            try:
                if timeout_seconds:
                    choice = await asyncio.wait_for(
                        self._input_queue.get(), timeout_seconds
                    )
                else:
                    choice = await self._input_queue.get()
            except asyncio.TimeoutError:
                raise TimeoutError(f"Player {player_name} timed out")
        else:
            # Fall back to synchronous input
            try:
                choice = self.io_interface.input("Enter your choice: ")
            except KeyboardInterrupt:
                raise TimeoutError(f"Player {player_name} cancelled")

        # Convert the choice to an action
        choice = choice.strip().lower()
        if choice in action_map:
            return action_map[choice]
        else:
            # If invalid, ask again recursively
            self.io_interface.output("Invalid choice. Please try again.")
            return await self.request_player_action(
                player_id, player_name, valid_actions, timeout_seconds
            )

    async def notify_game_event(
        self, event_type: Union[str, Enum], data: Dict[str, Any]
    ) -> None:
        """
        Notify the user of a game event via the console.

        Args:
            event_type: The type of event that occurred
            data: Data associated with the event
        """
        # Convert enum to string if necessary
        if isinstance(event_type, Enum):
            event_type = event_type.name

        # Format the message based on the event type
        message = self._format_event_message(event_type, data)
        if message:
            self.io_interface.output(message)

    def _format_event_message(
        self, event_type: str, data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Format an event message based on the event type.

        Args:
            event_type: The type of event
            data: Data associated with the event

        Returns:
            Formatted message string or None if no message needed
        """
        # Handle different event types with appropriate messages
        if event_type == "CARD_DEALT":
            # Format card dealt message
            card = data.get("card", "Unknown Card")
            player_name = data.get("player_name", "Unknown Player")
            if data.get("is_dealer", False):
                return f"Dealer gets {card}"
            else:
                return f"{player_name} gets {card}"

        elif event_type == "PLAYER_ACTION":
            # Format player action message
            player_name = data.get("player_name", "Unknown Player")
            action_type = data.get("action_type", "Unknown Action")
            return f"{player_name} {action_type.lower()}s"

        elif event_type == "HAND_RESULT":
            # Format hand result message
            player_name = data.get("player_name", "Unknown Player")
            result = data.get("result", "unknown")
            if data.get("is_blackjack", False):
                if data.get("is_dealer", False):
                    return "Dealer has Blackjack!"
                else:
                    return f"{player_name} has Blackjack!"
            elif data.get("is_busted", False):
                if data.get("is_dealer", False):
                    return "Dealer busts!"
                else:
                    return f"{player_name} busts!"
            else:
                return f"{player_name} {result}s"

        elif event_type == "PAYOUT":
            # Format payout message
            player_name = data.get("player_name", "Unknown Player")
            payout = data.get("payout", 0)
            bet = data.get("bet", 0)
            if payout > 0:
                return f"{player_name} wins ${payout - bet}"
            elif payout == bet:
                return f"{player_name} pushes, gets back ${bet}"
            else:
                return f"{player_name} loses ${bet}"

        # Default fallback
        return None

    async def handle_timeout(
        self, player_id: str, player_name: str
    ) -> Awaitable[Action]:
        """
        Handle a player timeout by defaulting to STAND.

        Args:
            player_id: Unique identifier for the player
            player_name: Display name of the player

        Returns:
            The default action (STAND)
        """
        self.io_interface.output(f"{player_name} timed out. Standing by default.")
        return Action.STAND
