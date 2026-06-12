"""Run surface for the Rust fast core, with graceful fallback.

`simulate` is the library entry point; `resolve_engine` is the policy that
decides (and explains) which engine a given configuration runs on. The
fast core accelerates exactly the configurations the parity suite proves
equivalent: classic variant, perfect-shuffle shoe, table-encodable
strategies. Everything else falls back to the pure-Python reference
engine, transparently under "auto" and loudly under "fast".

Orchestration, statistics, confidence intervals, control variates, and
plotting all stay in Python: the core returns one aggregate report per
batch, shaped exactly like ``SimulationStats.report()``.
"""

import random
import time
from dataclasses import dataclass

from cardsharp.blackjack.stats import SimulationStats
from cardsharp.blackjack.strategy import (
    BasicStrategy,
    CountingStrategy,
    SolverStrategy,
)
from cardsharp.fastsim.encoding import (
    CORE_AVAILABLE,
    cardsharp_core,
    encode_counting_config,
    encode_strategy_table,
    make_core_rules,
)


@dataclass(frozen=True)
class EngineChoice:
    """The outcome of engine resolution: which engine, and why."""

    use_core: bool
    reason: str


@dataclass(frozen=True)
class SimulationRun:
    """A completed simulation: aggregate stats plus run metadata."""

    stats: SimulationStats
    engine: str  # "fast" or "python"
    seed: int
    duration: float

    @property
    def rounds_per_second(self) -> float:
        if self.duration <= 0:
            return 0.0
        return self.stats.n_rounds / self.duration


def strategy_is_encodable(strategy) -> bool:
    """True if the core can reproduce this strategy exactly.

    Tables cover BasicStrategy and the non-composition-dependent
    SolverStrategy; CountingStrategy additionally crosses as a
    CountingConfig (Hi-Lo count, bet ramp, Illustrious 18 deviations).
    MartingaleStrategy and other bet-progression or custom strategies
    must run on the reference engine.
    """
    if type(strategy) is BasicStrategy:
        return True
    if type(strategy) is SolverStrategy and strategy.cd_table is None:
        return True
    if type(strategy) is CountingStrategy:
        return True
    return False


def resolve_engine(
    rules,
    strategy,
    requested: str = "auto",
    needs_per_round: bool = False,
    needs_cv: bool = False,
    shuffle_type: str = "perfect",
    n_players: int = 1,
) -> EngineChoice:
    """Decide which engine runs this configuration.

    ``requested`` is "auto", "fast", or "python". "fast" raises with the
    full list of blockers instead of silently falling back.
    """
    if requested == "python":
        return EngineChoice(
            False,
            "Python engine requested (deprecated since v0.7.0; removal "
            "scheduled for the next release)",
        )

    blockers = []
    if not CORE_AVAILABLE:
        blockers.append("cardsharp-core extension not installed (uv sync --extra fast)")
    if needs_per_round:
        blockers.append("per-round output (--vis) requires the Python engine")
    if needs_cv and n_players > 1:
        blockers.append(
            "control variates with multiple players require the Python "
            "engine (the core's per-deal accumulator is single-seat)"
        )
    if not strategy_is_encodable(strategy):
        blockers.append(f"strategy {type(strategy).__name__} is not table-encodable")
    if getattr(rules, "variant_name", "classic") != "classic":
        blockers.append(f"variant '{rules.variant_name}' not supported yet")
    if shuffle_type not in ("perfect", "riffle", "strip"):
        blockers.append(f"unknown shuffle_type '{shuffle_type}'")

    if not blockers:
        return EngineChoice(True, "all features supported by the fast core")

    reason = "; ".join(blockers)
    if requested == "fast":
        raise RuntimeError(f"--engine fast is unavailable: {reason}")
    return EngineChoice(False, reason)


def run_fast_batch(
    rules,
    strategy,
    num_rounds: int,
    seed: int,
    n_players: int = 1,
    initial_bankroll: float = 1000,
    threads: int = 0,
    shuffle_type: str = "perfect",
    shuffle_count=None,
    conditional_settlement: bool = False,
) -> SimulationStats:
    """Run one batch on the Rust core and lift the report into stats.

    ``threads`` = 0 uses all cores; the result is bit-identical for a
    given seed regardless of thread count (the core shards the batch
    deterministically and merges in shard order).

    ``conditional_settlement`` records each round's exact expected net
    over the dealer's draw distribution (Rao-Blackwellization) instead
    of the realized net: same mean, less variance, tighter CIs for the
    same number of rounds. Peek rules and non-CSM shoes only.
    """
    table = encode_strategy_table(strategy, rules)
    counting = (
        encode_counting_config(strategy) if type(strategy) is CountingStrategy else None
    )
    report = cardsharp_core.simulate_batch(
        make_core_rules(rules),
        table,
        num_rounds,
        seed=seed % (2**64),
        n_players=n_players,
        initial_bankroll=initial_bankroll,
        threads=threads,
        counting=counting,
        shuffle_type=shuffle_type,
        shuffle_count=shuffle_count,
        conditional_settlement=conditional_settlement,
    )
    return SimulationStats.from_dict(report)


def run_fast_per_deal(
    rules,
    strategy,
    num_rounds: int,
    seed: int,
    threads: int = 0,
    conditional_settlement: bool = False,
    shuffle_type: str = "perfect",
    shuffle_count=None,
):
    """Single-player batch with the core's per-deal accumulator.

    Returns ``(stats, cells)`` where ``cells`` is a flat list of 1000
    ``(n, sum_x, sum_x2)`` tuples with X = net/initial_bet bucketed by
    the round's deal state (c1, c2, upcard) in solver card values
    (Ace=1, ten-classes collapsed), indexed
    ``((lo-1)*10 + (hi-1))*10 + (up-1)``; only lo <= hi cells populate.
    Y references are subtracted Python-side -- Y is constant within a
    cell, so both the EV diagnostic's d = X - Y moments and the control
    variate's joint (X, Y) moments derive exactly from these X moments.
    """
    table = encode_strategy_table(strategy, rules)
    counting = (
        encode_counting_config(strategy) if type(strategy) is CountingStrategy else None
    )
    report = cardsharp_core.simulate_batch(
        make_core_rules(rules),
        table,
        num_rounds,
        seed=seed % (2**64),
        threads=threads,
        counting=counting,
        shuffle_type=shuffle_type,
        shuffle_count=shuffle_count,
        conditional_settlement=conditional_settlement,
        per_deal=True,
    )
    cells = report.pop("per_deal")
    return SimulationStats.from_dict(report), cells


def attach_cv_from_cells(stats: SimulationStats, cells, deal_ev_table, mu_y):
    """Fill ``stats``' control-variate accumulators from per-deal cells.

    The control variate Y is the solver's exact E[X | deal] for the
    round's (c1, c2, upcard); it is CONSTANT within a per-deal cell, so
    every joint moment the CV estimator needs reconstructs exactly from
    the cells' X moments: sum_y = sum_k n_k y_k, sum_xy = sum_k y_k
    sum_x_k, and so on. This is mathematically identical to the
    per-round Welford accumulation the Python engine performed (float
    summation order differs at ~1e-15), so
    ``SimulationStats.control_variate_he_with_ci`` works unchanged.
    """
    n = 0
    sum_x = sum_x2 = 0.0
    sum_y = sum_y2 = sum_xy = 0.0
    for idx, (cell_n, cell_sx, cell_sx2) in enumerate(cells):
        if cell_n == 0:
            continue
        lo = idx // 100 + 1
        hi = (idx // 10) % 10 + 1
        up = idx % 10 + 1
        y = deal_ev_table.get((lo, hi, up))
        if y is None:
            raise RuntimeError(
                f"deal ({lo},{hi},{up}) was simulated but is absent from "
                f"the solver's deal-EV table"
            )
        n += cell_n
        sum_x += cell_sx
        sum_x2 += cell_sx2
        sum_y += cell_n * y
        sum_y2 += cell_n * y * y
        sum_xy += y * cell_sx
    if n == 0:
        return stats

    x_mean = sum_x / n
    y_mean = sum_y / n
    stats.cv_n = n
    stats.cv_x_mean = x_mean
    stats.cv_y_mean = y_mean
    stats.cv_x_M2 = max(sum_x2 - n * x_mean * x_mean, 0.0)
    stats.cv_y_M2 = max(sum_y2 - n * y_mean * y_mean, 0.0)
    stats.cv_xy_C = sum_xy - n * x_mean * y_mean
    stats.cv_mu_y = mu_y
    return stats


def run_fast_cv(
    rules,
    strategy,
    num_rounds: int,
    seed: int,
    deal_ev_table,
    mu_y: float,
    threads: int = 0,
    shuffle_type: str = "perfect",
    shuffle_count=None,
):
    """Control-variate simulation on the fast core (single player).

    Runs the per-deal batch and derives the CV accumulators from the
    cells, so the returned ``SimulationStats`` reports both the plain
    and the CV-adjusted house edge exactly like the Python engine's
    --cv path did.
    """
    stats, cells = run_fast_per_deal(
        rules,
        strategy,
        num_rounds,
        seed,
        threads=threads,
        shuffle_type=shuffle_type,
        shuffle_count=shuffle_count,
    )
    return attach_cv_from_cells(stats, cells, deal_ev_table, mu_y)


def run_fast_paired(
    rules_a,
    strategy_a,
    rules_b,
    strategy_b,
    num_rounds: int,
    seed: int,
    n_players: int = 1,
    initial_bankroll: float = 10_000_000,
    threads: int = 0,
    conditional_settlement: bool = False,
):
    """Common-Random-Numbers comparison of two rule variants on the core.

    Every round both variants play identically shuffled decks, so the
    paired difference of per-round house edges reflects rule divergence
    only. Returns (stats_a, stats_b, diff) where diff is a dict with
    n/mean/M2 of the per-round HE_a - HE_b series. Counting strategies
    are unsupported (per-round shoe resets destroy the count), matching
    cardsharp.blackjack.comparison.
    """
    if type(strategy_a) is CountingStrategy or type(strategy_b) is CountingStrategy:
        raise ValueError("CRN comparison does not support counting strategies")
    report = cardsharp_core.simulate_paired(
        make_core_rules(rules_a),
        encode_strategy_table(strategy_a, rules_a),
        make_core_rules(rules_b),
        encode_strategy_table(strategy_b, rules_b),
        num_rounds,
        seed=seed % (2**64),
        n_players=n_players,
        initial_bankroll=initial_bankroll,
        threads=threads,
        conditional_settlement=conditional_settlement,
    )
    return (
        SimulationStats.from_dict(report["a"]),
        SimulationStats.from_dict(report["b"]),
        {
            "n": report["diff_n"],
            "mean": report["diff_mean"],
            "M2": report["diff_M2"],
        },
    )


def _run_python_batch(
    rules,
    strategy,
    num_rounds: int,
    seed: int,
    n_players: int = 1,
    initial_bankroll: int = 1000,
    shuffle_type: str = "perfect",
    shuffle_count=None,
) -> SimulationStats:
    """Reference-engine loop, mirroring the CLI's --single_cpu path."""
    # Imported here so the facade never drags the full engine (and its
    # matplotlib dependency chain) in when only the fast core is used.
    from cardsharp.blackjack.blackjack import generate_player_names, play_game
    from cardsharp.common.io_interface import DummyIOInterface
    from cardsharp.common.shoe import Shoe

    random.seed(seed)
    player_names = generate_player_names(n_players)
    shoe = Shoe(
        num_decks=rules.num_decks,
        penetration=rules.penetration,
        use_csm=rules.is_using_csm(),
        burn_cards=rules.burn_cards,
        deck_factory=rules.variant.create_deck if rules.variant else None,
        shuffle_type=shuffle_type,
        shuffle_count=shuffle_count,
    )
    agg = SimulationStats()
    io_interface = DummyIOInterface()
    for _ in range(num_rounds):
        _net, _total, _initial, report, shoe = play_game(
            rules, io_interface, player_names, strategy, shoe, initial_bankroll
        )
        agg.merge(SimulationStats.from_dict(report))
    return agg


def simulate(
    rules,
    strategy,
    num_rounds: int,
    seed=None,
    engine: str = "auto",
    n_players: int = 1,
    initial_bankroll: int = 1000,
    needs_per_round: bool = False,
    needs_cv: bool = False,
    shuffle_type: str = "perfect",
    shuffle_count=None,
    threads: int = 0,
) -> SimulationRun:
    """Simulate ``num_rounds`` of blackjack on the best available engine."""
    if seed is None:
        seed = random.SystemRandom().randint(0, 2**63 - 1)

    choice = resolve_engine(
        rules,
        strategy,
        requested=engine,
        needs_per_round=needs_per_round,
        needs_cv=needs_cv,
        shuffle_type=shuffle_type,
    )

    start = time.perf_counter()
    if choice.use_core:
        stats = run_fast_batch(
            rules,
            strategy,
            num_rounds,
            seed,
            n_players,
            initial_bankroll,
            threads,
            shuffle_type,
            shuffle_count,
        )
        engine_used = "fast"
    else:
        stats = _run_python_batch(
            rules,
            strategy,
            num_rounds,
            seed,
            n_players,
            initial_bankroll,
            shuffle_type,
            shuffle_count,
        )
        engine_used = "python"
    duration = time.perf_counter() - start

    return SimulationRun(stats=stats, engine=engine_used, seed=seed, duration=duration)
