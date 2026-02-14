# Web Adapter for CardSharp

The Web Adapter allows the CardSharp engine to be used with web-based interfaces. This documentation covers how to use the web adapter with Streamlit to create interactive card games.

## Overview

The web adapter is designed to bridge the gap between:
- The asynchronous nature of the CardSharp engine
- The synchronous, request-response nature of web frameworks

It achieves this by using queues to pass information between the engine and web interface.

## Components

### WebAdapter

The `WebAdapter` class implements the `PlatformAdapter` interface and provides:

- Methods for sending game state to the web interface
- Handling player actions
- Managing game events
- Thread-safe queues for communication

### Streamlit App

The example Streamlit app shows how to use the web adapter to create a fully functional blackjack game:

- Real-time game state updates
- Interactive betting
- Player action buttons
- Game event display

## Usage

### Running the Example

To run the example Streamlit app:

```bash
uv run streamlit run examples/streamlit_blackjack.py
```

### Creating Custom Web Interfaces

To create your own web interface with the WebAdapter:

1. Create an instance of the WebAdapter
2. Initialize the CardSharp engine with the adapter
3. Run the engine in a separate thread or process
4. Use the adapter's synchronous methods to interact with the engine from your web framework

Example:

```python
from cardsharp.adapters import WebAdapter
from cardsharp.engine import BlackjackEngine

# Create adapter and engine
adapter = WebAdapter()
engine = BlackjackEngine(adapter, config)

# Initialize in a separate thread
def run_engine_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def initialize():
        await adapter.initialize()
        await engine.initialize()
        await engine.start_game()
        
    loop.run_until_complete(initialize())

# Start the thread
import threading
engine_thread = threading.Thread(target=run_engine_thread)
engine_thread.start()

# In your web app, use the adapter's sync methods:
current_state = adapter.get_current_state()
# Submit a player action
adapter.submit_action("HIT")
```

## Architecture

The web adapter uses:

1. **Asynchronous Queues** for engine-side communication
2. **Thread-safe Queues** for web-side communication 
3. **Monitoring Tasks** to transfer items between them

This architecture allows the engine to run asynchronously while the web interface can interact with it synchronously, which is crucial for most web frameworks.

## Customizing

You can extend the `WebAdapter` class to add additional features:

- Support for multiple games
- User authentication
- Game history tracking
- Multiplayer functionality

## Limitations

- The current implementation is designed for single-session use
- For production applications, you would need to add session management
- The adapter assumes a single game instance per adapter