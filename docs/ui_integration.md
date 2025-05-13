# UI Integration with Cardsharp Engine

This document explains how to integrate user interfaces with the Cardsharp engine using the new engine pattern and API.

## Overview

The Cardsharp framework now provides a clean separation between game logic (implemented in the engine) and user interface (implemented in adapters and UIs). This separation allows different UI frameworks to be used with the same game logic.

The key components in this architecture are:

1. **Engine**: Implements the game logic and state transitions
2. **API**: Provides a high-level interface for interacting with the engine
3. **Adapters**: Handle communication between the engine and various platforms
4. **UI**: Implements the user interface

## Web UI Implementation

The main UI implementation in Cardsharp is the Streamlit-based web UI. This UI uses the WebAdapter to communicate with the engine and provides a web-based interface for playing the games.

### Architecture

The UI architecture follows this pattern:

```
User <-> Streamlit UI <-> WebAdapter <-> BlackjackGame API <-> BlackjackEngine
```

- **User**: Interacts with the Streamlit UI
- **Streamlit UI**: Renders the game state and handles user inputs
- **WebAdapter**: Bridges the gap between the UI and the engine
- **BlackjackGame API**: Provides a high-level interface to the engine
- **BlackjackEngine**: Implements the game logic

### Event Flow

The event flow in this architecture is:

1. Engine emits events via the EventBus
2. Adapter receives events from the EventBus
3. UI receives events from the adapter
4. UI updates the display based on events
5. User interacts with the UI
6. UI sends actions to the adapter
7. Adapter forwards actions to the engine
8. Engine processes actions and updates the game state
9. Engine emits new events, and the cycle continues

## Using the Modern UI

To use the modern Blackjack UI:

1. Install Streamlit: `pip install streamlit`
2. Run the example script: `python examples/modern_blackjack_ui.py`

This will start a Streamlit app that provides a web-based interface for playing Blackjack.

## Creating Custom UIs

You can create custom UIs by following these steps:

1. Choose an appropriate adapter or create a new one
2. Create a UI class that uses the adapter and the API
3. Implement the UI logic to display the game state and handle user inputs

Here's a simplified example of a custom UI:

```python
from cardsharp.api import BlackjackGame
from cardsharp.adapters import DummyAdapter

# Create an adapter
adapter = DummyAdapter()

# Create a game instance
game = BlackjackGame(adapter=adapter)

# Initialize the game
await game.initialize()
await game.start_game()

# Add a player
player_id = await game.add_player("Alice")

# Place a bet
await game.place_bet(player_id, 10.0)

# Auto-play a round
result = await game.auto_play_round()

# Display the result
print(result)

# Shutdown the game
await game.shutdown()
```

## Using WebSockets

The WebAdapter supports WebSockets for real-time communication between the engine and the UI. To use WebSockets:

1. Create a WebAdapter with WebSockets enabled: `adapter = WebAdapter(use_websockets=True)`
2. Create a WebSocket client in your UI
3. Connect to the WebSocket server
4. Subscribe to events
5. Send actions to the server

The WebSocket server runs on a separate port and provides a JSON-based API for communicating with the engine.

## Conclusion

The new UI architecture in Cardsharp provides a clean separation between game logic and user interface, allowing different UI frameworks to be used with the same game logic. The Streamlit-based web UI demonstrates how to integrate a UI with the Cardsharp engine using the new engine pattern and API.