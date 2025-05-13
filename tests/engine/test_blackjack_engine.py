"""
Tests for the BlackjackEngine class.

This module contains tests for the BlackjackEngine class
to ensure it provides the expected behavior and correctly
implements the CardsharpEngine interface.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch
import time

from cardsharp.engine.blackjack import BlackjackEngine
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType
from cardsharp.state import GameState, GameStage
from cardsharp.blackjack.action import Action


class TestBlackjackEngine(unittest.TestCase):
    """Tests for the BlackjackEngine class."""

    def setUp(self):
        """Set up the test case."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Create a dummy adapter
        self.adapter = DummyAdapter()

        # Create a config for the engine
        self.config = {
            "dealer_rules": {"stand_on_soft_17": True, "peek_for_blackjack": True},
            "deck_count": 2,
            "rules": {
                "blackjack_pays": 1.5,
                "deck_count": 2,
                "dealer_hit_soft_17": False,
                "offer_insurance": True,
                "allow_surrender": True,
                "allow_double_after_split": True,
                "min_bet": 5.0,
                "max_bet": 1000.0,
            },
        }

        # Create a blackjack engine
        self.engine = BlackjackEngine(self.adapter, self.config)

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
        self.assertEqual(self.engine.deck_count, 2)

    @patch.object(EventBus, "emit")
    def test_initialize(self, mock_emit):
        """Test that initialize sets up the engine correctly."""

        async def run_test():
            await self.engine.initialize()

            # Check that shoe was initialized
            self.assertGreater(len(self.engine.shoe), 0)

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

            # Check that state has the correct rules
            for key, value in self.engine.rules.items():
                if key in self.engine.state.rules:
                    self.assertEqual(self.engine.state.rules[key], value)

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
            player_id = await self.engine.add_player("Test Player", 1000.0)

            # Check that the player was added
            self.assertEqual(len(self.engine.state.players), 1)
            self.assertEqual(self.engine.state.players[0].name, "Test Player")
            self.assertEqual(self.engine.state.players[0].balance, 1000.0)
            self.assertEqual(self.engine.state.players[0].id, player_id)

            # Check that PLAYER_JOINED event was emitted
            calls = [args[0] for args, _ in mock_emit.call_args_list]
            self.assertIn(EngineEventType.PLAYER_JOINED, calls)

        self.loop.run_until_complete(run_test())

    @patch.object(StateTransitionEngine, "place_bet")
    @patch.object(EventBus, "emit")
    def test_place_bet(self, mock_emit, mock_place_bet):
        """Test that place_bet places a bet correctly."""

        async def run_test():
            # Mock the place_bet method to return a modified state
            modified_state = MagicMock()
            mock_place_bet.return_value = modified_state

            # Start a game and add a player
            await self.engine.start_game()
            player_id = await self.engine.add_player("Test Player", 1000.0)

            # Set the stage to PLACING_BETS
            self.engine.state = GameState(stage=GameStage.PLACING_BETS)

            # Place a bet
            await self.engine.place_bet(player_id, 10.0)

            # Check that place_bet was called with the correct arguments
            mock_place_bet.assert_called_once()
            args = mock_place_bet.call_args[0]
            self.assertEqual(args[1], player_id)
            self.assertEqual(args[2], 10.0)

            # Check that the state was updated
            self.assertEqual(self.engine.state, modified_state)

            # Check that PLAYER_BET event was emitted
            calls = [args[0] for args, _ in mock_emit.call_args_list]
            self.assertIn(EngineEventType.PLAYER_BET, calls)

        self.loop.run_until_complete(run_test())

    def test_deal_card(self):
        """Test that _deal_card returns a card from the shoe."""
        # Initialize the shoe
        self.engine._init_shoe()

        # Deal a card
        card = self.engine._deal_card()

        # Check that a card was returned
        self.assertIsNotNone(card)

        # Check that the shoe index was incremented
        self.assertEqual(self.engine.shoe_index, 1)

    def test_shuffle_shoe(self):
        """Test that _shuffle_shoe shuffles the shoe."""
        # Initialize the shoe
        self.engine._init_shoe()

        # Remember the original order
        original_order = self.engine.shoe.copy()

        # Shuffle the shoe
        self.engine._shuffle_shoe()

        # Check that the shoe was shuffled
        self.assertNotEqual(self.engine.shoe, original_order)

        # Check that the shoe index was reset
        self.assertEqual(self.engine.shoe_index, 0)

    def test_get_valid_actions(self):
        """Test that _get_valid_actions returns the correct actions."""
        # Create a mock state with a player and hand
        from cardsharp.blackjack.state import GameState, PlayerState, HandState

        # Create a mock player with a hand
        player = PlayerState(
            id="test_player",
            name="Test Player",
            balance=1000.0,
            hands=[
                HandState(
                    bet=10.0,
                    cards=[MagicMock(rank="A"), MagicMock(rank="A")],
                    is_blackjack=False,
                    is_bust=False,
                    is_done=False,
                    is_split=False,
                    value=12,
                    is_soft=True,
                )
            ],
            current_hand_index=0,
        )

        # Create a mock state
        state = MagicMock()
        state.current_player = player
        state.current_player_index = 0

        # Set the mock state
        self.engine.state = state

        # Get valid actions
        valid_actions = self.engine._get_valid_actions()

        # Check that the expected actions are included
        self.assertIn(Action.HIT, valid_actions)
        self.assertIn(Action.STAND, valid_actions)
        self.assertIn(Action.DOUBLE, valid_actions)
        self.assertIn(Action.SPLIT, valid_actions)
        self.assertIn(Action.SURRENDER, valid_actions)


if __name__ == "__main__":
    unittest.main()
