"""Tests for the optional cardsharp_core Rust extension.

The extension is an optional accelerator built with `uv sync --extra fast`
(requires a Rust toolchain). When it is not installed these tests skip,
so the pure-Python path stays green without it.

The card-stream tests here are a Phase 3 (beads-9ro.3) self-check; the
comprehensive parity suite is Phase 5 (beads-9ro.5).
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
from cardsharp.blackjack.stats import SimulationStats  # noqa: E402
from cardsharp.blackjack.strategy import BasicStrategy  # noqa: E402
from cardsharp.common.card import Card, Rank, Suit  # noqa: E402
from cardsharp.common.io_interface import DummyIOInterface  # noqa: E402
from cardsharp.common.shoe import Shoe  # noqa: E402
from cardsharp.fastsim import encode_strategy_table, make_core_rules  # noqa: E402

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
    """Test double for exercising the insurance machinery on both engines."""

    def decide_insurance(self, player) -> bool:
        return True


def python_stream(rules, strategy, codes):
    """Play rounds from a fixed card sequence through the Python engine.

    The pre-shuffled shoe is overwritten with the injected sequence and its
    reshuffle point pushed past the end so no shuffle can occur; the stream
    ends when a round cannot complete.
    """
    shoe = Shoe(num_decks=rules.num_decks, penetration=1.0)
    shoe.cards = [Card(Suit.SPADES, Rank(c)) for c in codes]
    shoe.next_card_index = 0
    shoe.total_cards = len(shoe.cards)
    shoe.reshuffle_point = len(shoe.cards) + 10_000
    rounds = []
    while shoe.total_cards - shoe.next_card_index >= 4:
        before = shoe.next_card_index
        try:
            net, total, initial, report, shoe = play_game(
                rules, DummyIOInterface(), ["P"], strategy, shoe, 1000
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


def rust_stream(rules, strategy, codes, always_insure=False):
    table = encode_strategy_table(strategy, rules)
    records = cardsharp_core.play_card_stream(
        make_core_rules(rules), table, bytes(codes), always_insure=always_insure
    )
    return [
        {
            "net": r.players[0].net,
            "total": r.players[0].total_bet,
            "initial": r.players[0].initial_bet,
            "wins": sum(1 for w in r.players[0].winners if w == "player"),
            "losses": sum(1 for w in r.players[0].winners if w == "dealer"),
            "draws": sum(1 for w in r.players[0].winners if w == "draw"),
            "consumed": r.cards_consumed,
        }
        for r in records
    ]


def test_engine_version_reports_crate_version():
    version = cardsharp_core.engine_version()
    assert isinstance(version, str)
    assert version.count(".") == 2


def test_ping_round_trips_arguments():
    assert cardsharp_core.ping(41) == 42
    assert cardsharp_core.ping(0) == 1


def test_player_blackjack_pays_three_to_two():
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    # Deal order: player, dealer, player, dealer.
    records = cardsharp_core.play_card_stream(
        make_core_rules(rules), table, bytes([1, 5, 13, 9])
    )
    assert len(records) == 1
    p = records[0].players[0]
    assert p.blackjack
    assert p.net == 15.0  # 3:2 on a 10 bet
    assert p.winners == ["player"]
    assert p.actions == [[]]  # settled before the players' turn
    assert records[0].cards_consumed == 4
    assert records[0].dealer_cards == [5, 9]  # dealer never draws


def test_dealer_blackjack_with_peek_ends_round():
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    records = cardsharp_core.play_card_stream(
        make_core_rules(rules), table, bytes([10, 1, 9, 10])
    )
    p = records[0].players[0]
    assert p.net == -10.0
    assert p.winners == ["dealer"]
    assert records[0].cards_consumed == 4


def test_insurance_pays_two_to_one_on_dealer_blackjack():
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    records = cardsharp_core.play_card_stream(
        make_core_rules(rules), table, bytes([10, 1, 9, 10]), always_insure=True
    )
    p = records[0].players[0]
    # Lost 10 (bet) and 5 (insurance), won 15 (insurance pays 2:1 plus stake).
    assert p.net == 0.0
    assert p.total_bet == 15.0


def test_sixteen_versus_ten_surrenders():
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    records = cardsharp_core.play_card_stream(
        make_core_rules(rules), table, bytes([10, 10, 6, 7])
    )
    p = records[0].players[0]
    assert p.actions == [["surrender"]]
    assert p.net == -5.0
    # Dealer reveals but does not draw on a dead round.
    assert records[0].dealer_cards == [10, 7]


def test_eleven_versus_six_doubles():
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    # P: 6,5 = 11 vs dealer 6. Double draws 9 -> 20. Dealer 6,10 = 16
    # draws 8 -> 24, bust.
    records = cardsharp_core.play_card_stream(
        make_core_rules(rules), table, bytes([6, 6, 5, 10, 9, 8])
    )
    p = records[0].players[0]
    assert p.actions == [["double"]]
    assert p.net == 20.0
    assert p.total_bet == 20.0
    assert records[0].cards_consumed == 6


def test_split_eights_versus_six():
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    # P: 8,8 vs dealer 6 -> split. Hand 1: 8,10 = 18 stand. Hand 2:
    # 8,9 = 17 stand. Dealer 6,10,2 = 18.
    records = cardsharp_core.play_card_stream(
        make_core_rules(rules), table, bytes([8, 6, 8, 10, 10, 9, 2])
    )
    p = records[0].players[0]
    assert len(p.hands) == 2
    assert p.actions[0][0] == "split"
    assert p.hands[0] == [8, 10]
    assert p.hands[1] == [8, 9]
    assert p.winners == ["draw", "dealer"]
    assert p.net == -10.0  # push on 18, lose 17 vs 18


def test_no_peek_both_blackjacks_push():
    rules = make_rules(dealer_peek=False)
    table = encode_strategy_table(BasicStrategy(), rules)
    records = cardsharp_core.play_card_stream(
        make_core_rules(rules), table, bytes([1, 1, 13, 13])
    )
    p = records[0].players[0]
    assert p.blackjack
    assert p.winners == ["draw"]
    assert p.net == 0.0


@pytest.mark.parametrize(
    "rules_overrides,always_insure,trials,seed",
    [
        ({}, False, 300, 11),
        ({"dealer_peek": False}, False, 200, 22),
        ({"dealer_peek": False}, True, 150, 33),
        ({"dealer_hit_soft_17": False, "allow_resplitting": True}, False, 200, 44),
    ],
)
def test_card_stream_parity_fuzz(rules_overrides, always_insure, trials, seed):
    """Both engines must produce identical money flow, outcomes, and card
    consumption for identical card streams."""
    rules = make_rules(**rules_overrides)
    strategy = AlwaysInsureStrategy() if always_insure else BasicStrategy()
    rng = random.Random(seed)
    compared = 0
    for trial in range(trials):
        codes = [rng.randint(1, 13) for _ in range(60)]
        py = python_stream(rules, strategy, codes)
        rs = rust_stream(rules, strategy, codes, always_insure=always_insure)
        # The Python shoe recycles discards at exhaustion while the stream
        # stops, so only the common prefix is comparable.
        for i in range(min(len(py), len(rs))):
            assert py[i] == rs[i], (
                f"trial {trial} round {i} diverged: {py[i]} != {rs[i]} "
                f"(codes={codes})"
            )
            compared += 1
    assert compared > trials  # sanity: streams produced multiple rounds


def test_simulate_batch_is_deterministic_per_seed():
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    core_rules = make_core_rules(rules)
    a = cardsharp_core.simulate_batch(core_rules, table, 10_000, seed=5)
    b = cardsharp_core.simulate_batch(core_rules, table, 10_000, seed=5)
    c = cardsharp_core.simulate_batch(core_rules, table, 10_000, seed=6)
    assert a == b
    assert a != c


def test_simulate_batch_results_are_thread_count_invariant():
    """Shards are self-contained and merged in shard order, so any thread
    count must produce bit-identical aggregates for a given seed. Uses
    600k rounds so the batch spans multiple shards."""
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    core_rules = make_core_rules(rules)
    one = cardsharp_core.simulate_batch(core_rules, table, 600_000, seed=9, threads=1)
    two = cardsharp_core.simulate_batch(core_rules, table, 600_000, seed=9, threads=2)
    all_cores = cardsharp_core.simulate_batch(core_rules, table, 600_000, seed=9)
    assert one == two == all_cores
    assert one["n_rounds"] == 600_000


def test_counting_results_are_thread_count_invariant():
    """The counter is per-shard, so thread count cannot change results."""
    from cardsharp.blackjack.strategy import CountingStrategy
    from cardsharp.fastsim import encode_counting_config

    rules = make_rules()
    strategy = CountingStrategy(num_decks=6)
    table = encode_strategy_table(strategy, rules)
    counting = encode_counting_config(strategy)
    core_rules = make_core_rules(rules)
    one = cardsharp_core.simulate_batch(
        core_rules, table, 600_000, seed=13, threads=1, counting=counting
    )
    many = cardsharp_core.simulate_batch(
        core_rules, table, 600_000, seed=13, counting=counting
    )
    assert one == many
    # The ramp produces variable bets, so mean initial bet exceeds the
    # table minimum.
    assert one["bet_mean"] > 10.0


def test_counting_house_edge_beats_flat_basic():
    """Hi-Lo with the 1x-20x ramp and Illustrious 18 must show a clear
    player improvement over flat basic strategy (~+0.63% house edge at
    these rules). Loose statistical band; exact behavior is pinned by
    the parity suite."""
    from cardsharp.blackjack.strategy import CountingStrategy
    from cardsharp.fastsim import run_fast_batch

    rules = make_rules()
    stats = run_fast_batch(rules, CountingStrategy(num_decks=6), 2_000_000, seed=77)
    he = -stats.net_sum / stats.bet_sum
    assert -0.04 < he < 0.004, f"counting house edge {he:.4%} outside expected band"


def test_csm_house_edge_matches_fresh_shoe_band():
    """A CSM continuously recycles discards, so there is no cut-card
    effect: its house edge must sit at the fresh-shoe value. Loose
    multi-sigma band; the CSM mechanics themselves are unit-tested in
    the crate (composition conservation, refill thresholds)."""
    fresh = make_rules(penetration=0.01)
    csm = make_rules(use_csm=True)
    table = encode_strategy_table(BasicStrategy(), fresh)
    a = SimulationStats.from_dict(
        cardsharp_core.simulate_batch(make_core_rules(fresh), table, 2_000_000, seed=31)
    )
    b = SimulationStats.from_dict(
        cardsharp_core.simulate_batch(make_core_rules(csm), table, 2_000_000, seed=32)
    )
    he_fresh = -a.net_sum / a.bet_sum
    he_csm = -b.net_sum / b.bet_sum
    assert (
        abs(he_fresh - he_csm) < 0.0035
    ), f"CSM HE {he_csm:.4%} vs fresh-shoe HE {he_fresh:.4%}"


def test_realistic_shuffles_house_edge_matches_perfect_band():
    """Four GSR riffles (or six strips) are not perfectly random, but for
    a fixed table strategy the EV effect is far below this resolution:
    a material gap means the shuffle implementation is broken."""
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    core_rules = make_core_rules(rules)
    perfect = SimulationStats.from_dict(
        cardsharp_core.simulate_batch(core_rules, table, 2_000_000, seed=41)
    )
    he_perfect = -perfect.net_sum / perfect.bet_sum
    for shuffle_type in ("riffle", "strip"):
        s = SimulationStats.from_dict(
            cardsharp_core.simulate_batch(
                core_rules, table, 2_000_000, seed=42, shuffle_type=shuffle_type
            )
        )
        he = -s.net_sum / s.bet_sum
        assert (
            abs(he - he_perfect) < 0.0035
        ), f"{shuffle_type} HE {he:.4%} vs perfect {he_perfect:.4%}"


def test_conditional_settlement_is_unbiased_and_reduces_variance():
    """Same seed with the flag on and off plays IDENTICAL physical rounds
    (settlement consumes no randomness), so the two estimator means can
    differ only by the dealer noise that conditioning averaged out --
    near zero with small variance -- while the recorded per-round
    variance must strictly drop."""
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    core_rules = make_core_rules(rules)
    plain = cardsharp_core.simulate_batch(core_rules, table, 2_000_000, seed=88)
    rb = cardsharp_core.simulate_batch(
        core_rules, table, 2_000_000, seed=88, conditional_settlement=True
    )
    he_plain = -plain["net_sum"] / plain["bet_sum"]
    he_rb = -rb["net_sum"] / rb["bet_sum"]
    assert (
        abs(he_rb - he_plain) < 0.002
    ), f"RB mean {he_rb:.4%} vs plain {he_plain:.4%} on identical rounds"
    var_plain = plain["net_M2"] / (plain["n_rounds"] - 1)
    var_rb = rb["net_M2"] / (rb["n_rounds"] - 1)
    assert (
        var_rb < var_plain * 0.95
    ), f"no variance reduction: {var_rb:.3f} vs {var_plain:.3f}"


def test_conditional_settlement_requires_peek_and_non_csm():
    table = encode_strategy_table(BasicStrategy(), make_rules())
    for bad in (make_rules(dealer_peek=False), make_rules(use_csm=True)):
        with pytest.raises(ValueError, match="conditional_settlement"):
            cardsharp_core.simulate_batch(
                make_core_rules(bad),
                table,
                100,
                seed=1,
                conditional_settlement=True,
            )


def test_conditional_net_matches_hand_computation():
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    core_rules = make_core_rules(rules)

    # Player 10,10 = 20 stands; dealer 10,6 = 16 must hit. Exactly two
    # cards remain in the stream: a 5 (dealer makes 21, player loses) and
    # a ten (dealer busts, player wins 20). Expected payout = 10, so the
    # conditional net is 0 while the realized net is -10 (the 5 comes
    # first).
    records = cardsharp_core.play_card_stream(
        core_rules,
        table,
        bytes([10, 10, 10, 6, 5, 10]),
        conditional_settlement=True,
        max_rounds=1,
    )
    r = records[0]
    assert r.players[0].net == -10.0
    assert r.conditional_net == 0.0

    # Pat dealer: nothing to average, conditional equals realized exactly.
    records = cardsharp_core.play_card_stream(
        core_rules,
        table,
        bytes([10, 9, 10, 9]),
        conditional_settlement=True,
    )
    r = records[0]
    assert r.conditional_net == r.players[0].net == 10.0


def test_paired_crn_identical_variants_diff_is_exactly_zero():
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    core_rules = make_core_rules(rules)
    report = cardsharp_core.simulate_paired(
        core_rules, table, core_rules, table, 50_000, seed=5
    )
    assert report["diff_mean"] == 0.0
    assert report["diff_M2"] == 0.0
    assert report["a"] == report["b"]


def test_paired_crn_h17_s17_delta_and_tightness():
    """H17 vs S17 differ by ~20bp; CRN pairing must recover that delta
    with a CI several times tighter than independent runs of the same
    budget would give."""
    import math

    h17, s17 = make_rules(dealer_hit_soft_17=True), make_rules(dealer_hit_soft_17=False)
    strategy = BasicStrategy()
    report = cardsharp_core.simulate_paired(
        make_core_rules(h17),
        encode_strategy_table(BasicStrategy(), h17),
        make_core_rules(s17),
        encode_strategy_table(strategy, s17),
        400_000,
        seed=12,
    )
    n = report["diff_n"]
    diff_mean = report["diff_mean"]
    diff_se = math.sqrt(report["diff_M2"] / (n - 1) / n)
    assert 0.0010 < diff_mean < 0.0030, f"H17-S17 delta {diff_mean:.4%}"
    assert diff_mean - 4 * diff_se > 0, "delta should be clearly resolved"

    # Tightness: paired SE vs the SE of a difference of independent runs.
    var_a = report["a"]["net_M2"] / (n - 1) / (report["a"]["bet_mean"] ** 2)
    var_b = report["b"]["net_M2"] / (n - 1) / (report["b"]["bet_mean"] ** 2)
    independent_se = math.sqrt((var_a + var_b) / n)
    assert (
        independent_se / diff_se > 5
    ), f"CRN only {independent_se / diff_se:.1f}x tighter"


def test_simulate_batch_house_edge_in_plausible_band():
    """Loose 4-sigma guard against gross engine breakage (the tight
    statistical gate is beads-9ro.6)."""
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    report = cardsharp_core.simulate_batch(
        make_core_rules(rules), table, 2_000_000, seed=99
    )
    stats = SimulationStats.from_dict(report)
    he, lo, hi, half = stats.house_edge_with_ci()
    assert report["n_rounds"] == 2_000_000
    # 6-deck H17 DAS LS basic strategy sits near 0.65%.
    assert 0.0030 < he < 0.0100, f"house edge {he:.4%} outside plausible band"


# ---------------------------------------------------------------------------
# Per-deal accumulator and first_cards (beads-i2s.4)


def _decode_deal_index(idx):
    return idx // 100 + 1, (idx // 10) % 10 + 1, idx % 10 + 1


def test_first_cards_survive_splits_surrender_and_blackjack():
    """first_cards must record the deal as dealt, not the reshaped hands:
    it is the player's half of the per-deal key."""
    rules = make_rules(allow_resplitting=True)
    table = encode_strategy_table(BasicStrategy(), rules)

    # 8,8 vs 6 splits into two hands; first_cards stays (8, 8).
    rec = cardsharp_core.play_card_stream(
        make_core_rules(rules), table, bytes([8, 6, 8, 10, 5, 9, 10, 10, 10])
    )
    player = rec[0].players[0]
    assert player.first_cards == [8, 8]
    assert len(player.hands) >= 2

    # 10,6 vs 10 surrenders; the hand is untouched but the key must match.
    rec = cardsharp_core.play_card_stream(
        make_core_rules(rules), table, bytes([10, 10, 6, 5, 10, 10])
    )
    player = rec[0].players[0]
    assert player.actions == [["surrender"]]
    assert player.first_cards == [10, 6]

    # Player blackjack: ace-ten recorded in deal order.
    rec = cardsharp_core.play_card_stream(
        make_core_rules(rules), table, bytes([1, 9, 13, 5, 10, 8])
    )
    player = rec[0].players[0]
    assert player.blackjack
    assert player.first_cards == [1, 13]


def test_per_deal_cells_are_complete_and_consistent():
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    report = cardsharp_core.simulate_batch(
        make_core_rules(rules), table, 50_000, seed=421, per_deal=True
    )
    cells = report["per_deal"]
    assert len(cells) == 1000

    # Every round lands in exactly one cell, and only in the legal
    # lo <= hi triangle.
    assert sum(n for n, _, _ in cells) == 50_000
    for idx, (n, _, _) in enumerate(cells):
        lo, hi, _up = _decode_deal_index(idx)
        if lo > hi:
            assert n == 0

    # Flat bets: the ratio-of-sums house edge equals the per-round mean
    # of X = net/initial, so the cells must reproduce the report's edge
    # (different summation order: tolerance at float-noise scale).
    sum_x = sum(s for _, s, _ in cells)
    he_cells = -sum_x / 50_000
    he_report = -report["net_sum"] / report["bet_sum"]
    assert abs(he_cells - he_report) < 1e-12

    # All ten-class pairs collapse into (10, 10): four times the weight
    # of any single-rank pair, so it must dominate pair cells.
    ten_ten = sum(cells[((10 - 1) * 10 + (10 - 1)) * 10 + up][0] for up in range(10))
    assert ten_ten / 50_000 > 0.05


def test_per_deal_is_deterministic_and_thread_invariant():
    """Cells merge in shard order, so the table is a pure function of
    (seed, n_rounds, config) -- two shards exercise the merge path."""
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    runs = [
        cardsharp_core.simulate_batch(
            make_core_rules(rules),
            table,
            300_000,
            seed=77,
            threads=threads,
            per_deal=True,
        )["per_deal"]
        for threads in (1, 2, 1)
    ]
    assert runs[0] == runs[1] == runs[2]


def test_per_deal_requires_single_player_and_defaults_off():
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    with pytest.raises(ValueError, match="per_deal requires n_players=1"):
        cardsharp_core.simulate_batch(
            make_core_rules(rules), table, 100, seed=1, n_players=2, per_deal=True
        )
    report = cardsharp_core.simulate_batch(make_core_rules(rules), table, 100, seed=1)
    assert "per_deal" not in report


def test_per_deal_composes_with_conditional_settlement():
    """With settlement on, X is the Rao-Blackwellized net: totals still
    cover every round and the cells reproduce the report's (conditional)
    financial sums."""
    rules = make_rules()
    table = encode_strategy_table(BasicStrategy(), rules)
    report = cardsharp_core.simulate_batch(
        make_core_rules(rules),
        table,
        50_000,
        seed=88,
        per_deal=True,
        conditional_settlement=True,
    )
    cells = report["per_deal"]
    assert sum(n for n, _, _ in cells) == 50_000
    he_cells = -sum(s for _, s, _ in cells) / 50_000
    he_report = -report["net_sum"] / report["bet_sum"]
    assert abs(he_cells - he_report) < 1e-12
