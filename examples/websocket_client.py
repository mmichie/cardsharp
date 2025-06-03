#!/usr/bin/env python3
"""
WebSocket Client Example

This script demonstrates how to create a WebSocket client that connects to
the Cardsharp engine's WebSocket server. It provides a simple command-line
interface for playing blackjack.
"""

import asyncio
import argparse
import json
import sys
import uuid
import time

try:
    # Import necessary modules
    from cardsharp.events.websocket import (
        ClientMessage,
        ServerMessage,
    )
    from cardsharp.events import EngineEventType
    from cardsharp.blackjack.action import Action
except ImportError:
    print("ERROR: CardSharp package not found or incompletely installed.")
    print("Please ensure CardSharp is installed properly with: poetry install")
    sys.exit(1)


class WebSocketClient:
    """
    Simple WebSocket client for interacting with the Cardsharp engine.

    This class provides a command-line interface for playing blackjack via
    the WebSocket interface.
    """

    def __init__(self, server_url: str = "ws://localhost:8765"):
        """
        Initialize the WebSocket client.

        Args:
            server_url: URL of the WebSocket server
        """
        self.server_url = server_url
        self.client_id = str(uuid.uuid4())
        self.connected = False
        self.pending_action_request = None
        self.dealer_hand = []
        self.player_hands = []
        self.balance = 1000.0
        self.betting_required = False

        # Queue for user input
        self.input_queue = asyncio.Queue()

        # Define valid actions
        self.actions = {
            "1": "HIT",
            "2": "STAND",
            "3": "DOUBLE",
            "4": "SPLIT",
            "5": "SURRENDER",
            "h": "HIT",
            "s": "STAND",
            "d": "DOUBLE",
            "p": "SPLIT",
            "r": "SURRENDER",
            "hit": "HIT",
            "stand": "STAND",
            "double": "DOUBLE",
            "split": "SPLIT",
            "surrender": "SURRENDER",
        }

    async def connect(self):
        """Connect to the WebSocket server."""
        try:
            import websockets
        except ImportError:
            print("ERROR: websockets package not found.")
            print("Please install it with: pip install websockets")
            sys.exit(1)

        print(f"Connecting to {self.server_url}...")

        try:
            self.ws = await websockets.connect(self.server_url)

            # Send connect message
            await self.send_message(
                ClientMessage.CONNECT, {"client_id": self.client_id}
            )

            # Wait for connected message
            response = await self.ws.recv()
            data = json.loads(response)

            if data.get("type") == ServerMessage.CONNECTED:
                self.connected = True
                print(f"Connected to server with client ID: {self.client_id}")

                # Subscribe to all events
                await self.send_message(
                    ClientMessage.SUBSCRIBE,
                    {"event_types": ["*"]},  # Subscribe to all events
                )

                return True
            else:
                print(f"Failed to connect: {data}")
                return False

        except Exception as e:
            print(f"Error connecting to server: {e}")
            return False

    async def disconnect(self):
        """Disconnect from the WebSocket server."""
        if self.connected:
            try:
                # Send disconnect message
                await self.send_message(
                    ClientMessage.DISCONNECT, {"client_id": self.client_id}
                )

                # Close the WebSocket connection
                await self.ws.close()
                print("Disconnected from server")
            except Exception as e:
                print(f"Error disconnecting: {e}")
            finally:
                self.connected = False

    async def send_message(self, message_type: str, data: dict):
        """
        Send a message to the server.

        Args:
            message_type: Type of message to send
            data: Data to include in the message
        """
        if not self.connected:
            print("Not connected to server")
            return

        message = {"type": message_type, "data": data, "timestamp": time.time()}

        try:
            await self.ws.send(json.dumps(message))
        except Exception as e:
            print(f"Error sending message: {e}")

    async def handle_message(self, message: dict):
        """
        Handle a message from the server.

        Args:
            message: The message to handle
        """
        message_type = message.get("type", "")
        message_data = message.get("data", {})

        if message_type == ServerMessage.EVENT:
            # Event message
            event_type = message_data.get("event_type", "")
            event_data = message_data.get("data", {})

            await self.handle_event(event_type, event_data)

        elif message_type == ServerMessage.ACTION_REQUEST:
            # Action request
            await self.handle_action_request(message_data)

        elif message_type == ServerMessage.CONNECTED:
            # Connected message
            print("Connected to server")

        elif message_type == ServerMessage.DISCONNECTED:
            # Disconnected message
            print("Disconnected from server")
            self.connected = False

        elif message_type == ServerMessage.ERROR:
            # Error message
            error_message = message_data.get("message", "Unknown error")
            print(f"Error from server: {error_message}")

    async def handle_event(self, event_type: str, event_data: dict):
        """
        Handle an event from the server.

        Args:
            event_type: Type of event
            event_data: Event data
        """
        # Handle different event types
        if event_type == EngineEventType.CARD_DEALT.name:
            # Card dealt event
            card = event_data.get("card", "?")
            is_dealer = event_data.get("is_dealer", False)
            is_hole_card = event_data.get("is_hole_card", False)

            if is_dealer:
                if is_hole_card:
                    print(f"Dealer gets a hole card")
                else:
                    self.dealer_hand.append(card)
                    print(f"Dealer gets {card}")
            else:
                player_name = event_data.get("player_name", "Player")
                print(f"{player_name} gets {card}")

        elif event_type == EngineEventType.HAND_RESULT.name:
            # Hand result event
            player_name = event_data.get("player_name", "Player")
            result = event_data.get("result", "unknown")
            payout = event_data.get("payout", 0)

            if result == "win":
                print(f"✅ {player_name} wins ${payout:.2f}!")
            elif result == "lose":
                print(f"❌ {player_name} loses")
            elif result == "push":
                print(f"🟰 {player_name} pushes (tie)")
            elif result == "surrender":
                print(f"🏳️ {player_name} surrendered")

        elif event_type == EngineEventType.BANKROLL_UPDATED.name:
            # Bankroll updated event
            player_name = event_data.get("player_name", "Player")
            balance = event_data.get("balance", 0)
            print(f"💰 {player_name}'s balance: ${balance:.2f}")
            self.balance = balance

        elif event_type == EngineEventType.PLAYER_ACTION.name:
            # Player action event
            player_name = event_data.get("player_name", "Player")
            action = event_data.get("action", "UNKNOWN")
            print(f"{player_name} {action.lower()}s")

        elif event_type == EngineEventType.DEALER_ACTION.name:
            # Dealer action event
            action = event_data.get("action", "UNKNOWN")
            print(f"Dealer {action.lower()}s")

        elif event_type == EngineEventType.UI_UPDATE_NEEDED.name:
            # UI update needed event
            # This is a high-level event that indicates the UI should be updated
            state = event_data.get("state", {})
            # We'll use this to update our local state
            # ...

        elif event_type == EngineEventType.ROUND_STARTED.name:
            # Round started event
            round_number = event_data.get("round_number", 0)
            print(f"\n{'=' * 20} ROUND {round_number} {'=' * 20}\n")
            self.betting_required = True

    async def handle_action_request(self, request_data: dict):
        """
        Handle an action request from the server.

        Args:
            request_data: The action request data
        """
        request_id = request_data.get("request_id", "")
        player_id = request_data.get("player_id", "")
        player_name = request_data.get("player_name", "Player")
        valid_actions = request_data.get("valid_actions", [])

        # Store the request for later
        self.pending_action_request = {
            "request_id": request_id,
            "player_id": player_id,
            "player_name": player_name,
            "valid_actions": valid_actions,
            "timestamp": time.time(),
        }

        # Prompt the user for an action
        print(f"\n{player_name}'s turn. Valid actions:")

        # Map numbers to actions for easier input
        action_map = {}
        for i, action in enumerate(valid_actions):
            action_map[str(i + 1)] = action
            print(f"{i+1}: {action}")

        # Wait for user input
        self.input_queue.put_nowait("action_needed")

    async def process_input(self):
        """Process user input."""
        # Check if we need to place a bet
        if self.betting_required:
            min_bet = 5.0
            max_bet = min(1000.0, self.balance)

            print(f"\nYour balance: ${self.balance:.2f}")
            print(f"Enter your bet (${min_bet:.2f}-${max_bet:.2f}):")

            bet_str = await self.get_input()
            try:
                bet = float(bet_str)
                if min_bet <= bet <= max_bet:
                    # Send the bet
                    await self.send_message(
                        ClientMessage.ACTION,
                        {"action": "place_bet", "data": {"amount": bet}},
                    )
                    self.betting_required = False
                else:
                    print(f"Bet must be between ${min_bet:.2f} and ${max_bet:.2f}")
            except ValueError:
                print("Please enter a valid number")

        # Check if we need to respond to an action request
        elif self.pending_action_request:
            valid_actions = self.pending_action_request.get("valid_actions", [])
            request_id = self.pending_action_request.get("request_id", "")

            action_input = await self.get_input()
            action_input = action_input.strip().lower()

            # Map input to action
            if action_input in self.actions:
                action_name = self.actions[action_input]

                # Check if the action is valid
                if action_name in valid_actions:
                    # Send the action
                    await self.send_message(
                        ClientMessage.ACTION,
                        {
                            "action": "player_action",
                            "data": {"action": action_name, "request_id": request_id},
                        },
                    )
                    self.pending_action_request = None
                else:
                    print(f"Invalid action. Valid actions: {', '.join(valid_actions)}")
            else:
                print(f"Invalid input. Please enter a number or action name.")

    async def get_input(self):
        """Get user input asynchronously."""
        # Create a future to store the input
        future = asyncio.Future()

        def stdin_callback():
            user_input = sys.stdin.readline().strip()
            asyncio.run_coroutine_threadsafe(
                self.input_queue.put(user_input), asyncio.get_event_loop()
            )

        # Add reader for stdin
        loop = asyncio.get_event_loop()
        loop.add_reader(sys.stdin.fileno(), stdin_callback)

        try:
            # Wait for input to be available
            user_input = await self.input_queue.get()

            # If this is a signal, get the next input
            if user_input == "action_needed":
                user_input = await self.input_queue.get()

            return user_input
        finally:
            # Remove the reader
            loop.remove_reader(sys.stdin.fileno())

    async def run(self):
        """Run the WebSocket client."""
        # Connect to the server
        if not await self.connect():
            return

        try:
            # Start the receive loop
            receive_task = asyncio.create_task(self.receive_loop())

            # Start the heartbeat loop
            heartbeat_task = asyncio.create_task(self.heartbeat_loop())

            # Wait for Ctrl+C to exit
            print("Press Ctrl+C to exit")
            await asyncio.gather(receive_task, heartbeat_task)

        except KeyboardInterrupt:
            print("\nExiting...")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            # Disconnect from the server
            await self.disconnect()

    async def receive_loop(self):
        """Receive messages from the server."""
        try:
            while self.connected:
                # Receive message
                message = await self.ws.recv()
                data = json.loads(message)

                # Handle message
                await self.handle_message(data)

                # Check for user input if needed
                if self.pending_action_request or self.betting_required:
                    input_task = asyncio.create_task(self.process_input())
                    await input_task

        except asyncio.CancelledError:
            # Task was cancelled, just exit
            return
        except Exception as e:
            print(f"Error in receive loop: {e}")
            self.connected = False

    async def heartbeat_loop(self):
        """Send heartbeats to the server."""
        try:
            while self.connected:
                # Send heartbeat
                await self.send_message(
                    ClientMessage.HEARTBEAT, {"timestamp": time.time()}
                )

                # Wait for next heartbeat
                await asyncio.sleep(10.0)

        except asyncio.CancelledError:
            # Task was cancelled, just exit
            return
        except Exception as e:
            print(f"Error in heartbeat loop: {e}")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="WebSocket client for Cardsharp")
    parser.add_argument(
        "--url", type=str, default="ws://localhost:8765", help="WebSocket server URL"
    )

    args = parser.parse_args()

    # Create client
    client = WebSocketClient(args.url)

    # Run client
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
