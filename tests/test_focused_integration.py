"""
Simplified integration tests for the Cardsharp system.

This module contains targeted integration tests focusing only on essential
interactions between the API, engine, and adapters, with strict cleanup.
"""

import asyncio
import pytest
from typing import Dict, Any

from cardsharp.api import BlackjackGame, HighCardGame
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus, EngineEventType
from cardsharp.blackjack.action import Action


@pytest.fixture(autouse=True)
def reset_event_bus():
    """Reset the event bus singleton before and after each test."""
    EventBus._instance = None
    yield
    EventBus._instance = None


@pytest.mark.asyncio
async def test_blackjack_focused_integration():
    """Test basic Blackjack game functionality with proper cleanup."""
    # Create adapter and game
    adapter = DummyAdapter()
    game = BlackjackGame(adapter=adapter, auto_play=True)

    try:
        # Initialize and start
        await game.initialize()
        await game.start_game()

        # Add player, place bet, play round
        player_id = await game.add_player("TestPlayer", 1000.0)
        bet_result = await game.place_bet(player_id, 10.0)
        assert bet_result is True

        # Get state before playing
        state_before = await game.get_state()
        assert len(state_before.players) == 1

        # Play a round
        result = await game.auto_play_round(default_bet=10.0)

        # Validate result contains expected data
        assert isinstance(result, dict)
        assert "players" in result

    finally:
        # Ensure proper cleanup
        await game.shutdown()


@pytest.mark.asyncio
async def test_highcard_focused_integration():
    """Test basic High Card game functionality with proper cleanup."""
    # Create adapter and game
    adapter = DummyAdapter()
    game = HighCardGame(adapter=adapter)

    try:
        # Initialize and start
        await game.initialize()
        await game.start_game()

        # Add players
        player1 = await game.add_player("Player1")
        player2 = await game.add_player("Player2")

        # Get state before playing
        state_before = await game.get_state()
        assert len(state_before.players) == 2

        # Play a round
        result = await game.play_round()

        # Validate result contains expected data
        assert isinstance(result, dict)

    finally:
        # Ensure proper cleanup
        await game.shutdown()
