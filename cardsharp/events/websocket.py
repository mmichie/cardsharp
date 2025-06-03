"""
WebSocket event handler for the Cardsharp engine.

This module provides WebSocket support for the event system, allowing real-time
communication between the Cardsharp engine and web clients.
"""

import asyncio
import logging
import threading
import time
import uuid
from typing import Any, Dict, Set, Optional, Union, Callable
from enum import Enum

from cardsharp.events.emitter import (
    EventBus,
    EventPriority,
    EngineEventType,
)

# Setup logging
logger = logging.getLogger("cardsharp.events.websocket")


class ClientMessage:
    """Message types that clients can send to the server."""

    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    ACTION = "action"
    HEARTBEAT = "heartbeat"
    CONNECT = "connect"
    DISCONNECT = "disconnect"


class ServerMessage:
    """Message types that the server can send to clients."""

    EVENT = "event"
    ACTION_REQUEST = "action_request"
    ERROR = "error"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    HEARTBEAT = "heartbeat"


class WebSocketClient:
    """
    Represents a connected WebSocket client.

    This class tracks a client's subscriptions and provides methods
    for sending messages to the client.
    """

    def __init__(self, client_id: str, send_callback: Callable[[Dict[str, Any]], None]):
        """
        Initialize a WebSocket client.

        Args:
            client_id: Unique identifier for the client
            send_callback: Function to call to send a message to the client
        """
        self.id = client_id
        self._send = send_callback
        self.subscriptions: Set[str] = set()
        self.game_id: Optional[str] = None
        self.player_id: Optional[str] = None
        self.connected_at = time.time()
        self.last_activity = time.time()

    def send(self, message_type: str, data: Dict[str, Any]) -> None:
        """
        Send a message to the client.

        Args:
            message_type: Type of message to send
            data: Data to include in the message
        """
        message = {"type": message_type, "data": data, "timestamp": time.time()}
        self._send(message)
        self.last_activity = time.time()

    def send_event(
        self, event_type: Union[str, Enum], event_data: Dict[str, Any]
    ) -> None:
        """
        Send an event to the client.

        Args:
            event_type: Type of event
            event_data: Event data
        """
        # Convert enum to string if necessary
        if isinstance(event_type, Enum):
            event_type = event_type.name

        # Only send if client is subscribed to this event type
        if "*" in self.subscriptions or event_type in self.subscriptions:
            self.send(
                ServerMessage.EVENT, {"event_type": event_type, "data": event_data}
            )


class WebSocketEventHandler:
    """
    Handles WebSocket events for the Cardsharp engine.

    This class bridges the gap between the event system and WebSocket clients.
    It manages client connections, handles subscriptions, and routes events.
    """

    def __init__(self):
        """Initialize the WebSocket event handler."""
        self.event_bus = EventBus.get_instance()
        self.clients: Dict[str, WebSocketClient] = {}
        self._client_lock = threading.RLock()

        # Register with the event bus to receive all events
        self.event_subscription = self.event_bus.on_any(
            self._handle_event, EventPriority.LOW
        )

        # Start the heartbeat task
        self.heartbeat_task = None
        self.running = False

    async def start(self):
        """Start the WebSocket event handler."""
        self.running = True
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self):
        """Stop the WebSocket event handler."""
        self.running = False
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass

        # Unsubscribe from the event bus
        if self.event_subscription:
            self.event_subscription()

    async def _heartbeat_loop(self):
        """Send periodic heartbeats to clients and clean up disconnected clients."""
        try:
            while self.running:
                # Send heartbeats and check for disconnected clients
                current_time = time.time()
                disconnected_clients = []

                with self._client_lock:
                    for client_id, client in self.clients.items():
                        # Send heartbeat
                        try:
                            client.send(
                                ServerMessage.HEARTBEAT, {"timestamp": current_time}
                            )
                        except Exception as e:
                            logger.warning(
                                f"Error sending heartbeat to client {client_id}: {e}"
                            )
                            disconnected_clients.append(client_id)

                        # Check if client is still connected (no activity for 30 seconds)
                        if current_time - client.last_activity > 30.0:
                            logger.info(f"Client {client_id} timed out")
                            disconnected_clients.append(client_id)

                # Disconnect clients that timed out or had errors
                for client_id in disconnected_clients:
                    await self.disconnect_client(client_id)

                # Wait for next heartbeat
                await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            # Task was cancelled, just exit
            return
        except Exception as e:
            logger.error(f"Error in heartbeat loop: {e}", exc_info=True)

    def _handle_event(self, event_data):
        """
        Handle an event from the event bus.

        Args:
            event_data: Tuple of (event_type, event_data)
        """
        event_type, data = event_data

        # Broadcast to subscribed clients
        with self._client_lock:
            for client in self.clients.values():
                try:
                    client.send_event(event_type, data)
                except Exception as e:
                    logger.warning(f"Error sending event to client {client.id}: {e}")

    async def connect_client(
        self,
        client_id: Optional[str] = None,
        send_callback: Callable[[Dict[str, Any]], None] = None,
    ) -> str:
        """
        Connect a new WebSocket client.

        Args:
            client_id: Optional client ID. If not provided, a new ID will be generated.
            send_callback: Function to call to send a message to the client

        Returns:
            The client ID
        """
        if client_id is None:
            client_id = str(uuid.uuid4())

        if send_callback is None:
            # Default callback that does nothing
            send_callback = lambda msg: None

        # Create a new client
        client = WebSocketClient(client_id, send_callback)

        # Add to clients
        with self._client_lock:
            self.clients[client_id] = client

        # Send connected message
        client.send(ServerMessage.CONNECTED, {"client_id": client_id})

        logger.info(f"Client {client_id} connected")
        return client_id

    async def disconnect_client(self, client_id: str) -> None:
        """
        Disconnect a WebSocket client.

        Args:
            client_id: ID of the client to disconnect
        """
        with self._client_lock:
            client = self.clients.pop(client_id, None)

        if client:
            # Send disconnected message
            try:
                client.send(ServerMessage.DISCONNECTED, {"client_id": client_id})
            except Exception:
                pass

            logger.info(f"Client {client_id} disconnected")

    async def handle_client_message(
        self, client_id: str, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle a message from a client.

        Args:
            client_id: ID of the client sending the message
            message: The message to handle

        Returns:
            Response to send back to the client
        """
        # Get the client
        with self._client_lock:
            client = self.clients.get(client_id)

        if not client:
            logger.warning(f"Received message from unknown client {client_id}")
            return {"type": ServerMessage.ERROR, "data": {"message": "Unknown client"}}

        # Update client activity time
        client.last_activity = time.time()

        # Handle message based on type
        message_type = message.get("type", "")
        message_data = message.get("data", {})

        if message_type == ClientMessage.SUBSCRIBE:
            # Subscribe the client to event types
            event_types = message_data.get("event_types", [])
            with self._client_lock:
                client.subscriptions.update(event_types)

            return {
                "type": ServerMessage.CONNECTED,
                "data": {"subscriptions": list(client.subscriptions)},
            }

        elif message_type == ClientMessage.UNSUBSCRIBE:
            # Unsubscribe the client from event types
            event_types = message_data.get("event_types", [])
            with self._client_lock:
                client.subscriptions.difference_update(event_types)

            return {
                "type": ServerMessage.CONNECTED,
                "data": {"subscriptions": list(client.subscriptions)},
            }

        elif message_type == ClientMessage.ACTION:
            # Handle client action (forward to the event bus)
            action = message_data.get("action", "")
            action_data = message_data.get("data", {})

            # Add client ID to action data
            action_data["client_id"] = client_id

            # Emit to event bus
            self.event_bus.emit(
                EngineEventType.USER_INTERACTION_RECEIVED,
                {"action": action, "data": action_data},
            )

            return {
                "type": ServerMessage.EVENT,
                "data": {"event_type": "action_received"},
            }

        elif message_type == ClientMessage.HEARTBEAT:
            # Just update the activity time (already done above)
            return {"type": ServerMessage.HEARTBEAT, "data": {"timestamp": time.time()}}

        else:
            logger.warning(
                f"Unknown message type from client {client_id}: {message_type}"
            )
            return {
                "type": ServerMessage.ERROR,
                "data": {"message": "Unknown message type"},
            }

    def get_connected_clients(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all connected clients.

        Returns:
            Dictionary mapping client IDs to client information
        """
        result = {}
        with self._client_lock:
            for client_id, client in self.clients.items():
                result[client_id] = {
                    "id": client.id,
                    "connected_at": client.connected_at,
                    "last_activity": client.last_activity,
                    "subscriptions": list(client.subscriptions),
                    "game_id": client.game_id,
                    "player_id": client.player_id,
                }

        return result

    def send_to_client(
        self, client_id: str, message_type: str, data: Dict[str, Any]
    ) -> bool:
        """
        Send a message to a specific client.

        Args:
            client_id: ID of the client to send to
            message_type: Type of message to send
            data: Data to include in the message

        Returns:
            True if the message was sent, False otherwise
        """
        with self._client_lock:
            client = self.clients.get(client_id)

        if client:
            try:
                client.send(message_type, data)
                return True
            except Exception as e:
                logger.warning(f"Error sending message to client {client_id}: {e}")

        return False

    def broadcast(
        self,
        message_type: str,
        data: Dict[str, Any],
        filter_func: Optional[Callable[[WebSocketClient], bool]] = None,
    ) -> int:
        """
        Broadcast a message to all clients, optionally filtered.

        Args:
            message_type: Type of message to send
            data: Data to include in the message
            filter_func: Optional function to filter clients

        Returns:
            Number of clients the message was sent to
        """
        count = 0
        with self._client_lock:
            for client in self.clients.values():
                if filter_func is None or filter_func(client):
                    try:
                        client.send(message_type, data)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Error broadcasting to client {client.id}: {e}")

        return count


# Singleton instance
_websocket_handler = None
_handler_lock = threading.Lock()


def get_websocket_handler() -> WebSocketEventHandler:
    """
    Get the singleton instance of the WebSocketEventHandler.

    Returns:
        WebSocketEventHandler instance
    """
    global _websocket_handler
    if _websocket_handler is None:
        with _handler_lock:
            if _websocket_handler is None:
                _websocket_handler = WebSocketEventHandler()

    return _websocket_handler
