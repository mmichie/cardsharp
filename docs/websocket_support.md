# WebSocket Support for CardSharp

The CardSharp engine now includes built-in WebSocket support for real-time communication between the engine and web clients. This document describes how to use the WebSocket features.

## Overview

WebSocket support consists of:

1. **WebSocket Event Handler**: A WebSocket-aware event handler that bridges the event system with WebSocket clients
2. **Web Adapter WebSocket Integration**: Enhanced web adapter that can communicate with clients via WebSockets
3. **Example WebSocket Server**: A standalone server for hosting WebSocket connections
4. **Example WebSocket Client**: A simple client for connecting to the WebSocket server

This architecture allows real-time bidirectional communication between the engine and web clients, which is essential for multiplayer games and responsive user interfaces.

## Components

### WebSocketEventHandler

The `WebSocketEventHandler` is a singleton class that:

- Manages WebSocket client connections
- Routes events to subscribed clients
- Handles client messages and forwards them to the event bus
- Maintains client state (subscriptions, last activity, etc.)
- Sends heartbeats to clients to detect disconnections

### Web Adapter WebSocket Integration

The `WebAdapter` class has been enhanced to:

- Optionally use WebSockets for communication
- Emit events to the event bus that get forwarded to WebSocket clients
- Receive events from WebSocket clients via the event bus
- Maintain backward compatibility with the original implementation

### Example WebSocket Server

The `websocket_server.py` example demonstrates:

- Setting up a WebSocket server with the `websockets` package
- Connecting to the WebSocket event handler
- Handling client connections and messages
- Forwarding messages between clients and the event handler

### Example WebSocket Client

The `websocket_client.py` example demonstrates:

- Connecting to the WebSocket server
- Subscribing to events
- Handling events from the server
- Sending actions to the server
- Maintaining a heartbeat connection

## Usage

### Starting the WebSocket Server

```bash
uv run python examples/websocket_server.py --host localhost --port 8765
```

### Running the WebSocket Client

```bash
uv run python examples/websocket_client.py --url ws://localhost:8765
```

### Using WebSockets with the Web Adapter

```python
from cardsharp.adapters import WebAdapter
from cardsharp.engine import BlackjackEngine

# Create adapter with WebSocket support enabled
adapter = WebAdapter(use_websockets=True)

# Create engine with the adapter
engine = BlackjackEngine(adapter)

# Initialize and start the engine
await adapter.initialize()
await engine.initialize()
await engine.start_game()
```

## Message Protocol

WebSocket communication uses a simple JSON protocol:

### Client Messages

- `connect`: Connect to the server
- `disconnect`: Disconnect from the server
- `subscribe`: Subscribe to events
- `unsubscribe`: Unsubscribe from events
- `action`: Perform an action
- `heartbeat`: Keep the connection alive

### Server Messages

- `connected`: Confirmation of connection
- `disconnected`: Notification of disconnection
- `event`: Game event
- `action_request`: Request for player action
- `error`: Error message
- `heartbeat`: Keep-alive response

Example message:

```json
{
  "type": "event",
  "data": {
    "event_type": "CARD_DEALT",
    "data": {
      "player_id": "player1",
      "player_name": "Player 1",
      "card": "A♠",
      "hand_id": "hand1",
      "timestamp": 1633123456.789
    }
  },
  "timestamp": 1633123456.789
}
```

## Extending WebSocket Support

### Custom WebSocket Clients

To create a custom WebSocket client:

1. Connect to the WebSocket server
2. Send a `connect` message with an optional client ID
3. Subscribe to events with a `subscribe` message
4. Handle messages from the server
5. Send actions in response to action requests
6. Send heartbeats periodically

### Custom WebSocket Servers

The example server can be extended to:

- Add authentication
- Support multiple games
- Add monitoring and metrics
- Implement custom message handlers
- Scale to handle more connections

## Dependencies

WebSocket support requires the `websockets` package:

```bash
pip install websockets
```

Or using Poetry:

```bash
uv add websockets
```