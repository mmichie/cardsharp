# Cardsharp Architecture Modernization

This document outlines the plan for modernizing the Cardsharp engine architecture and the implementation of Phase 1 of this plan.

## Current Architecture Analysis

The current Cardsharp architecture has several limitations:

1. **I/O Coupling**: Game logic is tightly bound to input/output operations, making integration with asynchronous platforms difficult.
2. **Monolithic State Management**: Player state, game flow, and rule enforcement are interwoven.
3. **Synchronous Design**: The architecture assumes a synchronous execution model, which doesn't align with modern platforms that largely operate asynchronously.
4. **Limited Event Architecture**: The event recording system is primarily used for verification rather than driving game flow.

## Target Architecture

The proposed architecture addresses these limitations through:

1. **Event-Driven Core**: All state changes and actions are communicated via events.
2. **Adapter Pattern**: Platform-specific code is isolated in adapters.
3. **Immutable State**: Game state is treated as immutable, with state transitions returning new states.
4. **Asynchronous Support**: All interfaces support both synchronous and asynchronous operation.

### Key Components

#### Event System

The event system serves as the foundation for the new architecture, enabling:
- Bidirectional communication between components
- Subscription to events with prioritization
- Asynchronous event handling
- Backward compatibility with the existing verification system

#### Adapter Interface

The adapter interface provides a clean boundary between game logic and platform-specific code:
- Renders game state for specific platforms
- Handles user input based on platform capabilities
- Translates platform events into game actions

#### Immutable State Management

The state management system:
- Treats game state as immutable
- Provides pure functions for state transitions
- Separates state from behavior
- Makes testing and debugging easier

#### Platform-Agnostic API

The API layer:
- Provides a clean, consistent interface for game operations
- Abstracts away implementation details
- Supports both synchronous and asynchronous platforms

## Implementation Strategy

### Phase 1: Event System and Adapters (Completed)

**Goal**: Establish a robust event system and adapter interface as the foundation for later changes.

#### Phase 1 Components

1. **Enhanced EventEmitter**:
   - Extends the existing event recording system
   - Supports subscription-based event handling
   - Provides priority-based handling
   - Supports both synchronous and asynchronous listeners
   - Maintains backward compatibility

2. **EventBus**:
   - Global singleton event bus for application-wide events
   - Enables decoupled components to communicate

3. **Expanded Event Types**:
   - Comprehensive set of engine events covering all aspects of the game

4. **PlatformAdapter Interface**:
   - Abstract class defining the interface for platform-specific adapters
   - Methods for rendering, input/output, and notifications

5. **Initial Adapters**:
   - `CLIAdapter`: For console-based operation (backward compatibility)
   - `DummyAdapter`: For testing and simulation

### Phase 2: State Immutability (Planned)

**Goal**: Refactor state management to use immutable patterns.

1. **Immutable GameState**:
   - Create frozen dataclasses for state
   - Move mutable state out of game/player/dealer classes
   - Implement state transition functions

2. **State Transition Logic**:
   - Create pure functions for state transitions
   - Each function returns a new state without modifying the input

### Phase 3: Asynchronous API (Planned)

**Goal**: Create a clean, platform-agnostic API that supports asynchronous operation.

1. **CardsharpEngine**:
   - Core engine class that encapsulates game mechanics
   - Provides both sync and async interfaces

2. **BlackjackGame**:
   - High-level game interface
   - Uses the engine and exposes a simpler API

### Phase 4: Integration (Planned)

**Goal**: Connect all components into a cohesive system that maintains backward compatibility.

## Phase 1 Implementation Details

### Using the Event System

The enhanced event system serves as the communication layer for all components:

```python
from cardsharp.events import EventEmitter, EventBus, EngineEventType, EventPriority

# Using the global event bus (singleton)
event_bus = EventBus.get_instance()

# Subscribe to an event with normal priority
def on_card_dealt(data):
    print(f"Card dealt: {data['card']} to {data['player']}")

unsubscribe = event_bus.on(EngineEventType.CARD_DEALT, on_card_dealt)

# Subscribe to an event with high priority
def on_high_priority_card_dealt(data):
    print(f"HIGH PRIORITY: Card dealt: {data['card']}")

event_bus.on(EngineEventType.CARD_DEALT, on_high_priority_card_dealt, 
             EventPriority.HIGH)

# Subscribe to an event for a single occurrence
event_bus.once(EngineEventType.ROUND_ENDED, 
               lambda data: print(f"Round ended with result: {data['result']}"))

# Emit an event
event_bus.emit(EngineEventType.CARD_DEALT, {
    "card": "A♠",
    "player": "Player 1",
    "timestamp": time.time()
})

# Unsubscribe when no longer needed
unsubscribe()
```

### Using Platform Adapters

Platform adapters create a clean separation between core game logic and platform-specific code:

```python
from cardsharp.adapters import CLIAdapter
from cardsharp.blackjack.action import Action

# Create a CLI adapter for console interaction
adapter = CLIAdapter()

# Initialize the adapter
await adapter.initialize()

# Render game state
await adapter.render_game_state({
    "dealer": {
        "hand": ["A♠", "K♥"],
        "value": 21,
        "hide_second_card": False
    },
    "players": [
        {
            "name": "Player 1",
            "hands": [{
                "cards": ["J♠", "Q♦"],
                "value": 20,
                "bet": 10
            }],
            "balance": 100
        }
    ]
})

# Request player action
action = await adapter.request_player_action(
    player_id="player1",
    player_name="Player 1",
    valid_actions=[Action.HIT, Action.STAND]
)

# Notify about an event
await adapter.notify_game_event(
    "CARD_DEALT", 
    {"card": "A♠", "player_name": "Player 1", "is_dealer": False}
)

# Clean up
await adapter.shutdown()
```

### For Testing and Simulation

The `DummyAdapter` is useful for testing and simulation:

```python
from cardsharp.adapters import DummyAdapter
from cardsharp.blackjack.action import Action

# Create a dummy adapter with predefined actions
adapter = DummyAdapter(auto_actions={
    "player1": [Action.HIT, Action.STAND]
})

# Or with a strategy function
def basic_strategy(player_id, valid_actions):
    if Action.STAND in valid_actions:
        return Action.STAND
    return valid_actions[0]

adapter = DummyAdapter(strategy_function=basic_strategy, verbose=True)

# Use it like any other adapter
await adapter.render_game_state(game_state)
action = await adapter.request_player_action("player1", "Player 1", valid_actions)

# Analyze the results after simulation
events = adapter.get_events_by_type("CARD_DEALT")
states = adapter.rendered_states
```

## Integration with Current Codebase

The implementation is designed to be backward compatible with the current codebase:

1. **Event System Compatibility**:
   - Enhanced event emitter works with the existing verification system
   - New events can be consumed by existing components

2. **Adapter Compatibility**:
   - CLI adapter uses the existing IOInterface for I/O operations
   - Game components can be gradually migrated to use adapters

## Phase 2: Immutable State and Transition Functions (Completed)

Phase 2 has now been completed, implementing immutable state management and pure transition functions. This phase includes:

### 1. Immutable State Classes

We've created a set of immutable dataclasses that represent the game state:

- **GameState**: Overall game state container
- **PlayerState**: Individual player state
- **DealerState**: Dealer state
- **HandState**: Individual hand state

These classes are created using frozen dataclasses to ensure immutability:

```python
from cardsharp.state import GameState, PlayerState, DealerState, HandState, GameStage

# Create a new game state
game_state = GameState(
    rules={
        'blackjack_pays': 1.5,
        'deck_count': 6,
        'dealer_hit_soft_17': False
    }
)

# States cannot be modified directly - this would raise an error:
# game_state.players.append(new_player)  # Error!
```

### 2. State Transition Functions

We've implemented a `StateTransitionEngine` with pure functions for all state transitions:

```python
from cardsharp.state import StateTransitionEngine

# Add a player - returns a new state
new_state = StateTransitionEngine.add_player(
    state,
    name="Alice",
    balance=1000.0
)

# Place a bet - returns a new state
new_state = StateTransitionEngine.place_bet(
    new_state,
    player_id=player_id,
    amount=25.0
)

# Deal a card - returns a new state
new_state = StateTransitionEngine.deal_card(
    new_state,
    card=card,
    player_id=player_id
)
```

### 3. Engine Implementation

We've created a core engine implementation that uses the immutable state system:

- **CardsharpEngine**: Abstract base class for all game engines
- **BlackjackEngine**: Concrete implementation for blackjack

The engine connects the state system with the platform adapters:

```python
from cardsharp.adapters import CLIAdapter
from cardsharp.engine import BlackjackEngine

# Create an adapter and engine
adapter = CLIAdapter()
engine = BlackjackEngine(adapter)

# Initialize the engine
await engine.initialize()

# Start a game
await engine.start_game()

# Add a player
player_id = await engine.add_player("Alice", 1000.0)

# Place a bet
await engine.place_bet(player_id, 25.0)
```

## Next Steps

With Phase 2 completed, we're ready to move on to Phase 3 of the architecture modernization plan:

1. **Enhanced Async Support**:
   - Improve async functionality throughout the engine
   - Add support for event-driven flow control

2. **Platform Integration**:
   - Create more platform adapters (Web, Discord, etc.)
   - Demonstrate multi-platform capabilities

3. **Documentation and Examples**:
   - Create comprehensive guides for the new architecture
   - Provide examples for common use cases