"""Interactive session API tests (beads-i2s.1).

The structural guarantee under test: a Session runs the SAME play_round
as the batch entry points, so replaying the exact action script that
play_card_stream recorded -- through the channel-backed interactive path
-- must reproduce the records exactly (every hand, action, winner, bet,
net, and card consumed; `money` differs only because sessions persist
bankrolls across rounds while the batch path reseats a fresh bankroll
each round).
"""

import logging
import os
import random
from collections import deque

import pytest

cardsharp_core = pytest.importorskip(
    "cardsharp_core",
    reason="cardsharp-core extension not built (uv sync --extra fast)",
)

os.environ["BLACKJACK_DISABLE_LOGGING"] = "1"

from cardsharp.blackjack.decision_logger import decision_logger  # noqa: E402
from cardsharp.blackjack.rules import Rules  # noqa: E402
from cardsharp.blackjack.strategy import BasicStrategy  # noqa: E402
from cardsharp.fastsim import (  # noqa: E402
    encode_strategy_table,
    make_core_rules,
    open_session,
)

decision_logger.set_level(logging.ERROR)

BANKROLL = 1_000_000.0  # ample: affordability never binds in either path


def make_rules(**overrides):
    kwargs = dict(
        num_decks=6,
        dealer_peek=True,
        allow_double_after_split=True,
        allow_split=True,
        allow_insurance=True,
        allow_surrender=True,
        min_bet=10,
        max_bet=1000,
        penetration=0.75,
        dealer_hit_soft_17=True,
        max_splits=3,
    )
    kwargs.update(overrides)
    return Rules(**kwargs)


def stream_records(rules, codes, n_players=1, always_insure=False):
    table = encode_strategy_table(BasicStrategy(), rules)
    return cardsharp_core.play_card_stream(
        make_core_rules(rules),
        table,
        bytes(codes),
        n_players=n_players,
        initial_bankroll=BANKROLL,
        always_insure=always_insure,
    )


def seat_early_surrendered(player_record):
    """An early-surrendered seat shows no recorded actions (the reference
    quirk) and exactly half the original bet lost."""
    return not any(player_record.actions) and player_record.net == -(
        player_record.original_bets[0] / 2.0
    )


def replay_through_session(rules, codes, records, n_players=1, always_insure=False):
    """Drive a Session with the action script play_card_stream recorded;
    return the session's round records."""
    session = cardsharp_core.Session(
        make_core_rules(rules),
        n_players=n_players,
        bankroll=BANKROLL,
        cards=bytes(codes),
    )
    out = []
    for rec in records:
        script = {
            (seat, h): deque(p.actions[h])
            for seat, p in enumerate(rec.players)
            for h in range(len(p.actions))
        }
        step = session.begin_round([float(rules.min_bet)] * n_players)
        while step.phase != "round_over":
            if step.phase == "insurance":
                step = session.apply("insure" if always_insure else "decline")
            elif step.phase == "early_surrender":
                early = seat_early_surrendered(rec.players[step.seat])
                step = session.apply("surrender" if early else "stand")
            else:
                step = session.apply(script[(step.seat, step.hand_index)].popleft())
        assert all(not q for q in script.values()), "session asked fewer decisions"
        out.append(step.result)
    session.close()
    return out


def assert_records_equal_modulo_bankroll(session_rec, stream_rec, context):
    assert session_rec.cards_consumed == stream_rec.cards_consumed, context
    assert session_rec.dealer_cards == stream_rec.dealer_cards, context
    for sp, tp in zip(session_rec.players, stream_rec.players):
        assert sp.hands == tp.hands, context
        assert sp.actions == tp.actions, context
        assert sp.winners == tp.winners, context
        assert sp.first_cards == tp.first_cards, context
        assert sp.bets == tp.bets, context
        assert sp.original_bets == tp.original_bets, context
        assert sp.net == tp.net, context
        assert sp.initial_bet == tp.initial_bet, context
        assert sp.total_bet == tp.total_bet, context
        assert sp.blackjack == tp.blackjack, context


SPLIT_HEAVY = [6, 1, 1, 1, 1, 1, 1, 6, 1, 2, 2, 2, 2]
TEN_HEAVY = [3, 1, 1, 1, 1, 2, 2, 2, 1, 4, 4, 4, 4]
UNIFORM = [1] * 13


@pytest.mark.parametrize(
    "overrides,weights,n_players,always_insure,trials,seed",
    [
        pytest.param({}, UNIFORM, 1, False, 60, 501, id="base-uniform"),
        pytest.param(
            {"allow_resplitting": True, "resplit_aces": True, "hit_split_aces": True},
            SPLIT_HEAVY,
            1,
            False,
            60,
            502,
            id="resplit-aces-hit",
        ),
        pytest.param(
            {"dealer_hit_soft_17": False},
            SPLIT_HEAVY,
            1,
            False,
            50,
            503,
            id="s17-splits",
        ),
        pytest.param(
            {"dealer_peek": False}, TEN_HEAVY, 1, False, 50, 504, id="no-peek-tens"
        ),
        pytest.param(
            {"dealer_peek": False, "insurance_payout": 3.0},
            TEN_HEAVY,
            1,
            True,
            40,
            505,
            id="no-peek-insured",
        ),
        pytest.param(
            {"allow_early_surrender": True},
            TEN_HEAVY,
            1,
            False,
            50,
            506,
            id="early-surrender",
        ),
        pytest.param(
            {"five_card_charlie": True}, UNIFORM, 1, False, 40, 507, id="charlie"
        ),
        pytest.param({}, UNIFORM, 3, False, 40, 508, id="three-players"),
        pytest.param(
            {"allow_resplitting": True},
            SPLIT_HEAVY,
            2,
            False,
            40,
            509,
            id="two-players-resplit",
        ),
    ],
)
def test_session_replays_stream_records_exactly(
    overrides, weights, n_players, always_insure, trials, seed
):
    """Action-replay parity: identical cards + identical decisions through
    the interactive path must reproduce the batch path's records."""
    rules = make_rules(**overrides)
    rng = random.Random(seed)
    rounds_compared = 0
    for trial in range(trials):
        codes = rng.choices(range(1, 14), weights=weights, k=40 + 30 * n_players)
        records = stream_records(rules, codes, n_players, always_insure)
        if not records:
            continue
        replayed = replay_through_session(
            rules, codes, records, n_players, always_insure
        )
        assert len(replayed) == len(records)
        for i, (ses, ref) in enumerate(zip(replayed, records)):
            assert_records_equal_modulo_bankroll(
                ses, ref, f"trial {trial} round {i} codes={codes}"
            )
        rounds_compared += len(records)
    assert rounds_compared >= trials, "too few rounds exercised"


def test_session_bankroll_persists_and_tracks_nets():
    rules = make_rules()
    codes = [10, 9, 6, 8, 5] * 12  # several playable rounds
    records = stream_records(rules, codes)
    session = cardsharp_core.Session(
        make_core_rules(rules), bankroll=BANKROLL, cards=bytes(codes)
    )
    money = BANKROLL
    for rec in records:
        script = deque(rec.players[0].actions[0])
        step = session.begin_round([10.0])
        while step.phase != "round_over":
            step = session.apply(script.popleft())
        money += step.result.players[0].net
        assert session.money == [money]
    session.close()


def test_session_decision_context_shape():
    """The step at a decision carries the seat's live view: hand cards,
    legal actions, dealer upcard only."""
    rules = make_rules()
    session = cardsharp_core.Session(
        make_core_rules(rules), cards=bytes([8, 9, 8, 8, 10, 5, 9, 10, 10])
    )
    step = session.begin_round([10.0])
    assert step.phase == "decision"
    assert step.seat == 0 and step.hand_index == 0
    assert step.players[0].hands == [[8, 8]]
    assert step.dealer_cards == [9]  # hole card hidden
    assert "split" in step.valid_actions and "surrender" in step.valid_actions
    step = session.apply("split")
    assert len(step.players[0].hands) == 2
    assert step.players[0].actions[0] == ["split"]
    session.close()


def test_session_insurance_flow_pays_and_charges():
    rules = make_rules(dealer_peek=True)
    # Dealer A,10 blackjack; player 10,9. Insurance pays 2:1 -> net 0 - 10 = ...
    # bet 10 lost to dealer BJ, insurance 5 pays 5*(1+2)=15 -> net -10 + 10 = 0.
    session = cardsharp_core.Session(
        make_core_rules(rules), cards=bytes([10, 1, 9, 10])
    )
    step = session.begin_round([10.0])
    assert step.phase == "insurance"
    assert sorted(step.valid_actions) == ["decline", "insure"]
    step = session.apply("insure")
    assert step.phase == "round_over"
    assert step.result.players[0].net == 0.0  # -10 hand, +10 insurance profit
    assert session.money == [1000.0]

    # Same cards, declined: lose the hand outright.
    session2 = cardsharp_core.Session(
        make_core_rules(rules), cards=bytes([10, 1, 9, 10])
    )
    step = session2.begin_round([10.0])
    step = session2.apply("decline")
    assert step.phase == "round_over"
    assert step.result.players[0].net == -10.0
    session.close()
    session2.close()


def test_session_early_surrender_flow():
    rules = make_rules(allow_early_surrender=True, dealer_peek=False)
    # Player 10,6 vs dealer 10: early surrender forfeits half before peek.
    session = cardsharp_core.Session(
        make_core_rules(rules), cards=bytes([10, 10, 6, 9])
    )
    step = session.begin_round([10.0])
    assert step.phase == "early_surrender"
    step = session.apply("surrender")
    assert step.phase == "round_over"
    assert step.result.players[0].net == -5.0
    session.close()


def test_session_validates_inputs():
    rules = make_rules()
    session = cardsharp_core.Session(
        make_core_rules(rules), cards=bytes([10, 9, 6, 8] * 4)
    )

    with pytest.raises(RuntimeError, match="no decision pending"):
        session.apply("hit")
    with pytest.raises(ValueError, match="expected 1 bets"):
        session.begin_round([10.0, 10.0])
    with pytest.raises(ValueError, match="outside table limits"):
        session.begin_round([5.0])
    session2 = cardsharp_core.Session(
        make_core_rules(rules), bankroll=50.0, cards=bytes([10, 9, 6, 8] * 4)
    )
    with pytest.raises(ValueError, match="exceeds bankroll"):
        session2.begin_round([100.0])

    step = session.begin_round([10.0])
    assert step.phase == "decision"
    with pytest.raises(RuntimeError, match="already in progress"):
        session.begin_round([10.0])
    with pytest.raises(ValueError, match="unknown action"):
        session.apply("flip")
    with pytest.raises(ValueError, match="not legal here"):
        session.apply("split")  # 10,6 is not a pair
    # The pending decision survived all the rejected inputs.
    step = session.apply("stand")
    assert step.phase == "round_over"
    session.close()
    with pytest.raises(RuntimeError, match="closed"):
        session.begin_round([10.0])
    session2.close()


def test_session_stream_exhaustion_raises():
    rules = make_rules()
    session = cardsharp_core.Session(make_core_rules(rules), cards=bytes([10, 9, 6]))
    with pytest.raises(RuntimeError, match="exhausted"):
        session.begin_round([10.0])
    session.close()


def test_session_drop_mid_round_does_not_hang():
    """Dropping a session with a decision pending must unwind the worker
    (the decider goes inert and the round stands itself out)."""
    rules = make_rules()
    session = cardsharp_core.Session(
        make_core_rules(rules), cards=bytes([10, 9, 6, 8, 5, 5, 5, 5])
    )
    step = session.begin_round([10.0])
    assert step.phase == "decision"
    del session  # Drop runs: close channel, join worker; must not deadlock


def test_session_shoe_mode_is_deterministic_and_reshuffles():
    """Seeded shoe sessions: same seed + same script = identical records;
    the shoe persists across rounds and passes a penetration reshuffle."""
    rules = make_rules(num_decks=1, penetration=0.5)

    def run(seed):
        session = open_session(rules, bankroll=BANKROLL, seed=seed)
        trace = []
        for _ in range(20):  # 1-deck pen 0.5: several reshuffles guaranteed
            step = session.begin_round([10.0])
            while step.phase != "round_over":
                if step.phase == "insurance":
                    step = session.apply("decline")
                else:
                    step = session.apply(
                        "stand" if "stand" in step.valid_actions else "hit"
                    )
            rec = step.result
            trace.append(
                (rec.players[0].net, rec.cards_consumed, rec.players[0].first_cards)
            )
        session.close()
        return trace

    trace_a = run(seed=99)
    trace_b = run(seed=99)
    trace_c = run(seed=100)
    assert trace_a == trace_b
    assert sum(t[1] for t in trace_a) > 52, "20 rounds must cross a 1-deck reshuffle"
    assert trace_a != trace_c, "different seeds should differ"


def test_open_session_facade_and_multiseat_order():
    """Facade construction plus multi-seat prompting order: seats are
    asked in order, each to completion."""
    rules = make_rules()
    # P0 9,K (19); P1 10,10 (20); dealer 9,9 (18). Both stand and win.
    session = open_session(
        rules, n_players=2, bankroll=500.0, cards=[9, 10, 9, 13, 10, 9]
    )
    step = session.begin_round([10.0, 25.0])
    seats_asked = []
    while step.phase != "round_over":
        seats_asked.append(step.seat)
        step = session.apply("stand")
    assert seats_asked == [0, 1]
    assert step.result.players[0].winners == ["player"]
    assert step.result.players[1].winners == ["player"]
    assert session.money == [510.0, 525.0]
    session.close()
