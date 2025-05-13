"""
Integration tests for the Cardsharp system.

This module contains integration tests for the entire Cardsharp system,
testing the interaction between the API, engine, and adapters.
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch
import time

from cardsharp.api import BlackjackGame, HighCardGame
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType
from cardsharp.blackjack.action import Action


class TestBlackjackIntegration(unittest.TestCase):
    """Integration tests for the Blackjack game system."""

    def setUp(self):
        """Set up the test case."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Create a dummy adapter
        self.adapter = DummyAdapter()

        # Create a config for the game
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

        # Create a blackjack game
        self.game = BlackjackGame(
            adapter=self.adapter, config=self.config, auto_play=True
        )

    def tearDown(self):
        """Tear down the test case."""
        # Shutdown the game
        async def shutdown():
            await self.game.shutdown()

        self.loop.run_until_complete(shutdown())
        self.loop.close()

    def test_game_lifecycle(self):
        """Test the complete lifecycle of a blackjack game."""

        async def run_test():
            # Initialize the game
            await self.game.initialize()

            # Start the game
            await self.game.start_game()

            # Add players
            player1_id = await self.game.add_player("Alice", 1000.0)
            player2_id = await self.game.add_player("Bob", 1000.0)

            # Get the initial state
            initial_state = await self.game.get_state()

            # Check that the players were added
            self.assertEqual(len(initial_state.players), 2)

            # Play a round
            result = await self.game.auto_play_round(default_bet=10.0)

            # Check that the result is a dictionary
            self.assertIsInstance(result, dict)

            # Check that the stage is back to PLACING_BETS for the next round
            final_state = await self.game.get_state()
            self.assertEqual(final_state.stage.name, "PLACING_BETS")

            # Check that the players still exist
            self.assertEqual(len(final_state.players), 2)

            # Remove a player
            removed = await self.game.remove_player(player1_id)
            self.assertTrue(removed)

            # Check that the player was removed
            state_after_remove = await self.game.get_state()
            self.assertEqual(len(state_after_remove.players), 1)

        self.loop.run_until_complete(run_test())

    def test_player_actions(self):
        """Test that player actions work correctly."""

        async def run_test():
            # Initialize the game
            await self.game.initialize()

            # Start the game
            await self.game.start_game()

            # Add a player
            player_id = await self.game.add_player("Alice", 1000.0)

            # Place a bet
            bet_placed = await self.game.place_bet(player_id, 10.0)
            self.assertTrue(bet_placed)

            # Create a strategy that always stands
            await self.game.set_auto_action(player_id, Action.STAND)

            # Play a round
            result = await self.game.auto_play_round(default_bet=10.0)

            # Get the final state
            final_state = await self.game.get_state()

            # Execute different actions
            actions = [Action.HIT, Action.STAND, Action.DOUBLE]
            for action in actions:
                # Reset for next round
                state = await self.game.get_state()
                if state.stage.name != "PLAYER_TURN":
                    # Play another round
                    await self.game.auto_play_round(default_bet=10.0)

                # Set the action strategy
                await self.game.set_auto_action(player_id, action)

                # Try to execute the action
                try:
                    result = await self.game.execute_action(player_id, action)
                    # This may succeed or fail depending on the current state
                except Exception:
                    # Ignore exceptions here, as actions may not be valid in all states
                    pass

        self.loop.run_until_complete(run_test())


class TestHighCardIntegration(unittest.TestCase):
    """Integration tests for the High Card game system."""

    def setUp(self):
        """Set up the test case."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Create a dummy adapter
        self.adapter = DummyAdapter()

        # Create a config for the game
        self.config = {
            "shuffle_threshold": 5,
        }

        # Create a high card game
        self.game = HighCardGame(adapter=self.adapter, config=self.config)

    def tearDown(self):
        """Tear down the test case."""
        # Shutdown the game
        async def shutdown():
            await self.game.shutdown()

        self.loop.run_until_complete(shutdown())
        self.loop.close()

    def test_game_lifecycle(self):
        """Test the complete lifecycle of a high card game."""

        async def run_test():
            # Initialize the game
            await self.game.initialize()

            # Start the game
            await self.game.start_game()

            # Add players
            player1_id = await self.game.add_player("Alice")
            player2_id = await self.game.add_player("Bob")

            # Get the initial state
            initial_state = await self.game.get_state()

            # Check that the players were added
            self.assertEqual(len(initial_state.players), 2)

            # Play a round
            result = await self.game.play_round()

            # Check that the result is a dictionary
            self.assertIsInstance(result, dict)

            # Remove a player
            removed = await self.game.remove_player(player1_id)
            self.assertTrue(removed)

            # Check that the player was removed
            state_after_remove = await self.game.get_state()
            self.assertEqual(len(state_after_remove.players), 1)

            # Play multiple rounds
            results = await self.game.play_multiple_rounds(3)

            # Check that we got results for all rounds
            self.assertEqual(len(results), 3)

        self.loop.run_until_complete(run_test())


class TestMultiGameIntegration(unittest.TestCase):
    """Integration tests for multiple games running simultaneously."""

    def setUp(self):
        """Set up the test case."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Create dummy adapters
        self.adapter1 = DummyAdapter()
        self.adapter2 = DummyAdapter()

        # Create a blackjack game
        self.blackjack_game = BlackjackGame(adapter=self.adapter1, auto_play=True)

        # Create a high card game
        self.highcard_game = HighCardGame(adapter=self.adapter2)

    def tearDown(self):
        """Tear down the test case."""
        # Shutdown the games
        async def shutdown():
            await self.blackjack_game.shutdown()
            await self.highcard_game.shutdown()

        self.loop.run_until_complete(shutdown())
        self.loop.close()

    def test_multiple_games(self):
        """Test that multiple games can run simultaneously."""

        async def run_test():
            # Initialize the games
            await asyncio.gather(
                self.blackjack_game.initialize(), self.highcard_game.initialize()
            )

            # Start the games
            await asyncio.gather(
                self.blackjack_game.start_game(), self.highcard_game.start_game()
            )

            # Add players to both games
            blackjack_player = await self.blackjack_game.add_player("Alice", 1000.0)
            highcard_player1 = await self.highcard_game.add_player("Bob")
            highcard_player2 = await self.highcard_game.add_player("Charlie")

            # Play rounds in both games
            blackjack_task = asyncio.create_task(
                self.blackjack_game.auto_play_round(default_bet=10.0)
            )
            highcard_task = asyncio.create_task(self.highcard_game.play_round())

            # Wait for both games to complete their rounds
            blackjack_result, highcard_result = await asyncio.gather(
                blackjack_task, highcard_task
            )

            # Check that both games produced results
            self.assertIsInstance(blackjack_result, dict)
            self.assertIsInstance(highcard_result, dict)

        self.loop.run_until_complete(run_test())


if __name__ == "__main__":
    unittest.main()
