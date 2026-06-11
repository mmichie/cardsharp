#!/usr/bin/env python
"""Golden card-stream regression corpus for the Rust fast core (beads-i2s.3).

Freezes parity-proven engine behavior as committed data so the core stays
regression-locked against its own verified history after the Python
reference engine retires. Four golden families, replayed exactly by
tests/test_fastsim_golden.py:

- streams:  play_card_stream round records (hands, actions, winners,
            money flow, cards consumed) over seeded fuzz streams and
            crafted adversarial streams, across the supported rule
            surface including counting and conditional settlement.
- batches:  simulate_batch report dicts -- end-to-end shoe machinery the
            stream injection cannot reach (penetration, burn cards, CSM,
            riffle/strip shuffles, multi-shard merges).
- paired:   simulate_paired CRN comparison outputs.
- traces:   trace_shoe shuffle/exhaustion epochs.

Regenerate with:

    uv run python -m cardsharp.tools.golden_corpus

Regeneration is idempotent: on an engine whose semantics are unchanged it
rewrites byte-identical files, so `git diff` after a regen is exactly the
semantic delta. Update policy (also in tests/golden/README.md): goldens
are regenerated only for an INTENDED semantic change, in the same commit,
with the data diff reviewed round by round -- never to silence a failure
that is not understood.
"""

import argparse
import json
import random
from pathlib import Path

from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.strategy import BasicStrategy, CountingStrategy
from cardsharp.fastsim.encoding import (
    CORE_AVAILABLE,
    cardsharp_core,
    encode_counting_config,
    encode_strategy_table,
    make_core_rules,
)

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "tests" / "golden"

# Rank weights for stream generation, mirroring the parity suite's
# distributions: aces and eights hammer splits and surrender fallbacks,
# tens hammer peeks, low cards drive the running count positive.
WEIGHTS = {
    "UNIFORM": [1] * 13,
    "SPLIT_HEAVY": [6, 1, 1, 1, 1, 1, 1, 6, 1, 2, 2, 2, 2],
    "TEN_HEAVY": [3, 1, 1, 1, 1, 2, 2, 2, 1, 4, 4, 4, 4],
    "LOW_HEAVY": [3, 4, 4, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1],
}

# Defaults shared by every config; per-config "rules" entries override.
BASE_RULES: dict = dict(
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


def _stream(
    config_id,
    rules=None,
    weights="UNIFORM",
    seed=0,
    n_streams=20,
    cards_per_stream=70,
    n_players=1,
    bankroll=1000.0,
    always_insure=False,
    counting=False,
    conditional_settlement=False,
    streams=None,
):
    return {
        "config": config_id,
        "rules": rules or {},
        "weights": weights if streams is None else None,
        "seed": seed if streams is None else None,
        "n_streams": n_streams if streams is None else len(streams),
        "cards_per_stream": cards_per_stream if streams is None else None,
        "n_players": n_players,
        "bankroll": bankroll,
        "always_insure": always_insure,
        "counting": counting,
        "conditional_settlement": conditional_settlement,
        "streams": streams,
    }


# The rule surface, frozen. Seeded entries mirror the parity suite's fuzz
# configurations (which proved engine-vs-engine identity on this surface);
# entries with explicit "streams" are the directed adversarial cases.
STREAM_CONFIGS = [
    _stream("base-uniform", weights="UNIFORM", seed=1101),
    _stream("base-splits", weights="SPLIT_HEAVY", seed=1102),
    _stream("base-tens", weights="TEN_HEAVY", seed=1103),
    _stream(
        "resplit-aces-hit",
        rules={"allow_resplitting": True, "resplit_aces": True, "hit_split_aces": True},
        weights="SPLIT_HEAVY",
        seed=1104,
    ),
    _stream(
        "s17-resplit",
        rules={"dealer_hit_soft_17": False, "allow_resplitting": True},
        weights="SPLIT_HEAVY",
        seed=1105,
    ),
    _stream(
        "no-das-double-9-11",
        rules={"allow_double_after_split": False, "double_on": "9-11"},
        weights="SPLIT_HEAVY",
        seed=1106,
    ),
    _stream(
        "double-10-11-no-surrender",
        rules={"double_on": "10-11", "allow_surrender": False},
        weights="UNIFORM",
        seed=1107,
    ),
    _stream(
        "no-peek-tens", rules={"dealer_peek": False}, weights="TEN_HEAVY", seed=1108
    ),
    _stream(
        "no-peek-no-obo",
        rules={"dealer_peek": False, "allow_obo": False},
        weights="TEN_HEAVY",
        seed=1109,
    ),
    _stream(
        "no-peek-insured",
        rules={"dealer_peek": False, "insurance_payout": 3.0},
        weights="TEN_HEAVY",
        seed=1110,
        always_insure=True,
    ),
    _stream(
        "early-surrender-peek",
        rules={"allow_early_surrender": True},
        weights="TEN_HEAVY",
        seed=1111,
    ),
    _stream(
        "early-surrender-no-peek",
        rules={"allow_early_surrender": True, "dealer_peek": False},
        weights="TEN_HEAVY",
        seed=1112,
    ),
    _stream("charlie", rules={"five_card_charlie": True}, weights="UNIFORM", seed=1113),
    _stream("max-splits-1", rules={"max_splits": 1}, weights="SPLIT_HEAVY", seed=1114),
    _stream("one-deck", rules={"num_decks": 1}, weights="UNIFORM", seed=1115),
    _stream("broke-player", weights="SPLIT_HEAVY", seed=1116, bankroll=15.0),
    _stream("one-double-only", weights="SPLIT_HEAVY", seed=1117, bankroll=25.0),
    _stream(
        "three-players",
        weights="UNIFORM",
        seed=1118,
        n_players=3,
        cards_per_stream=130,
    ),
    _stream(
        "two-players-resplit",
        rules={"allow_resplitting": True},
        weights="SPLIT_HEAVY",
        seed=1119,
        n_players=2,
        cards_per_stream=100,
    ),
    _stream(
        "conditional-settlement",
        weights="UNIFORM",
        seed=1120,
        conditional_settlement=True,
    ),
    _stream(
        "conditional-settlement-splits",
        rules={"allow_resplitting": True},
        weights="SPLIT_HEAVY",
        seed=1121,
        conditional_settlement=True,
    ),
    # Counting streams are long so the running count evolves across
    # rounds; the Hi-Lo count, bet ramp, Illustrious 18 deviations, and
    # TC-based insurance all move money here.
    _stream(
        "count-uniform",
        weights="UNIFORM",
        seed=1201,
        counting=True,
        cards_per_stream=120,
    ),
    _stream(
        "count-high-tc",
        weights="LOW_HEAVY",
        seed=1202,
        counting=True,
        cards_per_stream=120,
    ),
    _stream(
        "count-negative-tc",
        weights="TEN_HEAVY",
        seed=1203,
        counting=True,
        cards_per_stream=120,
    ),
    _stream(
        "count-s17",
        rules={"dealer_hit_soft_17": False},
        weights="LOW_HEAVY",
        seed=1204,
        counting=True,
        cards_per_stream=120,
    ),
    _stream(
        "count-no-peek",
        rules={"dealer_peek": False},
        weights="LOW_HEAVY",
        seed=1205,
        counting=True,
        cards_per_stream=120,
    ),
    # Directed adversarial streams from the parity suite's crafted tests.
    _stream(
        "crafted-resplit-chain",
        rules={"allow_resplitting": True},
        streams=[[8, 6, 8, 10, 8, 8, 10, 9, 3, 7, 5, 10, 10, 10, 10, 10]],
    ),
    _stream("crafted-8-8-vs-A-surrender", streams=[[8, 1, 8, 9, 10, 10, 10, 5, 9]]),
    _stream(
        "crafted-8-8-vs-A-split",
        rules={"allow_surrender": False},
        streams=[[8, 1, 8, 9, 10, 10, 10, 5, 9]],
    ),
    _stream(
        "crafted-split-aces",
        rules={"allow_resplitting": True, "resplit_aces": True},
        streams=[[1, 9, 1, 8, 1, 10, 10]],
    ),
    _stream("crafted-h17-soft-17-draw", streams=[[10, 1, 10, 6, 4, 9]]),
    _stream(
        "crafted-s17-soft-17-stand",
        rules={"dealer_hit_soft_17": False},
        streams=[[10, 1, 10, 6, 4, 9]],
    ),
    _stream(
        "crafted-bet-ramp",
        counting=True,
        streams=[[2, 3, 4, 5, 6] * 4 + [10, 10, 10, 10, 10, 10]],
    ),
]


def _batch(
    config_id,
    rules=None,
    n_rounds=40_000,
    seed=0,
    n_players=1,
    counting=False,
    shuffle_type="perfect",
    shuffle_count=None,
    conditional_settlement=False,
    always_insure=False,
):
    return {
        "config": config_id,
        "rules": rules or {},
        "n_rounds": n_rounds,
        "seed": seed,
        "n_players": n_players,
        "counting": counting,
        "shuffle_type": shuffle_type,
        "shuffle_count": shuffle_count,
        "conditional_settlement": conditional_settlement,
        "always_insure": always_insure,
    }


# End-to-end shoe machinery that card-stream injection cannot reach.
# Reports are bit-identical for a given seed regardless of thread count
# (deterministic shards, ordered merges), which is what makes them
# golden-able. The multi-shard config crosses SHARD_ROUNDS to lock the
# shard split and Chan merge path.
BATCH_CONFIGS = [
    _batch("batch-6d-h17-pen075", seed=2101),
    _batch("batch-1d-pen095", rules={"num_decks": 1, "penetration": 0.95}, seed=2102),
    _batch(
        "batch-1d-pen100-exhaustion",
        rules={"num_decks": 1, "penetration": 1.0},
        n_rounds=20_000,
        seed=2103,
    ),
    _batch(
        "batch-2d-s17-pen050",
        rules={"num_decks": 2, "dealer_hit_soft_17": False, "penetration": 0.5},
        seed=2104,
    ),
    _batch("batch-burn-2", rules={"burn_cards": 2}, seed=2105),
    _batch("batch-csm-6d", rules={"use_csm": True}, seed=2106),
    _batch("batch-riffle-default", shuffle_type="riffle", seed=2107),
    _batch("batch-riffle-3", shuffle_type="riffle", shuffle_count=3, seed=2108),
    _batch("batch-strip", shuffle_type="strip", seed=2109),
    _batch("batch-counting-6d", counting=True, seed=2110),
    _batch("batch-counting-csm", counting=True, rules={"use_csm": True}, seed=2111),
    _batch("batch-counting-riffle", counting=True, shuffle_type="riffle", seed=2112),
    _batch("batch-conditional-settlement", conditional_settlement=True, seed=2113),
    _batch("batch-three-players", n_players=3, n_rounds=20_000, seed=2114),
    _batch(
        "batch-no-peek-insured",
        rules={"dealer_peek": False, "insurance_payout": 3.0},
        always_insure=True,
        seed=2115,
    ),
    _batch(
        "batch-no-peek-no-obo-1d",
        rules={"dealer_peek": False, "allow_obo": False, "num_decks": 1},
        seed=2116,
    ),
    _batch(
        "batch-early-surrender-2d",
        rules={"allow_early_surrender": True, "num_decks": 2},
        seed=2117,
    ),
    _batch("batch-charlie", rules={"five_card_charlie": True}, seed=2118),
    _batch(
        "batch-resplit-aces-hit",
        rules={"allow_resplitting": True, "resplit_aces": True, "hit_split_aces": True},
        seed=2119,
    ),
    _batch("batch-multi-shard", n_rounds=600_000, seed=2120),
]


PAIRED_CONFIGS = [
    {
        "config": "paired-h17-vs-s17",
        "rules_a": {},
        "rules_b": {"dealer_hit_soft_17": False},
        "n_rounds": 100_000,
        "seed": 3101,
    },
    {
        "config": "paired-das-vs-no-das",
        "rules_a": {"num_decks": 2},
        "rules_b": {"num_decks": 2, "allow_double_after_split": False},
        "n_rounds": 60_000,
        "seed": 3102,
    },
    {
        "config": "paired-identical",
        "rules_a": {},
        "rules_b": {},
        "n_rounds": 30_000,
        "seed": 3103,
    },
]


# (num_decks, penetration, burn_cards, deals pattern, pattern seed). The
# constant-30 single-deck case forces mid-round exhaustion recycling.
TRACE_CONFIGS = [
    {
        "config": "trace-6d-pen075",
        "num_decks": 6,
        "penetration": 0.75,
        "burn": 0,
        "pattern": "constant-6",
        "seed": 0,
    },
    {
        "config": "trace-6d-pen075-burn2",
        "num_decks": 6,
        "penetration": 0.75,
        "burn": 2,
        "pattern": "constant-6",
        "seed": 0,
    },
    {
        "config": "trace-1d-pen050",
        "num_decks": 1,
        "penetration": 0.5,
        "burn": 0,
        "pattern": "constant-5",
        "seed": 0,
    },
    {
        "config": "trace-2d-pen090",
        "num_decks": 2,
        "penetration": 0.9,
        "burn": 0,
        "pattern": "random",
        "seed": 4121,
    },
    {
        "config": "trace-6d-pen025",
        "num_decks": 6,
        "penetration": 0.25,
        "burn": 0,
        "pattern": "random",
        "seed": 4122,
    },
    {
        "config": "trace-1d-exhaustion",
        "num_decks": 1,
        "penetration": 1.0,
        "burn": 0,
        "pattern": "constant-30",
        "seed": 0,
    },
    {
        "config": "trace-1d-pen0999-burn1",
        "num_decks": 1,
        "penetration": 0.999,
        "burn": 1,
        "pattern": "random-large",
        "seed": 4123,
    },
]


def make_rules(overrides):
    kwargs = dict(BASE_RULES)
    kwargs.update(overrides)
    return Rules(**kwargs)


def build_strategy(rules, counting):
    """Fresh strategy per replay: the counting strategy's count is stateful."""
    if counting:
        return CountingStrategy(num_decks=rules.num_decks)
    return BasicStrategy()


def generate_streams(cfg):
    """The card streams for a config: explicit, or seeded fuzz."""
    if cfg["streams"] is not None:
        return [list(s) for s in cfg["streams"]]
    rng = random.Random(cfg["seed"])
    weights = WEIGHTS[cfg["weights"]]
    return [
        rng.choices(range(1, 14), weights=weights, k=cfg["cards_per_stream"])
        for _ in range(cfg["n_streams"])
    ]


def record_to_dict(record):
    """Serialize a RoundRecord with an explicit field list.

    Explicit so that future additive fields on the record classes (e.g.
    diagnostics) do not churn the corpus: goldens lock behavior, not the
    record schema.
    """
    return {
        "dealer": list(record.dealer_cards),
        "consumed": record.cards_consumed,
        "conditional_net": record.conditional_net,
        "players": [
            {
                "hands": [list(h) for h in p.hands],
                "actions": [list(a) for a in p.actions],
                "winners": list(p.winners),
                "bets": list(p.bets),
                "original_bets": list(p.original_bets),
                "net": p.net,
                "initial_bet": p.initial_bet,
                "total_bet": p.total_bet,
                "blackjack": p.blackjack,
                "money": p.money,
            }
            for p in record.players
        ],
    }


def replay_stream(cfg, cards):
    """Play one stored card stream through the core; return round dicts."""
    rules = make_rules(cfg["rules"])
    strategy = build_strategy(rules, cfg["counting"])
    table = encode_strategy_table(strategy, rules)
    counting_cfg = encode_counting_config(strategy) if cfg["counting"] else None
    records = cardsharp_core.play_card_stream(
        make_core_rules(rules),
        table,
        bytes(cards),
        n_players=cfg["n_players"],
        initial_bankroll=cfg["bankroll"],
        always_insure=cfg["always_insure"],
        counting=counting_cfg,
        conditional_settlement=cfg["conditional_settlement"],
    )
    return [record_to_dict(r) for r in records]


def run_batch(cfg):
    """Run one simulate_batch config; return the report dict (plain types)."""
    rules = make_rules(cfg["rules"])
    strategy = build_strategy(rules, cfg["counting"])
    table = encode_strategy_table(strategy, rules)
    counting_cfg = encode_counting_config(strategy) if cfg["counting"] else None
    report = cardsharp_core.simulate_batch(
        make_core_rules(rules),
        table,
        cfg["n_rounds"],
        seed=cfg["seed"],
        n_players=cfg["n_players"],
        always_insure=cfg["always_insure"],
        counting=counting_cfg,
        shuffle_type=cfg["shuffle_type"],
        shuffle_count=cfg["shuffle_count"],
        conditional_settlement=cfg["conditional_settlement"],
    )
    return {k: report[k] for k in sorted(report.keys())}


def run_paired(cfg):
    rules_a = make_rules(cfg["rules_a"])
    rules_b = make_rules(cfg["rules_b"])
    strategy = BasicStrategy()
    out = cardsharp_core.simulate_paired(
        make_core_rules(rules_a),
        encode_strategy_table(strategy, rules_a),
        make_core_rules(rules_b),
        encode_strategy_table(BasicStrategy(), rules_b),
        cfg["n_rounds"],
        seed=cfg["seed"],
    )
    return {
        "a": {k: out["a"][k] for k in sorted(out["a"].keys())},
        "b": {k: out["b"][k] for k in sorted(out["b"].keys())},
        "diff_n": out["diff_n"],
        "diff_mean": out["diff_mean"],
        "diff_M2": out["diff_M2"],
    }


def trace_deals(cfg):
    rng = random.Random(cfg["seed"])
    pattern = cfg["pattern"]
    if pattern == "constant-6":
        return [6] * 80
    if pattern == "constant-5":
        return [5] * 40
    if pattern == "constant-30":
        return [30] * 10
    if pattern == "random-large":
        return [rng.randint(10, 30) for _ in range(30)]
    return [rng.randint(4, 12) for _ in range(60)]


def run_trace(cfg, deals):
    trace = cardsharp_core.trace_shoe(
        cfg["num_decks"], cfg["penetration"], cfg["burn"], deals, seed=1
    )
    return [list(t) for t in trace]


def _dumps(obj):
    # sort_keys + allow_nan=False: stable bytes, and a NaN anywhere in a
    # report is a generation failure, never silently committed.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_corpus(root=GOLDEN_DIR):
    if not CORE_AVAILABLE:
        raise RuntimeError(
            "cardsharp_core is required to generate goldens (uv sync --extra fast)"
        )

    streams_dir = root / "streams"
    streams_dir.mkdir(parents=True, exist_ok=True)

    total_rounds = 0
    manifest_streams = {}
    written = set()
    for cfg in STREAM_CONFIGS:
        lines = [_dumps({"header": {k: v for k, v in cfg.items() if k != "streams"}})]
        config_rounds = 0
        for i, cards in enumerate(generate_streams(cfg)):
            lines.append(_dumps({"stream": i, "cards": cards}))
            for j, round_dict in enumerate(replay_stream(cfg, cards)):
                lines.append(_dumps({"stream": i, "round": j, "record": round_dict}))
                config_rounds += 1
        path = streams_dir / f"{cfg['config']}.jsonl"
        path.write_text("\n".join(lines) + "\n")
        written.add(path.name)
        manifest_streams[cfg["config"]] = config_rounds
        total_rounds += config_rounds
        print(f"  streams/{cfg['config']}.jsonl: {config_rounds} rounds")

    for stale in sorted(set(p.name for p in streams_dir.glob("*.jsonl")) - written):
        (streams_dir / stale).unlink()
        print(f"  removed stale streams/{stale}")

    batches = {
        cfg["config"]: {"params": cfg, "report": run_batch(cfg)}
        for cfg in BATCH_CONFIGS
    }
    (root / "batches.json").write_text(
        json.dumps(batches, sort_keys=True, indent=1, allow_nan=False) + "\n"
    )
    print(f"  batches.json: {len(batches)} reports")

    paired = {
        cfg["config"]: {"params": cfg, "result": run_paired(cfg)}
        for cfg in PAIRED_CONFIGS
    }
    (root / "paired.json").write_text(
        json.dumps(paired, sort_keys=True, indent=1, allow_nan=False) + "\n"
    )
    print(f"  paired.json: {len(paired)} comparisons")

    traces = {}
    for cfg in TRACE_CONFIGS:
        deals = trace_deals(cfg)
        traces[cfg["config"]] = {
            "params": cfg,
            "deals": deals,
            "trace": run_trace(cfg, deals),
        }
    (root / "shoe_traces.json").write_text(
        json.dumps(traces, sort_keys=True, indent=1, allow_nan=False) + "\n"
    )
    print(f"  shoe_traces.json: {len(traces)} traces")

    manifest = {
        "engine_version": cardsharp_core.engine_version(),
        "stream_rounds": manifest_streams,
        "total_stream_rounds": total_rounds,
        "batch_configs": len(batches),
        "paired_configs": len(paired),
        "trace_configs": len(traces),
    }
    (root / "MANIFEST.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=1) + "\n"
    )
    print(
        f"  MANIFEST.json: engine {manifest['engine_version']}, "
        f"{total_rounds} stream rounds"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate the golden card-stream regression corpus."
    )
    parser.add_argument(
        "--out",
        default=str(GOLDEN_DIR),
        help="corpus directory (default: tests/golden)",
    )
    args = parser.parse_args()
    print(f"writing corpus to {args.out}")
    write_corpus(Path(args.out))


if __name__ == "__main__":
    main()
