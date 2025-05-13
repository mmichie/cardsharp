"""
Tests for the base CardsharpEngine class.

This module contains tests for the CardsharpEngine base class
to ensure it provides the expected interface and behavior.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch
import time

from cardsharp.engine.base import CardsharpEngine
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType


class MockEngine(CardsharpEngine):
    """Mock implementation of CardsharpEngine for testing."""

    async def initialize(self):
        """Initialize the engine."""
        await super().initialize()

    async def shutdown(self):
        """Shut down the engine."""
        await super().shutdown()

    async def start_game(self):
        """Start a new game."""
        self.event_bus.emit(
            EngineEventType.GAME_CREATED,
            {"game_id": "test_game", "timestamp": time.time()},
        )

    async def add_player(self, name, balance=1000.0):
        """Add a player to the game."""
        return "test_player_id"

    async def place_bet(self, player_id, amount):
        """Place a bet for a player."""
        pass

    async def execute_player_action(self, player_id, action):
        """Execute a player action."""
        pass

    async def render_state(self):
        """Render the current game state."""
        pass


class TestCardsharpEngine(unittest.TestCase):
    """Tests for the CardsharpEngine base class."""

    def setUp(self):
        """Set up the test case."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Create a dummy adapter
        self.adapter = DummyAdapter()

        # Create a mock engine
        self.engine = MockEngine(self.adapter)

    def tearDown(self):
        """Tear down the test case."""
        self.loop.close()

    def test_initialization(self):
        """Test that the engine initializes correctly."""
        self.assertIsNotNone(self.engine)
        self.assertEqual(self.engine.adapter, self.adapter)
        self.assertEqual(self.engine.config, {})
        self.assertIsNotNone(self.engine.event_bus)

    def test_config(self):
        """Test that the engine uses the provided config."""
        config = {"test_key": "test_value"}
        engine = MockEngine(self.adapter, config)
        self.assertEqual(engine.config, config)

    @patch.object(DummyAdapter, "initialize")
    def test_initialize(self, mock_initialize):
        """Test that initialize calls the adapter's initialize method."""

        async def run_test():
            await self.engine.initialize()
            mock_initialize.assert_called_once()

        self.loop.run_until_complete(run_test())

    @patch.object(DummyAdapter, "shutdown")
    def test_shutdown(self, mock_shutdown):
        """Test that shutdown calls the adapter's shutdown method."""

        async def run_test():
            await self.engine.shutdown()
            mock_shutdown.assert_called_once()

        self.loop.run_until_complete(run_test())

    @patch.object(EventBus, "emit")
    def test_start_game(self, mock_emit):
        """Test that start_game emits the expected event."""

        async def run_test():
            await self.engine.start_game()

            # Check that emit was called with the correct event type
            mock_emit.assert_called()
            args = mock_emit.call_args[0]
            self.assertEqual(args[0], EngineEventType.GAME_CREATED)

        self.loop.run_until_complete(run_test())

    def test_abstract_methods(self):
        """Test that the abstract methods are implemented by the mock engine."""

        async def run_test():
            # These should not raise NotImplementedError
            await self.engine.initialize()
            await self.engine.shutdown()
            await self.engine.start_game()
            await self.engine.add_player("Test Player")
            await self.engine.place_bet("test_player_id", 10.0)
            await self.engine.execute_player_action("test_player_id", "test_action")
            await self.engine.render_state()

        self.loop.run_until_complete(run_test())


if __name__ == "__main__":
    unittest.main()
