"""
Tests for the base CardsharpEngine class.

This module contains tests for the CardsharpEngine base class
to ensure it provides the expected interface and behavior.
"""

import pytest
from unittest.mock import patch
import time

from cardsharp.engine.base import CardsharpEngine
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventEmitter, EngineEventType


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


@pytest.fixture
def engine():
    """Create a MockEngine instance for testing."""
    # Create a dummy adapter
    adapter = DummyAdapter()

    # Create a mock engine
    return MockEngine(adapter)


def test_initialization(engine):
    """Test that the engine initializes correctly."""
    assert engine is not None
    assert isinstance(engine.adapter, DummyAdapter)
    assert engine.config == {}
    assert engine.event_bus is not None


def test_config():
    """Test that the engine uses the provided config."""
    adapter = DummyAdapter()
    config = {"test_key": "test_value"}
    engine = MockEngine(adapter, config)
    assert engine.config == config


@pytest.mark.asyncio
@patch.object(DummyAdapter, "initialize")
async def test_initialize(mock_initialize, engine):
    """Test that initialize calls the adapter's initialize method."""
    await engine.initialize()
    mock_initialize.assert_called_once()


@pytest.mark.asyncio
@patch.object(DummyAdapter, "shutdown")
async def test_shutdown(mock_shutdown, engine):
    """Test that shutdown calls the adapter's shutdown method."""
    await engine.shutdown()
    mock_shutdown.assert_called_once()


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_start_game(mock_emit, engine):
    """Test that start_game emits the expected event."""
    await engine.start_game()

    # Check that emit was called with the correct event type
    mock_emit.assert_called()
    args = mock_emit.call_args[0]
    assert args[0] == EngineEventType.GAME_CREATED


@pytest.mark.asyncio
async def test_abstract_methods(engine):
    """Test that the abstract methods are implemented by the mock engine."""
    # These should not raise NotImplementedError
    await engine.initialize()
    await engine.shutdown()
    await engine.start_game()
    await engine.add_player("Test Player")
    await engine.place_bet("test_player_id", 10.0)
    await engine.execute_player_action("test_player_id", "test_action")
    await engine.render_state()


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
