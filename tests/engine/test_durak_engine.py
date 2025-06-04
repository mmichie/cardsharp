"""
Tests for the Durak card game implementation.

This module contains tests for the Durak card game state, transitions,
engine, and API components.
"""

import pytest
from unittest.mock import patch
from dataclasses import replace

from cardsharp.common.card import Card, Rank, Suit
from cardsharp.adapters import DummyAdapter
from cardsharp.durak.state import (
    GameState,
    PlayerState,
    TableState,
    GameStage,
    DurakRules,
)
from cardsharp.durak.transitions import StateTransitionEngine
from cardsharp.engine import DurakEngine
from cardsharp.api.durak import DurakGame


class TestDurakState:
    """Tests for the Durak game state models."""

    def test_game_state_initialization(self):
        """Test that GameState initializes with the correct default values."""
        state = GameState()

        assert state.id is not None
        assert state.players == []
        assert state.stage == GameStage.WAITING_FOR_PLAYERS
        assert state.trump_suit is None
        assert state.trump_card is None
        assert state.attacker_index is None
        assert state.defender_index is None
        assert state.active_player_index is None
        assert isinstance(state.table, TableState)
        assert state.deck == []
        assert state.discard_pile == []
        assert isinstance(state.rules, DurakRules)
        assert state.current_round == 0
        assert state.loser_id is None
        assert state.timestamp > 0

    def test_player_state_initialization(self):
        """Test that PlayerState initializes with the correct default values."""
        player = PlayerState()

        assert player.id is not None
        assert player.name == "Player"
        assert player.hand == []
        assert player.is_attacker is False
        assert player.is_defender is False
        assert player.is_out is False
        assert player.pass_count == 0
        assert player.card_count == 0

    def test_player_state_has_card_of_rank(self):
        """Test that has_card correctly identifies cards by rank."""
        # Create a player with some cards
        cards = [
            Card(Suit.HEARTS, Rank.SIX),
            Card(Suit.DIAMONDS, Rank.KING),
            Card(Suit.CLUBS, Rank.ACE),
        ]
        player = PlayerState(hand=cards)

        assert player.has_card(6)  # Player has a Six
        assert player.has_card(13)  # Player has a King (value 13 in durak)
        assert player.has_card(14)  # Player has an Ace (value 14 in durak)
        assert not player.has_card(7)  # Player doesn't have a Seven

    def test_table_state_methods(self):
        """Test TableState methods for managing attack and defense cards."""
        # Create some cards
        attack_card1 = Card(Suit.HEARTS, Rank.SIX)
        attack_card2 = Card(Suit.DIAMONDS, Rank.SIX)
        defense_card = Card(Suit.SPADES, Rank.SEVEN)

        # Create a table with one attack card and no defense
        table = TableState(attack_cards=[attack_card1])

        # Test getting undefended card
        assert table.get_undefended_card() == attack_card1

        # Test checking attack position
        assert table.is_attack_position_open(0)  # First position is open
        assert not table.is_attack_position_open(1)  # Second position doesn't exist yet

        # Test attack-defense pairs
        assert table.attack_defense_pairs == [(attack_card1, None)]

        # Now add a defense card
        table = TableState(attack_cards=[attack_card1], defense_cards=[defense_card])

        # No undefended card now
        assert table.get_undefended_card() is None

        # Test attack-defense pairs
        assert table.attack_defense_pairs == [(attack_card1, defense_card)]

        # Add another attack card
        table = TableState(
            attack_cards=[attack_card1, attack_card2], defense_cards=[defense_card]
        )

        # Now there is an undefended card
        assert table.get_undefended_card() == attack_card2

        # Test attack-defense pairs
        assert table.attack_defense_pairs == [
            (attack_card1, defense_card),
            (attack_card2, None),
        ]


class TestDurakTransitions:
    """Tests for the Durak game state transitions."""

    def test_initialize_game(self):
        """Test initializing a new game with rules."""
        state = GameState()
        rules = DurakRules(deck_size=36, allow_passing=True)

        new_state = StateTransitionEngine.initialize_game(state, rules)

        assert new_state.rules == rules
        assert len(new_state.deck) == 36  # For 36-card game
        assert new_state.trump_suit is not None
        assert new_state.stage == GameStage.WAITING_FOR_PLAYERS

    def test_add_player(self):
        """Test adding a player to the game."""
        state = GameState()

        new_state = StateTransitionEngine.add_player(state, "Alice")

        assert len(new_state.players) == 1
        assert new_state.players[0].name == "Alice"

        # Add another player
        new_state = StateTransitionEngine.add_player(new_state, "Bob")

        assert len(new_state.players) == 2
        assert new_state.players[1].name == "Bob"

    def test_deal_initial_cards(self):
        """Test dealing initial cards to players."""
        state = GameState()
        state = StateTransitionEngine.initialize_game(state)
        state = StateTransitionEngine.add_player(state, "Alice")
        state = StateTransitionEngine.add_player(state, "Bob")

        # Store the original deck size
        original_deck_size = len(state.deck)

        # Deal cards
        new_state = StateTransitionEngine.deal_initial_cards(state)

        # Check that cards were dealt
        assert len(new_state.players[0].hand) == 6
        assert len(new_state.players[1].hand) == 6

        # Check that the deck size decreased
        assert len(new_state.deck) == original_deck_size - 12

        # Check that attacker and defender are set
        assert new_state.attacker_index is not None
        assert new_state.defender_index is not None
        assert new_state.active_player_index == new_state.attacker_index

        # Check player roles
        assert new_state.players[new_state.attacker_index].is_attacker
        assert new_state.players[new_state.defender_index].is_defender

    @pytest.mark.parametrize(
        "stage,is_attacker,table_cards,expected_success",
        [
            # Valid attack with no cards on table
            (GameStage.ATTACK, True, 0, True),
            # Invalid attack - not attacker
            (GameStage.ATTACK, False, 0, False),
            # Invalid attack - not in attack stage
            (GameStage.DEFENSE, True, 0, False),
            # Valid attack with cards on table and matching rank
            (GameStage.ATTACK, True, 1, True),
            # Invalid attack - no matching rank on table
            (GameStage.ATTACK, True, 1, False),
        ],
    )
    def test_play_attack_card(self, stage, is_attacker, table_cards, expected_success):
        """Test playing an attack card."""
        # Setup basic game state
        state = GameState(stage=stage)

        # Create two players
        player1 = PlayerState(
            name="Alice",
            is_attacker=is_attacker,
            hand=[Card(Suit.HEARTS, Rank.SIX), Card(Suit.HEARTS, Rank.SEVEN)],
        )
        player2 = PlayerState(
            name="Bob",
            is_attacker=not is_attacker,
            is_defender=True,
            hand=[Card(Suit.HEARTS, Rank.EIGHT), Card(Suit.HEARTS, Rank.NINE)],
        )

        # Set up table
        table = TableState()
        if table_cards > 0:
            if expected_success:
                # Add a card with the same rank as player's first card
                table = TableState(attack_cards=[Card(Suit.SPADES, Rank.SIX)])
            else:
                # Add a card with a different rank
                table = TableState(attack_cards=[Card(Suit.SPADES, Rank.TEN)])

        # Update state
        state = replace(
            state,
            players=[player1, player2],
            attacker_index=0 if is_attacker else 1,
            defender_index=1 if is_attacker else 0,
            active_player_index=0 if is_attacker else 1,
            table=table,
        )

        # Try to play the first card
        new_state = StateTransitionEngine.play_attack_card(state, player1.id, 0)

        if expected_success:
            # Card should be played
            assert len(new_state.table.attack_cards) == table_cards + 1
            assert len(new_state.players[0].hand) == 1  # Card removed from hand
            assert new_state.stage == GameStage.DEFENSE  # Moved to defense stage
        else:
            # State should be unchanged
            assert new_state == state

    def test_play_defense_card(self):
        """Test playing a defense card."""
        # Setup basic game state
        state = GameState(stage=GameStage.DEFENSE, trump_suit=Suit.HEARTS)

        # Create two players
        attacker = PlayerState(
            name="Alice", is_attacker=True, hand=[Card(Suit.CLUBS, Rank.SIX)]
        )
        defender = PlayerState(
            name="Bob",
            is_defender=True,
            hand=[
                Card(Suit.CLUBS, Rank.SEVEN),  # Higher same suit - valid
                Card(Suit.DIAMONDS, Rank.EIGHT),  # Different suit - invalid
                Card(Suit.HEARTS, Rank.FIVE),  # Trump but lower - valid
            ],
        )

        # Set up table with an attack card
        table = TableState(attack_cards=[Card(Suit.CLUBS, Rank.SIX)])

        # Update state
        state = replace(
            state,
            players=[attacker, defender],
            attacker_index=0,
            defender_index=1,
            active_player_index=1,
            table=table,
        )

        # Test valid defense - higher same suit
        new_state = StateTransitionEngine.play_defense_card(state, defender.id, 0)
        assert len(new_state.table.defense_cards) == 1
        assert new_state.table.defense_cards[0].rank == Rank.SEVEN

        # Test invalid defense - different non-trump suit
        state = replace(state, active_player_index=1)  # Reset active player
        new_state = StateTransitionEngine.play_defense_card(state, defender.id, 1)
        assert len(new_state.table.defense_cards) == 0  # No change

        # Test valid defense - trump card
        new_state = StateTransitionEngine.play_defense_card(state, defender.id, 2)
        assert len(new_state.table.defense_cards) == 1
        assert new_state.table.defense_cards[0].rank == Rank.FIVE
        assert new_state.table.defense_cards[0].suit == Suit.HEARTS

    def test_take_cards(self):
        """Test taking all cards from the table."""
        # Setup basic game state
        state = GameState(stage=GameStage.DEFENSE)

        # Create two players
        attacker = PlayerState(
            name="Alice", is_attacker=True, hand=[Card(Suit.CLUBS, Rank.EIGHT)]
        )
        defender = PlayerState(
            name="Bob", is_defender=True, hand=[Card(Suit.HEARTS, Rank.NINE)]
        )

        # Set up table with attack and defense cards
        table = TableState(
            attack_cards=[Card(Suit.CLUBS, Rank.SIX), Card(Suit.DIAMONDS, Rank.SIX)],
            defense_cards=[Card(Suit.SPADES, Rank.SEVEN)],
        )

        # Update state
        state = replace(
            state,
            players=[attacker, defender],
            attacker_index=0,
            defender_index=1,
            active_player_index=1,
            table=table,
        )

        # Take cards
        new_state = StateTransitionEngine.take_cards(state, defender.id)

        # Check that the defender's hand has increased
        assert len(new_state.players[1].hand) == 4  # Original + 3 from table

        # Check that the table is now empty
        assert len(new_state.table.attack_cards) == 0
        assert len(new_state.table.defense_cards) == 0

        # Check that we moved to next round
        assert new_state.current_round > state.current_round


@pytest.mark.asyncio
class TestDurakEngine:
    """Tests for the Durak game engine."""

    async def test_engine_initialization(self):
        """Test initializing the engine."""
        adapter = DummyAdapter()
        engine = DurakEngine(adapter)

        await engine.initialize()

        assert engine.state is not None
        assert engine.state.rules.deck_size == 36  # Default

        # Test with custom config
        config = {"deck_size": 20, "allow_passing": True}
        engine = DurakEngine(adapter, config)

        await engine.initialize()

        assert engine.state.rules.deck_size == 20
        assert engine.state.rules.allow_passing is True

    async def test_add_player(self):
        """Test adding players to the engine."""
        adapter = DummyAdapter()
        engine = DurakEngine(adapter)

        await engine.initialize()

        # Add player
        player_id = await engine.add_player("Alice")

        assert len(engine.state.players) == 1
        assert engine.state.players[0].name == "Alice"
        assert engine.state.players[0].id == player_id

    async def test_get_valid_actions(self):
        """Test getting valid actions for a player."""
        adapter = DummyAdapter()
        engine = DurakEngine(adapter)

        await engine.initialize()

        # Add two players
        player1_id = await engine.add_player("Alice")
        player2_id = await engine.add_player("Bob")

        # No valid actions before the game starts
        valid_actions = engine.get_valid_actions(player1_id)
        assert valid_actions == {}

        # Manually set up a game state for testing
        player1 = PlayerState(
            id=player1_id,
            name="Alice",
            is_attacker=True,
            hand=[Card(Suit.CLUBS, Rank.SIX), Card(Suit.HEARTS, Rank.SEVEN)],
        )
        player2 = PlayerState(
            id=player2_id,
            name="Bob",
            is_defender=True,
            hand=[Card(Suit.CLUBS, Rank.EIGHT), Card(Suit.HEARTS, Rank.NINE)],
        )

        engine.state = replace(
            engine.state,
            players=[player1, player2],
            attacker_index=0,
            defender_index=1,
            active_player_index=0,
            stage=GameStage.ATTACK,
        )

        # Check attacker's valid actions
        valid_actions = engine.get_valid_actions(player1_id)
        assert "PLAY_CARD" in valid_actions
        assert "PASS" in valid_actions

        # Check defender has no valid actions yet
        valid_actions = engine.get_valid_actions(player2_id)
        assert valid_actions == {}


@pytest.mark.asyncio
class TestDurakAPI:
    """Tests for the Durak game API."""

    async def test_api_initialization(self):
        """Test initializing the API."""
        adapter = DummyAdapter()
        game = DurakGame(adapter=adapter)

        await game.initialize()

        assert game.engine is not None

        # Test with custom config
        config = {"deck_size": 20, "allow_passing": True}
        game = DurakGame(adapter=adapter, config=config)

        await game.initialize()

        assert game.engine.state.rules.deck_size == 20
        assert game.engine.state.rules.allow_passing is True

    async def test_add_remove_player(self):
        """Test adding and removing players."""
        adapter = DummyAdapter()
        game = DurakGame(adapter=adapter)

        await game.initialize()
        await game.start_game()

        # Add player
        player_id = await game.add_player("Alice")

        assert len(game.engine.state.players) == 1
        assert game.engine.state.players[0].name == "Alice"

        # Remove player
        success = await game.remove_player(player_id)

        assert success
        assert len(game.engine.state.players) == 0

    async def test_play_card(self):
        """Test playing a card."""
        adapter = DummyAdapter()
        game = DurakGame(adapter=adapter)

        await game.initialize()
        await game.start_game()

        # Add two players
        player1_id = await game.add_player("Alice")
        player2_id = await game.add_player("Bob")

        # Set up a manual game state for testing
        player1 = PlayerState(
            id=player1_id,
            name="Alice",
            is_attacker=True,
            hand=[Card(Suit.CLUBS, Rank.SIX), Card(Suit.HEARTS, Rank.SEVEN)],
        )
        player2 = PlayerState(
            id=player2_id,
            name="Bob",
            is_defender=True,
            hand=[Card(Suit.CLUBS, Rank.EIGHT), Card(Suit.HEARTS, Rank.NINE)],
        )

        # Mock the StateTransitionEngine.play_attack_card to always succeed
        with patch(
            "cardsharp.durak.transitions.StateTransitionEngine.play_attack_card"
        ) as mock_play:
            # Set up mock to return a new state
            new_state = replace(
                game.engine.state,
                players=[player1, player2],
                attacker_index=0,
                defender_index=1,
                active_player_index=0,
                stage=GameStage.ATTACK,
            )
            mock_play.return_value = new_state

            # Set up initial state
            game.engine.state = new_state

            # Need to manually execute to trigger the mock
            await game.engine.execute_player_action(
                player_id=player1_id, action="PLAY_CARD", card_index=0
            )

            # Verify success and mock calls
            assert mock_play.called
            mock_play.assert_called_once_with(new_state, player1_id, 0)

    async def test_take_cards(self):
        """Test taking cards."""
        adapter = DummyAdapter()
        game = DurakGame(adapter=adapter)

        await game.initialize()
        await game.start_game()

        # Add two players
        player1_id = await game.add_player("Alice")
        player2_id = await game.add_player("Bob")

        # Set up a manual game state for testing
        player1 = PlayerState(
            id=player1_id,
            name="Alice",
            is_attacker=True,
            hand=[Card(Suit.CLUBS, Rank.SIX)],
        )
        player2 = PlayerState(
            id=player2_id,
            name="Bob",
            is_defender=True,
            hand=[Card(Suit.CLUBS, Rank.EIGHT)],
        )

        # Mock the StateTransitionEngine.take_cards to always succeed
        with patch(
            "cardsharp.durak.transitions.StateTransitionEngine.take_cards"
        ) as mock_take:
            # Set up mock to return a new state
            new_state = replace(
                game.engine.state,
                players=[player1, player2],
                attacker_index=0,
                defender_index=1,
                active_player_index=1,
                stage=GameStage.DEFENSE,
            )
            mock_take.return_value = new_state

            # Set up initial state
            game.engine.state = new_state

            # Need to manually execute to trigger the mock
            await game.engine.execute_player_action(
                player_id=player2_id, action="TAKE_CARDS"
            )

            # Verify success and mock calls
            assert mock_take.called
            mock_take.assert_called_once_with(new_state, player2_id)
