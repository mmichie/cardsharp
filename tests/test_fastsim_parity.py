"""Card-stream parity suite: Rust core vs Python reference engine (beads-9ro.5).

Both engines play identical injected card sequences; every comparable
quantity must match exactly: money flow (net, initial, total bets),
per-hand outcomes, and cards consumed. Where stream injection cannot reach
-- shuffle timing across rounds and mid-round shoe exhaustion -- the suite
compares shuffle epochs instead, which depend only on consumption counts
and are therefore RNG-independent.

This is the accuracy gate from docs/optimization_principles.md: same
inputs, identical outcomes, edge cases thoroughly.
"""

import logging
import os
import random

import pytest

cardsharp_core = pytest.importorskip(
    "cardsharp_core",
    reason="cardsharp-core extension not built (uv sync --extra fast)",
)

os.environ["BLACKJACK_DISABLE_LOGGING"] = "1"

from cardsharp.blackjack.blackjack import play_game  # noqa: E402
from cardsharp.blackjack.decision_logger import decision_logger  # noqa: E402
from cardsharp.blackjack.rules import Rules  # noqa: E402
from cardsharp.blackjack.strategy import (  # noqa: E402
    BasicStrategy,
    CountingStrategy,
)
from cardsharp.common.card import Card, Rank, Suit  # noqa: E402
from cardsharp.common.io_interface import DummyIOInterface  # noqa: E402
from cardsharp.common.shoe import Shoe  # noqa: E402
from cardsharp.fastsim import (  # noqa: E402
    encode_counting_config,
    encode_strategy_table,
    make_core_rules,
)

decision_logger.set_level(logging.ERROR)


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


class AlwaysInsureStrategy(BasicStrategy):
    def decide_insurance(self, player) -> bool:
        return True


def python_stream(rules, strategy, codes, n_players=1, bankroll=1000):
    """Play rounds from a fixed card sequence through the Python engine."""
    player_names = [f"P{i}" for i in range(n_players)]
    shoe = Shoe(num_decks=rules.num_decks, penetration=1.0)
    shoe.cards = [Card(Suit.SPADES, Rank(c)) for c in codes]
    shoe.next_card_index = 0
    shoe.total_cards = len(shoe.cards)
    shoe.reshuffle_point = len(shoe.cards) + 10_000  # never shuffle
    rounds = []
    while shoe.total_cards - shoe.next_card_index >= 4 * (n_players + 1):
        before = shoe.next_card_index
        try:
            net, total, initial, report, shoe = play_game(
                rules, DummyIOInterface(), player_names, strategy, shoe, bankroll
            )
        except IndexError:
            break  # exhausted mid-round
        rounds.append(
            {
                "net": net,
                "total": total,
                "initial": initial,
                "wins": report["player_wins"],
                "losses": report["dealer_wins"],
                "draws": report["draws"],
                "consumed": shoe.next_card_index - before,
            }
        )
    return rounds


def rust_stream(
    rules, strategy, codes, n_players=1, bankroll=1000, always_insure=False
):
    table = encode_strategy_table(strategy, rules)
    counting = (
        encode_counting_config(strategy) if type(strategy) is CountingStrategy else None
    )
    records = cardsharp_core.play_card_stream(
        make_core_rules(rules),
        table,
        bytes(codes),
        n_players=n_players,
        initial_bankroll=bankroll,
        always_insure=always_insure,
        counting=counting,
    )
    rounds = []
    for r in records:
        winners = [w for p in r.players for w in p.winners]
        rounds.append(
            {
                "net": sum(p.net for p in r.players),
                "total": sum(p.total_bet for p in r.players),
                "initial": sum(p.initial_bet for p in r.players),
                "wins": winners.count("player"),
                "losses": winners.count("dealer"),
                "draws": winners.count("draw"),
                "consumed": r.cards_consumed,
            }
        )
    return rounds


def assert_streams_match(
    rules, strategy, codes, n_players=1, bankroll=1000, always_insure=False, context=""
):
    py = python_stream(rules, strategy, codes, n_players, bankroll)
    rs = rust_stream(rules, strategy, codes, n_players, bankroll, always_insure)
    # The Python shoe recycles discards at exhaustion while the stream
    # stops, so only the common prefix is comparable.
    compared = min(len(py), len(rs))
    for i in range(compared):
        assert py[i] == rs[i], (
            f"{context} round {i} diverged:\n  python={py[i]}\n  rust=  {rs[i]}\n"
            f"  codes={codes}"
        )
    return compared


def weighted_codes(rng, n, weights):
    return rng.choices(range(1, 14), weights=weights, k=n)


# Rank weights designed to hammer rare paths: aces and eights force
# splits, resplits, split aces, and surrender fallbacks; tens force
# dealer-blackjack peeks and 16-vs-ten surrenders.
SPLIT_HEAVY = [6, 1, 1, 1, 1, 1, 1, 6, 1, 2, 2, 2, 2]
TEN_HEAVY = [3, 1, 1, 1, 1, 2, 2, 2, 1, 4, 4, 4, 4]
UNIFORM = [1] * 13


FUZZ_CONFIGS = [
    pytest.param({}, UNIFORM, False, 1, 1000, 200, 101, id="base-uniform"),
    pytest.param({}, SPLIT_HEAVY, False, 1, 1000, 250, 102, id="base-splits"),
    pytest.param({}, TEN_HEAVY, False, 1, 1000, 200, 103, id="base-tens"),
    pytest.param(
        {"allow_resplitting": True, "resplit_aces": True, "hit_split_aces": True},
        SPLIT_HEAVY,
        False,
        1,
        1000,
        250,
        104,
        id="resplit-aces-hit",
    ),
    pytest.param(
        {"dealer_hit_soft_17": False, "allow_resplitting": True},
        SPLIT_HEAVY,
        False,
        1,
        1000,
        200,
        105,
        id="s17-resplit",
    ),
    pytest.param(
        {"allow_double_after_split": False, "double_on": "9-11"},
        SPLIT_HEAVY,
        False,
        1,
        1000,
        150,
        106,
        id="no-das-double-9-11",
    ),
    pytest.param(
        {"double_on": "10-11", "allow_surrender": False},
        UNIFORM,
        False,
        1,
        1000,
        150,
        107,
        id="double-10-11-no-surrender",
    ),
    pytest.param(
        {"dealer_peek": False},
        TEN_HEAVY,
        False,
        1,
        1000,
        200,
        108,
        id="no-peek-tens",
    ),
    pytest.param(
        {"dealer_peek": False, "allow_obo": False},
        TEN_HEAVY,
        False,
        1,
        1000,
        150,
        109,
        id="no-peek-no-obo",
    ),
    pytest.param(
        {"dealer_peek": False, "insurance_payout": 3.0},
        TEN_HEAVY,
        True,
        1,
        1000,
        150,
        110,
        id="no-peek-insured",
    ),
    pytest.param(
        {"allow_early_surrender": True},
        TEN_HEAVY,
        False,
        1,
        1000,
        150,
        111,
        id="early-surrender-peek",
    ),
    pytest.param(
        {"allow_early_surrender": True, "dealer_peek": False},
        TEN_HEAVY,
        False,
        1,
        1000,
        150,
        112,
        id="early-surrender-no-peek",
    ),
    pytest.param(
        {"five_card_charlie": True},
        UNIFORM,
        False,
        1,
        1000,
        150,
        113,
        id="charlie",
    ),
    pytest.param(
        {"max_splits": 1}, SPLIT_HEAVY, False, 1, 1000, 150, 114, id="max-splits-1"
    ),
    # The three ENGINE_INERT claims from the rules-surface tripwire
    # (tests/test_fastsim_runner.py): each flag is honored by neither
    # engine on classic strategy-driven rounds. If the Python engine ever
    # starts reading one of these, parity breaks here.
    pytest.param(
        {"allow_late_surrender": True, "allow_surrender": False},
        TEN_HEAVY,
        False,
        1,
        1000,
        100,
        120,
        id="late-surrender-flag-inert",
    ),
    pytest.param(
        {"time_limit": 30}, UNIFORM, False, 1, 1000, 100, 121, id="time-limit-inert"
    ),
    pytest.param(
        {"bonus_payouts": {"suited-6-7-8": 2.0, "7-7-7": 3.0, "five-card-21": 1.5}},
        UNIFORM,
        False,
        1,
        1000,
        100,
        122,
        id="bonus-payouts-inert",
    ),
    pytest.param({"num_decks": 1}, UNIFORM, False, 1, 1000, 150, 115, id="one-deck"),
    pytest.param({}, SPLIT_HEAVY, False, 1, 15, 200, 116, id="broke-player"),
    pytest.param({}, SPLIT_HEAVY, False, 1, 25, 150, 117, id="one-double-only"),
    pytest.param({}, UNIFORM, False, 3, 1000, 150, 118, id="three-players"),
    pytest.param(
        {"allow_resplitting": True},
        SPLIT_HEAVY,
        False,
        2,
        1000,
        150,
        119,
        id="two-players-resplit",
    ),
]


@pytest.mark.parametrize(
    "overrides,weights,always_insure,n_players,bankroll,trials,seed", FUZZ_CONFIGS
)
def test_stream_parity_fuzz(
    overrides, weights, always_insure, n_players, bankroll, trials, seed
):
    rules = make_rules(**overrides)
    strategy = AlwaysInsureStrategy() if always_insure else BasicStrategy()
    rng = random.Random(seed)
    cards_per_trial = 40 + 30 * n_players
    compared = 0
    for trial in range(trials):
        codes = weighted_codes(rng, cards_per_trial, weights)
        compared += assert_streams_match(
            rules,
            strategy,
            codes,
            n_players,
            bankroll,
            always_insure,
            context=f"trial {trial}",
        )
    assert compared >= trials  # several rounds per trial expected


# Drives the running count strongly positive: bet ramp, stand/double
# deviations, and TC>=3 insurance all fire. Aces stay frequent so
# insurance offers actually occur.
LOW_HEAVY = [3, 4, 4, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1]


@pytest.mark.parametrize(
    "overrides,weights,trials,seed",
    [
        pytest.param({}, UNIFORM, 150, 201, id="count-uniform"),
        pytest.param({}, LOW_HEAVY, 200, 202, id="count-high-tc"),
        pytest.param({}, TEN_HEAVY, 150, 203, id="count-negative-tc"),
        pytest.param(
            {"dealer_hit_soft_17": False}, LOW_HEAVY, 150, 204, id="count-s17"
        ),
        pytest.param({"dealer_peek": False}, LOW_HEAVY, 150, 205, id="count-no-peek"),
        pytest.param(
            {"allow_resplitting": True}, SPLIT_HEAVY, 150, 206, id="count-resplit"
        ),
    ],
)
def test_counting_stream_parity_fuzz(overrides, weights, trials, seed):
    """Counting parity: the Hi-Lo count, bet ramp, Illustrious 18
    deviations, and TC-based insurance must move money identically in
    both engines. Streams are long so the count evolves across rounds;
    the strategy is fresh per trial (its count is stateful)."""
    rules = make_rules(**overrides)
    rng = random.Random(seed)
    compared = 0
    for trial in range(trials):
        codes = weighted_codes(rng, 120, weights)
        strategy = CountingStrategy(num_decks=rules.num_decks)
        compared += assert_streams_match(
            rules, strategy, codes, context=f"counting trial {trial}"
        )
    assert compared > trials * 3  # long streams: several rounds per trial


def test_counting_bet_ramp_rises_with_the_count():
    """A run of low cards must raise later bets identically in both
    engines, and the ramp must actually fire."""
    rules = make_rules()
    codes = [2, 3, 4, 5, 6] * 4 + [10, 10, 10, 10, 10, 10]
    strategy = CountingStrategy(num_decks=rules.num_decks)
    assert_streams_match(rules, strategy, codes, context="bet-ramp")
    rs = rust_stream(rules, CountingStrategy(num_decks=rules.num_decks), codes)
    assert rs, "stream produced no rounds"
    assert any(
        r["initial"] > 10 for r in rs[1:]
    ), f"bet ramp never fired: {[r['initial'] for r in rs]}"


def test_resplit_eights_to_four_hands():
    """8,8 resplit chain reaching the max-hands cap, engine vs engine."""
    rules = make_rules(allow_resplitting=True)
    strategy = BasicStrategy()
    # P 8,8 vs dealer 6; each split hand draws another 8, resplitting to
    # the 4-hand cap, then each hand fills out.
    codes = [8, 6, 8, 10, 8, 8, 10, 9, 3, 7, 5, 10, 10, 10, 10, 10]
    assert_streams_match(rules, strategy, codes, context="resplit-chain")
    records = cardsharp_core.play_card_stream(
        make_core_rules(rules), encode_strategy_table(strategy, rules), bytes(codes)
    )
    assert len(records[0].players[0].hands) == 4
    assert records[0].players[0].actions[0][0] == "split"


def test_eights_versus_ace_surrender_chain():
    """8,8 vs A is chart-Surrender in H17; with surrender disabled the
    fallback chain must split instead. Both paths engine vs engine."""
    strategy = BasicStrategy()
    codes = [8, 1, 8, 9, 10, 10, 10, 5, 9]

    with_surrender = make_rules()
    assert_streams_match(with_surrender, strategy, codes, context="8-8-vs-A-surrender")
    rec = cardsharp_core.play_card_stream(
        make_core_rules(with_surrender),
        encode_strategy_table(strategy, with_surrender),
        bytes(codes),
    )
    assert rec[0].players[0].actions == [["surrender"]]

    no_surrender = make_rules(allow_surrender=False)
    assert_streams_match(no_surrender, strategy, codes, context="8-8-vs-A-split")
    rec = cardsharp_core.play_card_stream(
        make_core_rules(no_surrender),
        encode_strategy_table(strategy, no_surrender),
        bytes(codes),
    )
    assert rec[0].players[0].actions[0][0] == "split"


def test_split_aces_stand_automatically_even_when_resplitting_allowed():
    """Split aces draw one card each and stand; the state machine's
    stand-only branch makes resplit_aces unreachable (quirk preserved)."""
    rules = make_rules(allow_resplitting=True, resplit_aces=True)
    strategy = BasicStrategy()
    # P A,A vs dealer 9; the split hands draw an ace and a ten.
    codes = [1, 9, 1, 8, 1, 10, 10]
    assert_streams_match(rules, strategy, codes, context="split-aces")
    rec = cardsharp_core.play_card_stream(
        make_core_rules(rules), encode_strategy_table(strategy, rules), bytes(codes)
    )
    player = rec[0].players[0]
    assert len(player.hands) == 2
    assert all(len(h) == 2 for h in player.hands)


def test_dealer_soft_17_draw_chain_differs_by_rule():
    """Dealer A,6 must draw under H17 and stand under S17."""
    strategy = BasicStrategy()
    # P 10,10 stands; dealer A,6.
    codes = [10, 1, 10, 6, 4, 9]
    h17 = make_rules(dealer_hit_soft_17=True)
    s17 = make_rules(dealer_hit_soft_17=False)
    assert_streams_match(h17, strategy, codes, context="h17-draw")
    assert_streams_match(s17, strategy, codes, context="s17-stand")

    rec_h17 = cardsharp_core.play_card_stream(
        make_core_rules(h17), encode_strategy_table(BasicStrategy(), h17), bytes(codes)
    )
    rec_s17 = cardsharp_core.play_card_stream(
        make_core_rules(s17), encode_strategy_table(BasicStrategy(), s17), bytes(codes)
    )
    assert len(rec_h17[0].dealer_cards) > 2
    assert rec_s17[0].dealer_cards == [1, 6]


class _ShoeTracer:
    """Counts shuffle events on the Python shoe via method wrapping."""

    def __init__(self, shoe):
        self.shuffles = 0
        self.mid_round = 0
        orig_shuffle = shoe.shuffle
        orig_mid = shoe._reshuffle_discards_mid_round

        def counting_shuffle():
            self.shuffles += 1
            orig_shuffle()

        def counting_mid():
            self.mid_round += 1
            orig_mid()

        shoe.shuffle = counting_shuffle
        shoe._reshuffle_discards_mid_round = counting_mid


def python_shoe_trace(num_decks, penetration, burn_cards, deals_per_round):
    shoe = Shoe(num_decks=num_decks, penetration=penetration, burn_cards=burn_cards)
    tracer = _ShoeTracer(shoe)  # attached post-construction: init shuffle excluded
    trace = []
    for deals in deals_per_round:
        shoe.begin_round()
        shuffles_before = tracer.shuffles
        for _ in range(deals):
            shoe.deal()
        shoe.end_round()
        trace.append((shuffles_before, tracer.mid_round))
    return trace


@pytest.mark.parametrize(
    "num_decks,penetration,burn,pattern,seed",
    [
        (6, 0.75, 0, "constant-6", 0),
        (6, 0.75, 2, "constant-6", 0),
        (1, 0.5, 0, "constant-5", 0),
        (2, 0.9, 0, "random", 21),
        (6, 0.25, 0, "random", 22),
        (1, 1.0, 0, "constant-30", 0),  # forces mid-round exhaustion
        (1, 0.999, 1, "random-large", 23),
    ],
)
def test_shuffle_timing_parity(num_decks, penetration, burn, pattern, seed):
    """Shuffle epochs depend only on consumption counts, so both shoes must
    shuffle before exactly the same rounds and recycle discards mid-round
    at exactly the same rounds. This is the cut-card-semantics gate that
    card-stream injection cannot reach."""
    rng = random.Random(seed)
    if pattern == "constant-6":
        deals = [6] * 80
    elif pattern == "constant-5":
        deals = [5] * 40
    elif pattern == "constant-30":
        deals = [30] * 10
    elif pattern == "random-large":
        deals = [rng.randint(10, 30) for _ in range(30)]
    else:
        deals = [rng.randint(4, 12) for _ in range(60)]

    py_trace = python_shoe_trace(num_decks, penetration, burn, deals)
    rs_trace = cardsharp_core.trace_shoe(num_decks, penetration, burn, deals, seed=1)
    assert py_trace == [tuple(t) for t in rs_trace], (
        f"shuffle timing diverged for decks={num_decks} pen={penetration} "
        f"burn={burn} pattern={pattern}"
    )
    if pattern == "constant-30":
        assert any(mid > 0 for _, mid in py_trace), "exhaustion case never triggered"
