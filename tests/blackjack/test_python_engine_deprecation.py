"""The Python round engine's deprecation warning (beads-i2s.6 stage 2).

The engine is frozen as of v0.7.0 and scheduled for deletion in the next
release; every code path that still drives it must say so once per
process. These tests pin the warning at both round chokepoints and in
the engine-resolution reason, so the deprecation cannot silently vanish
before the removal actually happens.
"""

import logging
import os

import pytest

os.environ["BLACKJACK_DISABLE_LOGGING"] = "1"

import cardsharp.blackjack.blackjack as bj  # noqa: E402
from cardsharp.blackjack.decision_logger import decision_logger  # noqa: E402
from cardsharp.blackjack.rules import Rules  # noqa: E402
from cardsharp.blackjack.strategy import BasicStrategy  # noqa: E402
from cardsharp.common.io_interface import DummyIOInterface  # noqa: E402
from cardsharp.fastsim import resolve_engine  # noqa: E402

decision_logger.set_level(logging.ERROR)


@pytest.fixture(autouse=True)
def reset_once_guard():
    """The warning fires once per process; rearm it per test."""
    bj._python_engine_warned = False
    yield
    bj._python_engine_warned = False


def make_rules():
    return Rules(
        num_decks=6,
        dealer_peek=True,
        allow_double_after_split=True,
        min_bet=10,
        max_bet=1000,
        penetration=0.75,
        dealer_hit_soft_17=True,
    )


def test_play_game_warns_once():
    rules = make_rules()
    with pytest.warns(DeprecationWarning, match="deprecated since v0.7.0"):
        _, _, _, _, shoe = bj.play_game(
            rules, DummyIOInterface(), ["P"], BasicStrategy(), None, 1000
        )
    # Second round: the once-per-process guard holds (no new warning).
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        bj.play_game(rules, DummyIOInterface(), ["P"], BasicStrategy(), shoe, 1000)


def test_play_round_warns():
    from cardsharp.blackjack.actor import Player

    rules = make_rules()
    io = DummyIOInterface()
    game = bj.BlackjackGame(rules, io)
    game.add_player(Player("P", io, BasicStrategy(), initial_money=1000))
    with pytest.warns(DeprecationWarning, match="deprecated since v0.7.0"):
        game.play_round()


def test_resolve_engine_python_reason_mentions_deprecation():
    choice = resolve_engine(make_rules(), BasicStrategy(), requested="python")
    assert not choice.use_core
    assert "deprecated" in choice.reason
