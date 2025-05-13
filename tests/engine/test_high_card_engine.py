"""
Tests for the HighCardEngine class.

This module contains tests for the HighCardEngine class
to ensure it provides the expected behavior and correctly
implements the CardsharpEngine interface.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch
import time

from cardsharp.engine.high_card import HighCardEngine
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType
from cardsharp.high_card.state import GameState, GameStage


class TestHighCardEngine(unittest.TestCase):
    """Tests for the HighCardEngine class."""

    def setUp(self):
        """Set up the test case."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Create a dummy adapter
        self.adapter = DummyAdapter()

        # Create a config for the engine
        self.config = {
            "shuffle_threshold": 5,
        }

        # Create a high card engine
        self.engine = HighCardEngine(self.adapter, self.config)

    def tearDown(self):
        """Tear down the test case."""
        self.loop.close()

    def test_initialization(self):
        """Test that the engine initializes correctly."""
        self.assertIsNotNone(self.engine)
        self.assertEqual(self.engine.adapter, self.adapter)
        self.assertEqual(self.engine.config, self.config)
        self.assertIsNotNone(self.engine.event_bus)
        self.assertIsNotNone(self.engine.state)
        self.assertEqual(self.engine.shuffle_threshold, 5)

    @patch.object(EventBus, "emit")
    def test_initialize(self, mock_emit):
        """Test that initialize sets up the engine correctly."""

        async def run_test():
            await self.engine.initialize()

            # Check that deck was initialized
            self.assertIsNotNone(self.engine.deck)
            self.assertEqual(self.engine.deck.size, 52)

            # Check that ENGINE_INIT event was emitted
            mock_emit.assert_called()
            args = mock_emit.call_args[0]
            self.assertEqual(args[0], EngineEventType.ENGINE_INIT)

        self.loop.run_until_complete(run_test())

    @patch.object(EventBus, "emit")
    def test_shutdown(self, mock_emit):
        """Test that shutdown emits the expected event."""

        async def run_test():
            await self.engine.shutdown()

            # Check that ENGINE_SHUTDOWN event was emitted
            mock_emit.assert_called()
            args = mock_emit.call_args[0]
            self.assertEqual(args[0], EngineEventType.ENGINE_SHUTDOWN)

        self.loop.run_until_complete(run_test())

    @patch.object(EventBus, "emit")
    def test_start_game(self, mock_emit):
        """Test that start_game sets up a new game correctly."""

        async def run_test():
            await self.engine.start_game()

            # Check that a new state was created
            self.assertIsNotNone(self.engine.state)

            # Check that GAME_CREATED and GAME_STARTED events were emitted
            calls = [args[0] for args, _ in mock_emit.call_args_list]
            self.assertIn(EngineEventType.GAME_CREATED, calls)
            self.assertIn(EngineEventType.GAME_STARTED, calls)

        self.loop.run_until_complete(run_test())

    @patch.object(EventBus, "emit")
    def test_add_player(self, mock_emit):
        """Test that add_player adds a player correctly."""

        async def run_test():
            # Start a game
            await self.engine.start_game()

            # Add a player
            player_id = await self.engine.add_player("Test Player")

            # Check that the player was added
            self.assertEqual(len(self.engine.state.players), 1)
            self.assertEqual(self.engine.state.players[0].name, "Test Player")
            self.assertEqual(self.engine.state.players[0].id, player_id)

        self.loop.run_until_complete(run_test())

    @patch.object(DummyAdapter, "render_game_state")
    def test_render_state(self, mock_render):
        """Test that render_state calls the adapter's render_game_state method."""

        async def run_test():
            # Render the state
            await self.engine.render_state()

            # Check that render_game_state was called
            mock_render.assert_called_once()

        self.loop.run_until_complete(run_test())

    @patch.object(EventBus, "emit")
    def test_play_round(self, mock_emit):
        """Test that play_round plays a round correctly."""

        async def run_test():
            # Start a game
            await self.engine.start_game()

            # Add at least 2 players
            player1_id = await self.engine.add_player("Player 1")
            player2_id = await self.engine.add_player("Player 2")

            # Mock the render_state method to avoid UI interactions
            self.engine.render_state = MagicMock()

            # Play a round
            result = await self.engine.play_round()

            # Check that the result is a dictionary
            self.assertIsInstance(result, dict)

            # Check that the state was updated
            self.assertEqual(self.engine.state.stage, GameStage.COMPARING_CARDS)

            # Check that each player has a card
            for player in self.engine.state.players:
                self.assertIsNotNone(player.card)

            # Check that a winner was determined
            self.assertIsNotNone(self.engine.state.winner)

        self.loop.run_until_complete(run_test())

    def test_deal_card(self):
        """Test that _deal_card returns a card from the deck."""
        # Initialize the deck
        self.engine.deck.reset()
        self.engine.deck.shuffle()

        # Get the initial deck size
        initial_size = self.engine.deck.size

        # Deal a card
        card = self.engine._deal_card()

        # Check that a card was returned
        self.assertIsNotNone(card)

        # Check that the deck size was decremented
        self.assertEqual(self.engine.deck.size, initial_size - 1)


if __name__ == "__main__":
    unittest.main()
