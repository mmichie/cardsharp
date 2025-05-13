"""
Tests for the UI integration with the engine pattern.

This module contains tests to verify that the UI components
work correctly with the engine pattern.
"""

import unittest
import asyncio
import time
from unittest.mock import MagicMock, patch

from cardsharp.api import BlackjackGame
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType


class TestUIIntegration(unittest.TestCase):
    """Tests for the UI integration with the engine pattern."""

    def setUp(self):
        """Set up the test case."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Create a dummy adapter
        self.adapter = DummyAdapter()

        # Create a mock function to receive events
        self.received_events = []

        # Get the event bus
        self.event_bus = EventBus.get_instance()

    def tearDown(self):
        """Tear down the test case."""
        self.loop.close()

    def test_game_initialization(self):
        """Test that the game can be initialized."""

        async def run_test():
            # Create a game instance
            game = BlackjackGame(adapter=self.adapter)

            # Initialize the game
            await game.initialize()

            # Verify that the game was initialized
            self.assertIsNotNone(game.engine)
            self.assertEqual(game.adapter, self.adapter)

            # Start the game
            await game.start_game()

            # Get the initial state
            state = await game.get_state()

            # Verify the initial state
            self.assertEqual(state.stage.name, "WAITING_FOR_PLAYERS")

            # Shutdown the game
            await game.shutdown()

        # Run the test
        self.loop.run_until_complete(run_test())

    def test_player_management(self):
        """Test player management with the game."""

        async def run_test():
            # Create a game instance
            game = BlackjackGame(adapter=self.adapter)

            # Initialize the game
            await game.initialize()
            await game.start_game()

            # Add a player
            player_id = await game.add_player("Alice", 1000.0)

            # Verify the player was added
            state = await game.get_state()
            self.assertEqual(len(state.players), 1)
            self.assertEqual(state.players[0].name, "Alice")
            self.assertEqual(state.players[0].balance, 1000.0)

            # Remove the player
            result = await game.remove_player(player_id)

            # Verify the player was removed
            self.assertTrue(result)
            state = await game.get_state()
            self.assertEqual(len(state.players), 0)

            # Shutdown the game
            await game.shutdown()

        # Run the test
        self.loop.run_until_complete(run_test())

    def test_game_flow(self):
        """Test the game flow with the engine pattern."""

        async def run_test():
            # Listen for events
            unsubscribe_funcs = []

            # Create event handlers
            handlers = {
                EngineEventType.GAME_STARTED: MagicMock(),
                EngineEventType.PLAYER_JOINED: MagicMock(),
                EngineEventType.ROUND_STARTED: MagicMock(),
                EngineEventType.ROUND_ENDED: MagicMock(),
            }

            # Register event handlers
            for event_type, handler in handlers.items():
                unsubscribe = self.event_bus.on(event_type, handler)
                unsubscribe_funcs.append(unsubscribe)

            try:
                # Create a game instance with auto play
                game = BlackjackGame(adapter=self.adapter, auto_play=True)

                # Initialize the game
                await game.initialize()
                await game.start_game()

                # Verify GAME_STARTED event was emitted
                handlers[EngineEventType.GAME_STARTED].assert_called()

                # Add players
                player1 = await game.add_player("Alice", 1000.0)
                player2 = await game.add_player("Bob", 1000.0)

                # Verify PLAYER_JOINED events were emitted
                # Note: The event might be emitted multiple times due to internal operations
                self.assertTrue(handlers[EngineEventType.PLAYER_JOINED].call_count >= 2)

                # Play a round
                result = await game.auto_play_round(default_bet=10.0)

                # Verify ROUND_STARTED and ROUND_ENDED events were emitted
                handlers[EngineEventType.ROUND_STARTED].assert_called()
                handlers[EngineEventType.ROUND_ENDED].assert_called()

                # Verify the result
                self.assertIsNotNone(result)
                self.assertIn("players", result)
                self.assertEqual(len(result["players"]), 2)

                # Shutdown the game
                await game.shutdown()
            finally:
                # Unsubscribe event handlers
                for unsubscribe in unsubscribe_funcs:
                    unsubscribe()

        # Run the test
        self.loop.run_until_complete(run_test())


if __name__ == "__main__":
    unittest.main()
