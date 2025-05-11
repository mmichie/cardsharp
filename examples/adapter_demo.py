#!/usr/bin/env python3
"""
Example demonstrating the use of the new adapter system.

This script shows how to use the CLIAdapter to create a simple
command-line interactive game interface.
"""

import asyncio

# Check if cardsharp is installed properly
try:
    from cardsharp.adapters import CLIAdapter, DummyAdapter
    from cardsharp.events import EventBus, EngineEventType
except ImportError:
    print("ERROR: CardSharp package not found or incompletely installed.")
    print("Please ensure CardSharp is installed properly with: poetry install")
    import sys

    sys.exit(1)


class MockAction:
    """
    Mock Action class for demonstration purposes.
    In a real application, you would use the actual Action enum.
    """

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


# Create mock action constants
HIT = MockAction("HIT")
STAND = MockAction("STAND")
DOUBLE = MockAction("DOUBLE")
SPLIT = MockAction("SPLIT")


async def main():
    # Get the global event bus
    event_bus = EventBus.get_instance()

    # Create a CLI adapter
    adapter = CLIAdapter()

    # Initialize the adapter
    await adapter.initialize()

    print("Welcome to Cardsharp CLI Demo!")
    print("This demo shows how to use the CLIAdapter to interact with a user.\n")

    # Simulate game creation
    game_id = "game_demo"
    event_bus.emit(
        EngineEventType.GAME_CREATED,
        {"game_id": game_id, "timestamp": asyncio.get_event_loop().time()},
    )

    # Notify about game creation
    await adapter.notify_game_event(EngineEventType.GAME_CREATED, {"game_id": game_id})

    # Render initial game state
    initial_state = {
        "dealer": {"hand": ["A♠"], "value": 11, "hide_second_card": True},
        "players": [
            {
                "name": "Player 1",
                "hands": [{"cards": ["10♥", "J♦"], "value": 20, "bet": 10}],
                "balance": 100,
            }
        ],
    }

    await adapter.render_game_state(initial_state)

    # Request player action
    try:
        action = await adapter.request_player_action(
            player_id="player1",
            player_name="Player 1",
            valid_actions=[HIT, STAND, DOUBLE],
            timeout_seconds=30.0,
        )

        # Notify about player action
        await adapter.notify_game_event(
            EngineEventType.PLAYER_ACTION,
            {
                "player_id": "player1",
                "player_name": "Player 1",
                "action_type": action.name,
                "timestamp": asyncio.get_event_loop().time(),
            },
        )

        # Update the game state based on the action
        if action == HIT:
            # Player chose to hit
            await adapter.notify_game_event(
                "CARD_DEALT",
                {"card": "2♥", "player_name": "Player 1", "is_dealer": False},
            )

            # Update game state
            updated_state = {
                "dealer": {"hand": ["A♠"], "value": 11, "hide_second_card": True},
                "players": [
                    {
                        "name": "Player 1",
                        "hands": [
                            {"cards": ["10♥", "J♦", "2♥"], "value": 22, "bet": 10}
                        ],
                        "balance": 100,
                    }
                ],
            }

            await adapter.render_game_state(updated_state)

            # Player busted
            await adapter.notify_game_event(
                "HAND_RESULT",
                {"player_name": "Player 1", "result": "lose", "is_busted": True},
            )

        elif action == STAND:
            # Player chose to stand
            # Reveal dealer's hand
            await adapter.notify_game_event(
                "CARD_REVEALED", {"card": "K♥", "is_dealer": True}
            )

            # Update game state
            updated_state = {
                "dealer": {
                    "hand": ["A♠", "K♥"],
                    "value": 21,
                    "hide_second_card": False,
                },
                "players": [
                    {
                        "name": "Player 1",
                        "hands": [{"cards": ["10♥", "J♦"], "value": 20, "bet": 10}],
                        "balance": 100,
                    }
                ],
            }

            await adapter.render_game_state(updated_state)

            # Player loses to dealer
            await adapter.notify_game_event(
                "HAND_RESULT", {"player_name": "Player 1", "result": "lose"}
            )

        elif action == DOUBLE:
            # Player chose to double
            await adapter.notify_game_event(
                "CARD_DEALT",
                {"card": "A♦", "player_name": "Player 1", "is_dealer": False},
            )

            # Update game state
            updated_state = {
                "dealer": {
                    "hand": ["A♠", "K♥"],
                    "value": 21,
                    "hide_second_card": False,
                },
                "players": [
                    {
                        "name": "Player 1",
                        "hands": [
                            {
                                "cards": ["10♥", "J♦", "A♦"],
                                "value": 21,
                                "bet": 20,  # Doubled
                            }
                        ],
                        "balance": 80,  # Reduced by the doubled bet
                    }
                ],
            }

            await adapter.render_game_state(updated_state)

            # Player pushes with dealer
            await adapter.notify_game_event(
                "HAND_RESULT", {"player_name": "Player 1", "result": "push"}
            )

    except asyncio.TimeoutError:
        # Handle player timeout
        default_action = await adapter.handle_timeout("player1", "Player 1")
        await adapter.notify_game_event(
            EngineEventType.PLAYER_TIMEOUT,
            {
                "player_id": "player1",
                "player_name": "Player 1",
                "default_action": default_action.name,
            },
        )

    # End game
    await adapter.notify_game_event(EngineEventType.GAME_ENDED, {"game_id": game_id})

    print("\nDemo completed! Thank you for trying the Cardsharp CLI Adapter.")

    # Shutdown the adapter
    await adapter.shutdown()


async def dummy_adapter_demo():
    """
    Demonstrates how to use the DummyAdapter for testing and simulation.
    """
    # Create a dummy adapter with predefined actions
    adapter = DummyAdapter(auto_actions={"player1": [HIT, STAND]}, verbose=True)

    # Initialize
    await adapter.initialize()

    # Simulate the same flow as above, but with automatic responses
    # Render game state
    await adapter.render_game_state(
        {
            "dealer": {"hand": ["A♠"], "value": 11, "hide_second_card": True},
            "players": [
                {
                    "name": "Player 1",
                    "hands": [{"cards": ["10♥", "J♦"], "value": 20, "bet": 10}],
                    "balance": 100,
                }
            ],
        }
    )

    # Request action - will automatically return HIT (the first predefined action)
    action = await adapter.request_player_action(
        "player1", "Player 1", [HIT, STAND, DOUBLE]
    )

    # The dummy adapter should have returned HIT
    assert action == HIT

    # Request action again - will return STAND (the second predefined action)
    action = await adapter.request_player_action(
        "player1", "Player 1", [HIT, STAND, DOUBLE]
    )

    # The dummy adapter should have returned STAND
    assert action == STAND

    # After all predefined actions are used, it defaults to STAND
    action = await adapter.request_player_action(
        "player1", "Player 1", [HIT, STAND, DOUBLE]
    )

    # Should return a default action (STAND if available)
    assert action == STAND

    # Notify about various events to collect them
    events = [
        (EngineEventType.GAME_CREATED, {"game_id": "test_game"}),
        (EngineEventType.PLAYER_ACTION, {"player_name": "Player 1", "action": "HIT"}),
        (EngineEventType.CARD_DEALT, {"card": "2♥", "player_name": "Player 1"}),
        (EngineEventType.HAND_RESULT, {"player_name": "Player 1", "result": "win"}),
    ]

    for event_type, data in events:
        await adapter.notify_game_event(event_type, data)

    # Show the collected events
    print("\nDummy Adapter Events:")
    for event_type, data in adapter.events:
        print(f"- {event_type}: {data}")

    # Shutdown
    await adapter.shutdown()
    print("\nDummy adapter demo completed successfully!")


if __name__ == "__main__":
    # Run both demos
    asyncio.run(main())
    print("\n\n=== DUMMY ADAPTER DEMO ===")
    asyncio.run(dummy_adapter_demo())
