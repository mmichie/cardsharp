"""
Web adapter implementation for the Cardsharp engine.

This module provides a web-based adapter for the Cardsharp engine,
enabling interactive play through a web interface using Streamlit.
It also includes WebSocket support for real-time communication.
"""

import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Union
from enum import Enum
import queue
import uuid

from cardsharp.adapters.base import PlatformAdapter
from cardsharp.events import EventBus, EngineEventType, EventPriority

# Import Action from base which will handle the import or mock it
from cardsharp.adapters.base import Action

# Import WebSocket handler if available
try:
    from cardsharp.events.websocket import (
        ServerMessage,
        get_websocket_handler,
    )

    _has_websocket = True
except ImportError:
    _has_websocket = False

# Setup logging
logger = logging.getLogger("cardsharp.adapters.web")


class WebAdapter(PlatformAdapter):
    """
    Web-based adapter for the Cardsharp engine.

    This adapter uses Streamlit's session state to maintain game state and
    handle user interactions asynchronously. It also supports WebSocket
    communication for real-time updates.
    """

    def __init__(self, use_websockets: bool = True):
        """
        Initialize the web adapter.

        Args:
            use_websockets: Whether to use WebSocket communication
        """
        # Event queue for communication between Streamlit and the engine
        self.action_queue = asyncio.Queue()
        self.state_queue = asyncio.Queue()
        self.event_queue = asyncio.Queue()

        # Thread-safe queues for bridging async and sync worlds
        self.thread_action_queue = queue.Queue()
        self.thread_state_queue = queue.Queue()
        self.thread_event_queue = queue.Queue()

        # Latest state for rendering
        self.current_state = {}

        # Thread for monitoring thread-safe queues
        self.queue_monitor_task = None
        self.running = False

        # WebSocket support
        self.use_websockets = use_websockets and _has_websocket
        self.websocket_handler = None
        self.client_id = str(uuid.uuid4())
        self.event_bus = EventBus.get_instance()

        # Keep track of pending action requests
        self.pending_action_requests = {}

    async def initialize(self) -> None:
        """Initialize the web adapter."""
        self.running = True
        self.queue_monitor_task = asyncio.create_task(self._monitor_thread_queues())

        # Initialize WebSocket handler if requested
        if self.use_websockets:
            try:
                # Get the WebSocket handler
                self.websocket_handler = get_websocket_handler()

                # Start the WebSocket handler
                await self.websocket_handler.start()

                # Connect as a client
                self.client_id = await self.websocket_handler.connect_client(
                    self.client_id, self._handle_websocket_message
                )

                # Subscribe to relevant events
                await self.websocket_handler.handle_client_message(
                    self.client_id,
                    {
                        "type": "subscribe",
                        "data": {"event_types": ["*"]},  # Subscribe to all events
                    },
                )

                logger.info(f"WebSocket initialized with client ID: {self.client_id}")
            except Exception as e:
                logger.error(f"Error initializing WebSocket: {e}", exc_info=True)
                self.use_websockets = False

        # Listen for user interaction events
        self.event_bus.on(
            EngineEventType.USER_INTERACTION_RECEIVED,
            self._handle_user_interaction,
            EventPriority.HIGH,
        )

    async def shutdown(self) -> None:
        """Shutdown the web adapter."""
        self.running = False

        if self.queue_monitor_task:
            self.queue_monitor_task.cancel()
            try:
                await self.queue_monitor_task
            except asyncio.CancelledError:
                pass

        # Shutdown WebSocket handler if used
        if self.use_websockets and self.websocket_handler:
            # Disconnect as a client
            await self.websocket_handler.disconnect_client(self.client_id)

            # Stop the WebSocket handler
            await self.websocket_handler.stop()

    def _handle_websocket_message(self, message: Dict[str, Any]) -> None:
        """
        Handle a message from the WebSocket handler.

        Args:
            message: The message to handle
        """
        message_type = message.get("type", "")
        message_data = message.get("data", {})

        # Handle different message types
        if message_type == ServerMessage.EVENT:
            # Event message
            event_type = message_data.get("event_type", "")
            event_data = message_data.get("data", {})

            # Add to the event queue
            self.thread_event_queue.put((event_type, event_data))

        elif message_type == ServerMessage.ACTION_REQUEST:
            # Action request
            request_id = message_data.get("request_id", "")
            player_id = message_data.get("player_id", "")
            player_name = message_data.get("player_name", "")
            valid_actions = message_data.get("valid_actions", [])

            # Store the action request
            self.pending_action_requests[request_id] = {
                "player_id": player_id,
                "player_name": player_name,
                "valid_actions": valid_actions,
                "timestamp": time.time(),
            }

            # Add to the event queue
            self.thread_event_queue.put(("ACTION_REQUEST", message_data))

    async def _handle_user_interaction(self, data: Dict[str, Any]) -> None:
        """
        Handle a user interaction event.

        Args:
            data: The event data
        """
        action = data.get("action", "")
        action_data = data.get("data", {})

        if action == "player_action":
            # Player action - put in the action queue
            action_name = action_data.get("action", "")
            request_id = action_data.get("request_id", "")

            # If this is a response to a pending action request, handle it
            if request_id in self.pending_action_requests:
                # Remove from pending requests
                self.pending_action_requests.pop(request_id, None)

                # Put in the action queue
                await self.action_queue.put(action_name)
            else:
                # Put in the action queue anyway
                await self.action_queue.put(action_name)

    async def _monitor_thread_queues(self) -> None:
        """Monitor thread-safe queues and transfer items to async queues."""
        try:
            while self.running:
                # Check for actions from the web interface
                try:
                    while not self.thread_action_queue.empty():
                        action_data = self.thread_action_queue.get_nowait()

                        # If using WebSockets, emit an event
                        if self.use_websockets:
                            self.event_bus.emit(
                                EngineEventType.USER_INTERACTION_RECEIVED,
                                {
                                    "action": "player_action",
                                    "data": {
                                        "action": action_data,
                                        "client_id": self.client_id,
                                    },
                                },
                            )

                        # Also put directly in the action queue
                        await self.action_queue.put(action_data)
                except queue.Empty:
                    pass

                # Let other tasks run
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            # Task was cancelled, just exit
            return

    async def render_game_state(self, state: Dict[str, Any]) -> None:
        """
        Send the game state to the web interface.

        Args:
            state: The current game state
        """
        # Store the current state
        self.current_state = state

        # Put the state in the queue for the web interface
        self.thread_state_queue.put(state)

        # Also put it in the async queue for tests or other async consumers
        await self.state_queue.put(state)

        # If using WebSockets, emit a UI update event
        if self.use_websockets and self.websocket_handler:
            self.event_bus.emit(
                EngineEventType.UI_UPDATE_NEEDED,
                {"state": state, "timestamp": time.time()},
            )

    async def request_player_action(
        self,
        player_id: str,
        player_name: str,
        valid_actions: List[Action],
        timeout_seconds: Optional[float] = None,
    ) -> Action:
        """
        Request an action from a player via the web interface.

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
        # Generate a unique request ID
        request_id = str(uuid.uuid4())

        # Store the request information in a format the web interface can use
        action_request = {
            "request_id": request_id,
            "player_id": player_id,
            "player_name": player_name,
            "valid_actions": [action.name for action in valid_actions],
            "pending": True,
            "timestamp": time.time(),
        }

        # Put the request in the queue for the web interface
        self.thread_event_queue.put(("ACTION_REQUEST", action_request))

        # If using WebSockets, emit a user interaction needed event
        if self.use_websockets and self.websocket_handler:
            self.event_bus.emit(
                EngineEventType.USER_INTERACTION_NEEDED,
                {
                    "request_id": request_id,
                    "player_id": player_id,
                    "player_name": player_name,
                    "valid_actions": [action.name for action in valid_actions],
                    "timestamp": time.time(),
                },
            )

            # Also send directly to connected clients
            self.websocket_handler.broadcast(
                ServerMessage.ACTION_REQUEST, action_request
            )

        # Wait for the action from the web interface
        try:
            if timeout_seconds:
                action_name = await asyncio.wait_for(
                    self.action_queue.get(), timeout_seconds
                )
            else:
                action_name = await self.action_queue.get()

            # Convert action name to Action enum
            for action in valid_actions:
                if action.name == action_name:
                    return action

            # If the action is not valid, default to STAND if available
            if Action.STAND in valid_actions:
                return Action.STAND
            else:
                return valid_actions[0]

        except asyncio.TimeoutError:
            # Player timed out
            raise TimeoutError(f"Player {player_name} timed out")

    async def notify_game_event(
        self, event_type: Union[str, Enum], data: Dict[str, Any]
    ) -> None:
        """
        Notify the web interface of a game event.

        Args:
            event_type: The type of event that occurred
            data: Data associated with the event
        """
        # Convert enum to string if necessary
        event_type_str = event_type.name if isinstance(event_type, Enum) else event_type

        # Put the event in the queue for the web interface
        event_data = {"type": event_type_str, "data": data, "timestamp": time.time()}
        self.thread_event_queue.put(("GAME_EVENT", event_data))

        # Also put it in the async queue
        await self.event_queue.put((event_type_str, data))

        # WebSocket handling is done automatically by the event bus

    async def handle_timeout(self, player_id: str, player_name: str) -> Action:
        """
        Handle a player timeout by defaulting to STAND.

        Args:
            player_id: Unique identifier for the player
            player_name: Display name of the player

        Returns:
            The default action (STAND)
        """
        # Notify the web interface of the timeout
        timeout_data = {
            "player_id": player_id,
            "player_name": player_name,
            "timestamp": time.time(),
        }
        self.thread_event_queue.put(("TIMEOUT", timeout_data))

        # If using WebSockets, emit a timeout event
        if self.use_websockets:
            self.event_bus.emit(EngineEventType.PLAYER_TIMEOUT, timeout_data)

        # Return STAND as the default action
        return Action.STAND

    # Synchronous methods for the web interface

    def get_current_state(self) -> Dict[str, Any]:
        """
        Get the current game state.

        Returns:
            The current game state
        """
        return self.current_state

    def get_next_state(self, timeout=0.1) -> Optional[Dict[str, Any]]:
        """
        Get the next game state from the queue.

        Args:
            timeout: Timeout in seconds

        Returns:
            The next game state or None if no state is available
        """
        try:
            return self.thread_state_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_next_event(self, timeout=0.1) -> Optional[tuple]:
        """
        Get the next event from the queue.

        Args:
            timeout: Timeout in seconds

        Returns:
            Tuple of (event_type, event_data) or None if no event is available
        """
        try:
            return self.thread_event_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def submit_action(self, action_name: str, request_id: Optional[str] = None) -> None:
        """
        Submit a player action.

        Args:
            action_name: Name of the action to take
            request_id: Optional ID of the action request this is responding to
        """
        # If using WebSockets, we'll use the event bus
        if self.use_websockets:
            action_data = {
                "action": action_name,
                "request_id": request_id,
                "client_id": self.client_id,
                "timestamp": time.time(),
            }

            # Emit event via event bus
            self.event_bus.emit(
                EngineEventType.USER_INTERACTION_RECEIVED,
                {"action": "player_action", "data": action_data},
            )

        # Also use the direct queue for backward compatibility
        self.thread_action_queue.put(action_name)

    def get_websocket_client_id(self) -> Optional[str]:
        """
        Get the WebSocket client ID for this adapter.

        Returns:
            The client ID or None if WebSockets are not enabled
        """
        if self.use_websockets:
            return self.client_id
        return None
