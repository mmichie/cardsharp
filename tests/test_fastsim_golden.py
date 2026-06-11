"""Golden card-stream regression corpus replay (beads-i2s.3).

Replays the committed corpus in tests/golden/ through the Rust core and
asserts EXACT equality with the frozen outputs: every hand, action,
winner, bet, net, card consumed, batch report field, paired-comparison
moment, and shuffle epoch. This regression-locks the engine against its
own parity-proven history without needing the Python reference engine
alive.

A failure here means current engine behavior differs from the committed
goldens. If the change is unintended, fix the engine. If it is an
intended semantic change, regenerate the corpus in the same commit and
review the data diff round by round:

    uv run python -m cardsharp.tools.golden_corpus

See tests/golden/README.md for the full update policy.
"""

import json

import pytest

pytest.importorskip(
    "cardsharp_core",
    reason="cardsharp-core extension not built (uv sync --extra fast)",
)

from cardsharp.tools.golden_corpus import (  # noqa: E402
    BATCH_CONFIGS,
    GOLDEN_DIR,
    PAIRED_CONFIGS,
    STREAM_CONFIGS,
    TRACE_CONFIGS,
    replay_stream,
    run_batch,
    run_paired,
    run_trace,
)

_STREAM_IDS = [c["config"] for c in STREAM_CONFIGS]
_BATCH_IDS = [c["config"] for c in BATCH_CONFIGS]
_PAIRED_IDS = [c["config"] for c in PAIRED_CONFIGS]
_TRACE_IDS = [c["config"] for c in TRACE_CONFIGS]


def _load_stream_file(config_id):
    path = GOLDEN_DIR / "streams" / f"{config_id}.jsonl"
    assert path.exists(), (
        f"golden file missing: {path} -- the corpus is committed data; "
        f"regenerate with `uv run python -m cardsharp.tools.golden_corpus` "
        f"and commit the result"
    )
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    header = lines[0]["header"]
    cards = {}
    rounds = {}
    for line in lines[1:]:
        if "cards" in line:
            cards[line["stream"]] = line["cards"]
        else:
            rounds.setdefault(line["stream"], []).append(line)
    for stream_rounds in rounds.values():
        stream_rounds.sort(key=lambda r: r["round"])
    return header, cards, rounds


@pytest.fixture(scope="module")
def stream_configs_by_id():
    return {c["config"]: c for c in STREAM_CONFIGS}


@pytest.mark.parametrize("config_id", _STREAM_IDS)
def test_stream_golden(config_id, stream_configs_by_id):
    cfg = stream_configs_by_id[config_id]
    header, cards, stored_rounds = _load_stream_file(config_id)

    # Config drift gate: the in-code config must match the one the file
    # was generated from, or the replay below would test the wrong thing.
    expected_header = {k: v for k, v in cfg.items() if k != "streams"}
    assert header == expected_header, (
        f"{config_id}: tool config differs from the committed header -- "
        f"regenerate the corpus"
    )

    assert len(cards) == cfg["n_streams"]
    for i in sorted(cards):
        replayed = replay_stream(cfg, cards[i])
        stored = stored_rounds.get(i, [])
        assert len(replayed) == len(stored), (
            f"{config_id} stream {i}: {len(replayed)} rounds replayed, "
            f"{len(stored)} in the golden file"
        )
        for j, (fresh, golden) in enumerate(zip(replayed, stored)):
            assert fresh == golden["record"], (
                f"{config_id} stream {i} round {j} diverged from golden:\n"
                f"  fresh={fresh}\n  golden={golden['record']}\n"
                f"  cards={cards[i]}"
            )


@pytest.fixture(scope="module")
def golden_batches():
    return json.loads((GOLDEN_DIR / "batches.json").read_text())


@pytest.mark.parametrize("config_id", _BATCH_IDS)
def test_batch_golden(config_id, golden_batches):
    cfg = next(c for c in BATCH_CONFIGS if c["config"] == config_id)
    entry = golden_batches[config_id]
    assert entry["params"] == cfg, (
        f"{config_id}: tool config differs from committed params -- "
        f"regenerate the corpus"
    )
    fresh = run_batch(cfg)
    assert fresh == entry["report"], (
        f"{config_id}: simulate_batch report diverged from golden\n"
        f"  fresh={fresh}\n  golden={entry['report']}"
    )


@pytest.fixture(scope="module")
def golden_paired():
    return json.loads((GOLDEN_DIR / "paired.json").read_text())


@pytest.mark.parametrize("config_id", _PAIRED_IDS)
def test_paired_golden(config_id, golden_paired):
    cfg = next(c for c in PAIRED_CONFIGS if c["config"] == config_id)
    entry = golden_paired[config_id]
    assert entry["params"] == cfg
    fresh = run_paired(cfg)
    assert (
        fresh == entry["result"]
    ), f"{config_id}: simulate_paired result diverged from golden"


@pytest.fixture(scope="module")
def golden_traces():
    return json.loads((GOLDEN_DIR / "shoe_traces.json").read_text())


@pytest.mark.parametrize("config_id", _TRACE_IDS)
def test_trace_golden(config_id, golden_traces):
    cfg = next(c for c in TRACE_CONFIGS if c["config"] == config_id)
    entry = golden_traces[config_id]
    assert entry["params"] == cfg
    fresh = run_trace(cfg, entry["deals"])
    assert (
        fresh == entry["trace"]
    ), f"{config_id}: shuffle/exhaustion epochs diverged from golden"


def test_corpus_is_complete():
    """Every config has a file and every file has a config: stale or
    missing golden data fails loudly instead of silently shrinking
    coverage."""
    stream_files = {p.stem for p in (GOLDEN_DIR / "streams").glob("*.jsonl")}
    assert stream_files == set(_STREAM_IDS)
    batches = json.loads((GOLDEN_DIR / "batches.json").read_text())
    assert set(batches) == set(_BATCH_IDS)
    paired = json.loads((GOLDEN_DIR / "paired.json").read_text())
    assert set(paired) == set(_PAIRED_IDS)
    traces = json.loads((GOLDEN_DIR / "shoe_traces.json").read_text())
    assert set(traces) == set(_TRACE_IDS)
    assert (GOLDEN_DIR / "MANIFEST.json").exists()


def test_corpus_locks_interesting_behavior():
    """The corpus must actually contain the behavior it claims to lock:
    splits, doubles, surrenders, insurance, blackjacks, charlies,
    multi-hand rounds, conditional nets, and ramped counting bets. Guards
    against a regenerated corpus quietly degenerating into trivial
    rounds."""
    seen_actions = set()
    max_hands = 0
    saw_blackjack = saw_conditional = saw_ramped_bet = saw_insurance = False
    for config_id in _STREAM_IDS:
        header, _cards, stored_rounds = _load_stream_file(config_id)
        for stream_rounds in stored_rounds.values():
            for line in stream_rounds:
                for p in line["record"]["players"]:
                    for hand_actions in p["actions"]:
                        seen_actions.update(hand_actions)
                    max_hands = max(max_hands, len(p["hands"]))
                    saw_blackjack = saw_blackjack or p["blackjack"]
                    # total > 2x initial means insurance or split+double
                    # money moved beyond the base bet on a single hand.
                    if header["always_insure"] and p["total_bet"] > p["initial_bet"]:
                        saw_insurance = True
                    if header["counting"] and p["initial_bet"] > 10:
                        saw_ramped_bet = True
                if line["record"]["conditional_net"] is not None:
                    saw_conditional = True
    assert {"hit", "stand", "double", "split", "surrender"} <= seen_actions
    assert max_hands == 4, "no resplit chain reached the 4-hand cap"
    assert saw_blackjack
    assert saw_conditional
    assert saw_ramped_bet, "counting corpus never ramped a bet"
    assert saw_insurance, "insured corpus never bought insurance"
