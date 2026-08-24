"""GPU engine exactness tests (beads-f7n).

The GPU engine (`cardsharp_core.simulate_batch_gpu`) must reproduce the
CPU fast core's `simulate_batch` report BIT-FOR-BIT for every
configuration it accepts: the host generates the same shuffle orderings
the shoe would deal, the kernel plays the rounds in pure integers, and
the host replays money and Welford statistics in f64 in the same order.

The strongest check replays the committed golden corpus (tests/golden/)
through the GPU engine and compares against the frozen reports -- the
same regression lock the CPU core answers to.

Everything here skips cleanly when the extension lacks the gpu feature
or no usable adapter exists (e.g. CI runners without a GPU).
"""

import pytest

cardsharp_core = pytest.importorskip(
    "cardsharp_core",
    reason="cardsharp-core extension not built (uv sync --extra fast)",
)

if not getattr(cardsharp_core, "GPU_SUPPORT", False):
    pytest.skip("cardsharp-core built without the gpu feature", allow_module_level=True)

_GPU_OK, _GPU_INFO = cardsharp_core.gpu_probe()
if not _GPU_OK:
    pytest.skip(f"no usable GPU: {_GPU_INFO}", allow_module_level=True)

import json  # noqa: E402

from cardsharp.blackjack.rules import Rules  # noqa: E402
from cardsharp.blackjack.strategy import BasicStrategy, CountingStrategy  # noqa: E402
from cardsharp.fastsim import (  # noqa: E402
    encode_counting_config,
    encode_strategy_table,
    make_core_rules,
    resolve_engine,
    run_fast_batch,
)
from cardsharp.tools.golden_corpus import (  # noqa: E402
    BATCH_CONFIGS,
    GOLDEN_DIR,
    build_strategy,
    make_rules,
)


def _run_pair(rules, strategy, n_rounds, seed, **kwargs):
    """Run the same batch on the CPU core and the GPU engine."""
    table = encode_strategy_table(strategy, rules)
    counting = (
        encode_counting_config(strategy) if type(strategy) is CountingStrategy else None
    )
    core_rules = make_core_rules(rules)
    cpu = cardsharp_core.simulate_batch(
        core_rules, table, n_rounds, seed=seed, counting=counting, **kwargs
    )
    gpu = cardsharp_core.simulate_batch_gpu(
        core_rules, table, n_rounds, seed=seed, counting=counting, **kwargs
    )
    return cpu, gpu


def _assert_reports_identical(cpu, gpu, label):
    assert cpu.keys() == gpu.keys(), label
    diffs = {k: (cpu[k], gpu[k]) for k in cpu if cpu[k] != gpu[k]}
    assert not diffs, f"{label}: GPU report diverged from CPU: {diffs}"


@pytest.mark.parametrize(
    "label,rules_kwargs,strategy_factory,batch_kwargs",
    [
        ("basic-6d", dict(min_bet=10, max_bet=1000), BasicStrategy, {}),
        (
            "basic-peek-s17-das",
            dict(
                min_bet=10,
                max_bet=1000,
                dealer_peek=True,
                dealer_hit_soft_17=False,
                allow_double_after_split=True,
            ),
            BasicStrategy,
            {},
        ),
        (
            "basic-1d-pen09",
            dict(min_bet=10, max_bet=1000, num_decks=1, penetration=0.9),
            BasicStrategy,
            {},
        ),
        (
            "basic-riffle",
            dict(min_bet=10, max_bet=1000),
            BasicStrategy,
            dict(shuffle_type="riffle"),
        ),
        (
            "basic-3-players",
            dict(min_bet=10, max_bet=1000),
            BasicStrategy,
            dict(n_players=3),
        ),
        (
            "counting-6d",
            dict(min_bet=10, max_bet=1000),
            lambda: CountingStrategy(num_decks=6),
            {},
        ),
        (
            "counting-2d-strip",
            dict(min_bet=10, max_bet=1000, num_decks=2),
            lambda: CountingStrategy(num_decks=2),
            dict(shuffle_type="strip"),
        ),
    ],
)
def test_gpu_report_matches_cpu(label, rules_kwargs, strategy_factory, batch_kwargs):
    rules = Rules(**rules_kwargs)
    cpu, gpu = _run_pair(rules, strategy_factory(), 60_000, seed=1234, **batch_kwargs)
    _assert_reports_identical(cpu, gpu, label)


def test_gpu_report_matches_cpu_across_shards():
    # 300k rounds crosses SHARD_ROUNDS: locks the shard layout and the
    # ordered merge on the GPU path.
    rules = Rules(min_bet=10, max_bet=1000)
    cpu, gpu = _run_pair(rules, BasicStrategy(), 300_000, seed=777)
    _assert_reports_identical(cpu, gpu, "flat-multi-shard")


def _gpu_supported_golden(cfg):
    """Golden batch configs the GPU engine accepts (the rest run CPU-only
    paths by design: CSM shoes and conditional settlement)."""
    return not cfg["conditional_settlement"] and not cfg["rules"].get("use_csm", False)


_GOLDEN_GPU_IDS = [c["config"] for c in BATCH_CONFIGS if _gpu_supported_golden(c)]


@pytest.fixture(scope="module")
def golden_batches():
    return json.loads((GOLDEN_DIR / "batches.json").read_text())


@pytest.mark.parametrize("config_id", _GOLDEN_GPU_IDS)
def test_gpu_replays_golden_batches(config_id, golden_batches):
    """The GPU engine must reproduce the frozen golden batch reports
    exactly, just like the CPU core does in test_fastsim_golden."""
    cfg = next(c for c in BATCH_CONFIGS if c["config"] == config_id)
    entry = golden_batches[config_id]
    rules = make_rules(cfg["rules"])
    strategy = build_strategy(rules, cfg["counting"])
    table = encode_strategy_table(strategy, rules)
    counting_cfg = encode_counting_config(strategy) if cfg["counting"] else None
    report = cardsharp_core.simulate_batch_gpu(
        make_core_rules(rules),
        table,
        cfg["n_rounds"],
        seed=cfg["seed"],
        n_players=cfg["n_players"],
        always_insure=cfg["always_insure"],
        counting=counting_cfg,
        shuffle_type=cfg["shuffle_type"],
        shuffle_count=cfg["shuffle_count"],
    )
    fresh = {k: report[k] for k in sorted(report.keys())}
    assert fresh == entry["report"], (
        f"{config_id}: GPU report diverged from the golden corpus\n"
        f"  fresh={fresh}\n  golden={entry['report']}"
    )


def test_resolve_engine_gpu_and_facade():
    rules = Rules(min_bet=10, max_bet=1000)
    strategy = BasicStrategy()

    choice = resolve_engine(rules, strategy, requested="gpu")
    assert choice.use_core and choice.use_gpu

    # auto never picks the GPU on its own.
    auto = resolve_engine(rules, strategy, requested="auto")
    assert auto.use_core and not auto.use_gpu

    # The facade routes through the GPU and produces the same stats.
    cpu_stats = run_fast_batch(rules, strategy, 20_000, seed=99)
    gpu_stats = run_fast_batch(rules, strategy, 20_000, seed=99, use_gpu=True)
    assert cpu_stats.report() == gpu_stats.report()


def test_resolve_engine_gpu_blockers_are_loud():
    rules = Rules(min_bet=10, max_bet=1000)
    strategy = BasicStrategy()
    with pytest.raises(RuntimeError, match="control variates"):
        resolve_engine(rules, strategy, requested="gpu", needs_cv=True)
    with pytest.raises(RuntimeError, match="7 seats"):
        resolve_engine(rules, strategy, requested="gpu", n_players=8)


def test_gpu_rejects_inexact_money_configs():
    # Non-quarter-representable money cannot be replayed exactly in the
    # integer lattice; the engine must refuse rather than approximate.
    rules = Rules(min_bet=10, max_bet=1000)
    strategy = BasicStrategy()
    with pytest.raises(RuntimeError, match="multiple of 0.25"):
        run_fast_batch(
            rules, strategy, 1_000, seed=1, initial_bankroll=1000.3, use_gpu=True
        )
