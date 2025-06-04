"""
Tests for the WarEngine class.

This module contains tests for the WarEngine class
to ensure it provides the expected behavior and correctly
implements the CardsharpEngine interface.
"""

import pytest
from unittest.mock import MagicMock, patch

from cardsharp.engine.war import WarEngine
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EngineEventType, EventEmitter
from cardsharp.war.state import GameState, GameStage, RoundResult
from cardsharp.common.card import Card, Rank, Suit


@pytest.fixture
def war_engine():
    """Create a WarEngine instance for testing."""
    # Create a dummy adapter
    adapter = DummyAdapter()

    # Create a config for the engine
    config = {"shuffle_threshold": 5}

    # Create a war engine
    engine = WarEngine(adapter, config)
    return engine


def test_initialization(war_engine):
    """Test that the engine initializes correctly."""
    assert war_engine is not None
    assert war_engine.adapter is not None
    assert war_engine.config is not None
    assert war_engine.event_bus is not None
    assert war_engine.state is not None
    assert isinstance(war_engine.state, GameState)
    assert war_engine.deck is not None
    assert war_engine.shuffle_threshold == 5


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_initialize(mock_emit, war_engine):
    """Test that initialize sets up the engine correctly."""
    await war_engine.initialize()

    # Check that the deck was initialized
    assert war_engine.deck.size == 52  # Full deck

    # Check that ENGINE_INIT event was emitted
    mock_emit.assert_called()
    args, _ = mock_emit.call_args
    assert args[0] == EngineEventType.ENGINE_INIT
    assert args[1]["engine_type"] == "war"


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_shutdown(mock_emit, war_engine):
    """Test that shutdown emits the expected event."""
    await war_engine.shutdown()

    # Check that ENGINE_SHUTDOWN event was emitted
    mock_emit.assert_called()
    args, _ = mock_emit.call_args
    assert args[0] == EngineEventType.ENGINE_SHUTDOWN


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_start_game(mock_emit, war_engine):
    """Test that start_game sets up a new game correctly."""
    await war_engine.start_game()

    # Check that a new state was created
    assert war_engine.state is not None
    assert war_engine.state.stage == GameStage.WAITING_FOR_PLAYERS

    # Check that GAME_CREATED and GAME_STARTED events were emitted
    calls = [args[0] for args, _ in mock_emit.call_args_list]
    assert EngineEventType.GAME_CREATED in calls
    assert EngineEventType.GAME_STARTED in calls


@pytest.mark.asyncio
async def test_add_player(war_engine):
    """Test that add_player adds a player correctly."""
    # Start a game
    await war_engine.start_game()

    # Add a player
    player_id = await war_engine.add_player("Test Player")

    # Check that the player was added
    assert len(war_engine.state.players) == 1
    assert war_engine.state.players[0].name == "Test Player"
    assert war_engine.state.players[0].id == player_id


@pytest.mark.asyncio
async def test_play_round_insufficient_players(war_engine):
    """Test that play_round raises an error with insufficient players."""
    # Start a game
    await war_engine.start_game()

    # Add only one player
    await war_engine.add_player("Test Player")

    # Attempt to play a round should raise ValueError
    with pytest.raises(ValueError):
        await war_engine.play_round()


@pytest.mark.asyncio
@patch("cardsharp.common.deck.Deck.deal")
@patch("cardsharp.engine.war.WarEngine.render_state")
async def test_play_round_with_clear_winner(mock_render, mock_deal, war_engine):
    """Test playing a round with a clear winner."""
    # Set up cards to ensure player 1 wins
    mock_deal.side_effect = [
        Card(Suit.HEARTS, Rank.KING),  # Player 1 gets King
        Card(Suit.CLUBS, Rank.SEVEN),  # Player 2 gets 7
    ]

    # Start a game
    await war_engine.start_game()

    # Add two players
    await war_engine.add_player("Player 1")
    await war_engine.add_player("Player 2")

    # Play a round
    result = await war_engine.play_round()

    # Verify the winner is player 1
    assert result["stage"] == "ROUND_ENDED"

    # Check that render_state was called multiple times
    assert mock_render.call_count >= 2


@pytest.mark.asyncio
@patch("cardsharp.common.deck.Deck.deal")
@patch("cardsharp.engine.war.WarEngine.render_state")
async def test_play_round_with_war(mock_render, mock_deal, war_engine):
    """Test playing a round that results in a war."""
    # Set up cards to ensure a war happens
    mock_deal.side_effect = [
        Card(Suit.HEARTS, Rank.QUEEN),  # Player 1 gets Queen
        Card(Suit.SPADES, Rank.QUEEN),  # Player 2 gets Queen - WAR!
        Card(Suit.HEARTS, Rank.ACE),  # War card for Player 1
        Card(Suit.CLUBS, Rank.KING),  # War card for Player 2
    ]

    # Start a game
    await war_engine.start_game()

    # Add two players
    await war_engine.add_player("Player 1")
    await war_engine.add_player("Player 2")

    # Patch both compare_cards and resolve_war methods
    with patch(
        "cardsharp.war.transitions.StateTransitionEngine.compare_cards"
    ) as mock_compare, patch(
        "cardsharp.war.transitions.StateTransitionEngine.resolve_war"
    ) as mock_resolve_war:

        # Set up compare_cards to return WAR result
        mock_compare.return_value = (war_engine.state, RoundResult.WAR)

        # Set up resolve_war to return updated state
        mock_resolve_war.return_value = war_engine.state

        # Play a round
        await war_engine.play_round()

        # Verify compare_cards was called and returned WAR
        mock_compare.assert_called_once()

        # Verify resolve_war was called to resolve the war
        mock_resolve_war.assert_called_once()

        # Check that render_state was called multiple times
        assert mock_render.call_count >= 3


def test_deal_card(war_engine):
    """Test that _deal_card returns a card from the deck."""
    # Deal a card
    card = war_engine._deal_card()

    # Check that a card was returned
    assert card is not None
    assert isinstance(card, Card)
    assert war_engine.deck.size == 51  # Deck should have one less card


def test_deal_card_reshuffle(war_engine):
    """Test that _deal_card reshuffles when threshold is reached."""
    # Set up a deck close to the threshold
    original_deck = war_engine.deck
    mock_deck = MagicMock()
    mock_deck.size = 4  # Below the threshold of 5
    mock_deck.deal.return_value = Card(Suit.HEARTS, Rank.ACE)
    mock_deck.reset = MagicMock()
    mock_deck.shuffle = MagicMock()

    war_engine.deck = mock_deck

    try:
        # Deal a card
        card = war_engine._deal_card()

        # Check that the deck was reset and shuffled
        mock_deck.reset.assert_called_once()
        mock_deck.shuffle.assert_called_once()
        mock_deck.deal.assert_called_once()
        assert isinstance(card, Card)
    finally:
        # Restore the original deck
        war_engine.deck = original_deck


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
