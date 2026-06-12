"""
Tests for the BlackjackEngine class.

Since beads-i2s.2 the engine is a translation layer over the fast core's
session API: these tests assert the engine contract -- emitted events,
the GameState view, the adapter interplay, and real rules enforcement --
against deterministic injected card streams (the `card_stream` config
hook).
"""

import asyncio

import pytest
from unittest.mock import patch

pytest.importorskip(
    "cardsharp_core",
    reason="cardsharp-core extension not built (uv sync --extra fast)",
)

from cardsharp.engine.blackjack import BlackjackEngine  # noqa: E402
from cardsharp.adapters import DummyAdapter  # noqa: E402
from cardsharp.events import EngineEventType, EventEmitter  # noqa: E402
from cardsharp.blackjack.action import Action  # noqa: E402
from cardsharp.state import GameStage  # noqa: E402

BASE_CONFIG = {
    "dealer_rules": {"stand_on_soft_17": False, "peek_for_blackjack": True},
    "deck_count": 6,
    "rules": {
        "blackjack_pays": 1.5,
        "deck_count": 6,
        "dealer_hit_soft_17": True,
        "offer_insurance": True,
        "allow_surrender": True,
        "allow_double_after_split": True,
        "min_bet": 5.0,
        "max_bet": 1000.0,
    },
}


def make_engine(adapter=None, cards=None, **extra_config):
    config = {k: v for k, v in BASE_CONFIG.items()}
    config["rules"] = dict(BASE_CONFIG["rules"])
    if cards is not None:
        config["card_stream"] = list(cards)
    config.update(extra_config)
    return BlackjackEngine(adapter or DummyAdapter(), config)


def scripted_adapter(actions):
    """DummyAdapter that plays a fixed action sequence, then stands."""
    queue = [Action[a.upper()] for a in actions]

    def strategy(player_id, valid_actions):
        while queue:
            action = queue.pop(0)
            if action in valid_actions:
                return action
        return Action.STAND if Action.STAND in valid_actions else valid_actions[0]

    return DummyAdapter(strategy_function=strategy)


async def play_one_round(engine, bet=10.0, balance=1000.0, name="Tester"):
    await engine.initialize()
    await engine.start_game()
    player_id = await engine.add_player(name, balance)
    await engine.place_bet(player_id, bet)  # drives the round to completion
    return player_id


def test_initialization():
    engine = make_engine()
    assert engine.adapter is not None
    assert engine.event_bus is not None
    assert engine.state is not None
    assert engine.deck_count == 6
    # Config dicts map onto the real Rules object.
    assert engine.rules_obj.num_decks == 6
    assert engine.rules_obj.dealer_hit_soft_17 is True
    assert engine.rules_obj.blackjack_payout == 1.5
    assert engine.rules_obj.min_bet == 5.0


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_initialize_emits_engine_init(mock_emit):
    engine = make_engine()
    await engine.initialize()
    assert EngineEventType.ENGINE_INIT in [
        args[0] for args, _ in mock_emit.call_args_list
    ]


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_shutdown_emits_event_and_closes_session(mock_emit):
    engine = make_engine(cards=[10, 8, 9, 7, 10])
    await play_one_round(engine)
    assert engine._session is not None
    await engine.shutdown()
    assert engine._session is None
    assert EngineEventType.ENGINE_SHUTDOWN in [
        args[0] for args, _ in mock_emit.call_args_list
    ]


@pytest.mark.asyncio
@patch.object(EventEmitter, "emit")
async def test_start_game_and_player_events(mock_emit):
    engine = make_engine()
    await engine.start_game()
    await engine.add_player("Alice", 500.0)
    events = [args[0] for args, _ in mock_emit.call_args_list]
    assert EngineEventType.GAME_CREATED in events
    assert EngineEventType.GAME_STARTED in events
    assert EngineEventType.PLAYER_JOINED in events
    assert engine.state.players[0].name == "Alice"
    assert engine.state.players[0].balance == 500.0
    assert engine.state.stage == GameStage.PLACING_BETS


@pytest.mark.asyncio
async def test_place_bet_drives_a_full_round():
    """One bet from the only player runs the round to completion through
    the adapter: P 19 vs dealer 8,7 -> dealer draws T and busts."""
    adapter = DummyAdapter()  # defaults to STAND
    engine = make_engine(adapter, cards=[10, 8, 9, 7, 10])
    await engine.initialize()
    await engine.start_game()
    player_id = await engine.add_player("Win", 1000.0)
    await engine.place_bet(player_id, 10.0)

    assert engine.state.players[0].balance == 1010.0
    assert engine.state.stage == GameStage.PLACING_BETS  # ready for next
    assert engine.state.round_number == 1
    assert adapter.rendered_states, "round must render"
    await engine.shutdown()


@pytest.mark.asyncio
async def test_round_ended_event_carries_results():
    events = []
    adapter = DummyAdapter()
    engine = make_engine(adapter, cards=[10, 8, 9, 7, 10])
    unsub = engine.event_bus.on(
        EngineEventType.ROUND_ENDED, lambda data: events.append(data)
    )
    try:
        player_id = await play_one_round(engine)
        assert len(events) == 1
        assert events[0]["results"][player_id]["balance"] == 1010.0
        assert events[0]["dealer"]["hand"]["cards"] == ["8", "7", "T"]
    finally:
        unsub()
        await engine.shutdown()


@pytest.mark.asyncio
async def test_adapter_state_dict_shape_and_hole_card():
    adapter = DummyAdapter()
    engine = make_engine(adapter, cards=[10, 8, 9, 7, 10])
    await play_one_round(engine)

    assert adapter.rendered_states
    mid = adapter.rendered_states[0]
    assert mid["dealer"]["hide_second_card"] is True
    # Upcard plus a facedown placeholder: the hole card never leaks.
    assert mid["dealer"]["hand"] == ["8", "?"]
    hand = mid["players"][0]["hands"][0]
    assert hand["cards"] == ["T", "9"]
    assert hand["value"] == 19
    assert hand["bet"] == 10.0
    assert mid["players"][0]["name"] == "Tester"

    final = adapter.rendered_states[-1]
    assert final["dealer"]["hide_second_card"] is False
    assert final["dealer"]["hand"] == ["8", "7", "T"]
    assert final["dealer"]["value"] == 25
    await engine.shutdown()


@pytest.mark.asyncio
async def test_real_rules_split_flow():
    """Splits are real now: 8,8 v 6 split into two played hands with
    correct settlement (the old inline engine's split was half-wired)."""
    adapter = scripted_adapter(["split", "stand", "stand"])
    engine = make_engine(adapter, cards=[8, 6, 8, 10, 10, 5, 9, 8, 8])
    player_id = await play_one_round(engine, bet=10.0)

    # Dealer 6,T draws 9 -> 25 bust; both split hands win.
    assert engine.state.players[0].balance == 1020.0
    final = adapter.rendered_states[-1]
    assert len(final["players"][0]["hands"]) == 2
    assert player_id is not None
    await engine.shutdown()


@pytest.mark.asyncio
async def test_insurance_is_offered_and_declined_by_default():
    """Dealer ace: the decision surfaces as [INSURANCE, STAND]; the
    default adapter stands (declines), the dealer's blackjack takes the
    hand. The old engine skipped insurance entirely."""
    decisions = []
    adapter = DummyAdapter()
    engine = make_engine(adapter, cards=[10, 1, 9, 10])
    unsub = engine.event_bus.on(
        EngineEventType.PLAYER_DECISION_NEEDED, lambda d: decisions.append(d)
    )
    try:
        await play_one_round(engine, bet=10.0)
        assert engine.state.players[0].balance == 990.0
        assert any(
            Action.INSURANCE in d["valid_actions"] for d in decisions
        ), "insurance decision never surfaced"
    finally:
        unsub()
        await engine.shutdown()


@pytest.mark.asyncio
async def test_insurance_accepted_pays_out():
    adapter = scripted_adapter(["insurance"])
    engine = make_engine(adapter, cards=[10, 1, 9, 10])
    await play_one_round(engine, bet=10.0)
    # Hand loses 10; insurance bet 5 pays 2:1 (+10 profit): net 0.
    assert engine.state.players[0].balance == 1000.0
    await engine.shutdown()


@pytest.mark.asyncio
async def test_external_execute_action_path():
    """The api/web path: the adapter never answers; an external
    execute_player_action resolves the pending decision."""

    class BlockedAdapter(DummyAdapter):
        async def request_player_action(self, *args, **kwargs):
            await asyncio.Event().wait()  # never resolves

    adapter = BlockedAdapter()
    engine = make_engine(adapter, cards=[10, 8, 9, 7, 10])
    await engine.initialize()
    await engine.start_game()
    player_id = await engine.add_player("External", 1000.0)

    round_task = asyncio.create_task(engine.place_bet(player_id, 10.0))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if engine._current_decision_player == player_id:
            break
    await engine.execute_player_action(player_id, "stand")
    await asyncio.wait_for(round_task, timeout=5.0)

    assert engine.state.players[0].balance == 1010.0
    await engine.shutdown()


@pytest.mark.asyncio
async def test_execute_action_outside_turn_raises():
    engine = make_engine()
    await engine.start_game()
    player_id = await engine.add_player("Idle", 100.0)
    with pytest.raises(ValueError):
        await engine.execute_player_action(player_id, "hit")
    await engine.shutdown()


@pytest.mark.asyncio
async def test_bet_validation():
    engine = make_engine()
    await engine.start_game()
    player_id = await engine.add_player("Poor", 20.0)
    with pytest.raises(ValueError):
        await engine.place_bet(player_id, 50.0)  # exceeds balance
    with pytest.raises(ValueError):
        await engine.place_bet("nobody", 10.0)
    await engine.shutdown()


@pytest.mark.asyncio
async def test_multi_round_shoe_and_balance_continuity():
    """Rounds share one session: the shoe continues and balances carry."""
    adapter = DummyAdapter()
    engine = make_engine(adapter, cards=[10, 8, 9, 7, 10, 9, 10, 10, 6, 2])
    await engine.initialize()
    await engine.start_game()
    player_id = await engine.add_player("Repeat", 1000.0)
    await engine.place_bet(player_id, 10.0)
    assert engine.state.players[0].balance == 1010.0
    await engine.place_bet(player_id, 10.0)  # second round, same stream
    assert engine.state.players[0].balance == 1020.0
    assert engine.state.round_number == 2
    await engine.shutdown()
