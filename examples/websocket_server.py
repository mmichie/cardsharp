#!/usr/bin/env python3
"""
WebSocket Server Example

This script demonstrates how to create a WebSocket server that connects to
the Cardsharp engine's WebSocket event handler.
"""

import asyncio
import argparse
import json
import logging
import sys
import signal
from typing import Dict, Any, Set

try:
    # Import necessary modules
    from cardsharp.events.websocket import (
        WebSocketEventHandler,
        get_websocket_handler,
        ServerMessage,
        ClientMessage,
    )
except ImportError:
    print("ERROR: CardSharp package not found or incompletely installed.")
    print("Please ensure CardSharp is installed properly with: poetry install")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("websocket_server")


class WebSocketServer:
    """
    WebSocket server for the Cardsharp engine.

    This class provides a WebSocket server that connects to the Cardsharp
    engine's WebSocket event handler.
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        """
        Initialize the WebSocket server.

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        self.host = host
        self.port = port
        self.ws_handler = None
        self.clients: Dict[str, Any] = {}
        self.running = False

    async def start(self):
        """Start the WebSocket server."""
        try:
            import websockets
        except ImportError:
            logger.error(
                "websockets package not found. Please install it with: pip install websockets"
            )
            sys.exit(1)

        # Get the WebSocket handler
        self.ws_handler = get_websocket_handler()

        # Start the WebSocket handler
        await self.ws_handler.start()
        logger.info("WebSocket handler started")

        # Start the WebSocket server
        self.server = await websockets.serve(self.handle_client, self.host, self.port)
        self.running = True
        logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")

        # Register signal handlers
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(
            signal.SIGINT, lambda: asyncio.create_task(self.shutdown())
        )
        loop.add_signal_handler(
            signal.SIGTERM, lambda: asyncio.create_task(self.shutdown())
        )

        # Keep the server running
        await asyncio.Future()

    async def shutdown(self):
        """Shutdown the WebSocket server."""
        if not self.running:
            return

        logger.info("Shutting down WebSocket server...")
        self.running = False

        # Close all client connections
        for client_id in list(self.clients.keys()):
            await self.disconnect_client(client_id)

        # Stop the WebSocket handler
        if self.ws_handler:
            await self.ws_handler.stop()

        # Close the server
        self.server.close()
        await self.server.wait_closed()

        # Stop the event loop
        loop = asyncio.get_event_loop()
        loop.stop()

    async def handle_client(self, websocket, path):
        """
        Handle a WebSocket client connection.

        Args:
            websocket: WebSocket connection
            path: Request path
        """
        client_id = None

        try:
            # Wait for the client to send a message
            while self.running:
                # Receive message
                message = await websocket.recv()
                data = json.loads(message)

                # Handle message
                message_type = data.get("type", "")
                message_data = data.get("data", {})

                if message_type == ClientMessage.CONNECT:
                    # Client is connecting - get/create client ID
                    client_id = message_data.get("client_id", None)
                    client_id = await self.connect_client(client_id, websocket)

                elif client_id:
                    # Forward message to the WebSocket handler
                    response = await self.ws_handler.handle_client_message(
                        client_id, data
                    )

                    # Send response back to the client
                    await websocket.send(json.dumps(response))
                else:
                    # Client must connect first
                    await websocket.send(
                        json.dumps(
                            {
                                "type": ServerMessage.ERROR,
                                "data": {"message": "Not connected"},
                            }
                        )
                    )

        except asyncio.CancelledError:
            # Task was cancelled, just exit
            pass
        except Exception as e:
            logger.warning(f"Error handling client: {e}")
        finally:
            # Disconnect the client
            if client_id:
                await self.disconnect_client(client_id)

    async def connect_client(self, client_id: str, websocket) -> str:
        """
        Connect a new client.

        Args:
            client_id: Optional client ID
            websocket: WebSocket connection

        Returns:
            The client ID
        """
        # Connect the client to the WebSocket handler
        client_id = await self.ws_handler.connect_client(
            client_id, self.create_send_callback(websocket)
        )

        # Store the client
        self.clients[client_id] = {
            "websocket": websocket,
            "connected_at": asyncio.get_event_loop().time(),
        }

        logger.info(f"Client {client_id} connected")
        return client_id

    async def disconnect_client(self, client_id: str):
        """
        Disconnect a client.

        Args:
            client_id: Client ID to disconnect
        """
        # Remove from clients
        client = self.clients.pop(client_id, None)

        # Disconnect from the WebSocket handler
        await self.ws_handler.disconnect_client(client_id)

        # Close the WebSocket connection
        if client and client.get("websocket"):
            try:
                await client["websocket"].close()
            except Exception:
                pass

        logger.info(f"Client {client_id} disconnected")

    def create_send_callback(self, websocket):
        """
        Create a send callback for a WebSocket connection.

        Args:
            websocket: WebSocket connection

        Returns:
            Callback function
        """

        def send_callback(message: Dict[str, Any]):
            """Send a message to the WebSocket client."""
            # Create a task to send the message
            asyncio.create_task(self._send_message(websocket, message))

        return send_callback

    async def _send_message(self, websocket, message: Dict[str, Any]):
        """
        Send a message to a WebSocket client.

        Args:
            websocket: WebSocket connection
            message: Message to send
        """
        try:
            await websocket.send(json.dumps(message))
        except Exception as e:
            logger.warning(f"Error sending message: {e}")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="WebSocket server for Cardsharp")
    parser.add_argument("--host", type=str, default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind to")

    args = parser.parse_args()

    # Create server
    server = WebSocketServer(args.host, args.port)

    # Run server
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
