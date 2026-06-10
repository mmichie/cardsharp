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
from cardsharp.blackjack.strategy import BasicStrategy, SolverStrategy
from cardsharp.fastsim.encoding import (
    CORE_AVAILABLE,
    cardsharp_core,
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
    """True if the strategy is fully described by its hard/soft/pair tables.

    CountingStrategy, MartingaleStrategy, and the composition-dependent
    SolverStrategy subclass BasicStrategy but make decisions (or bets)
    outside the tables, so they must run on the reference engine.
    """
    if type(strategy) is BasicStrategy:
        return True
    if type(strategy) is SolverStrategy and strategy.cd_table is None:
        return True
    return False


def resolve_engine(
    rules,
    strategy,
    requested: str = "auto",
    needs_per_round: bool = False,
    needs_cv: bool = False,
    shuffle_type: str = "perfect",
) -> EngineChoice:
    """Decide which engine runs this configuration.

    ``requested`` is "auto", "fast", or "python". "fast" raises with the
    full list of blockers instead of silently falling back.
    """
    if requested == "python":
        return EngineChoice(False, "Python engine requested")

    blockers = []
    if not CORE_AVAILABLE:
        blockers.append("cardsharp-core extension not installed (uv sync --extra fast)")
    if needs_per_round:
        blockers.append("per-round output (--vis) requires the Python engine")
    if needs_cv:
        blockers.append("control variates (--cv) require the Python engine")
    if not strategy_is_encodable(strategy):
        blockers.append(f"strategy {type(strategy).__name__} is not table-encodable")
    if getattr(rules, "variant_name", "classic") != "classic":
        blockers.append(f"variant '{rules.variant_name}' not supported yet")
    if rules.is_using_csm():
        blockers.append("CSM shoes not supported yet")
    if shuffle_type != "perfect":
        blockers.append(f"shuffle_type '{shuffle_type}' not supported yet")

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
) -> SimulationStats:
    """Run one batch on the Rust core and lift the report into stats.

    ``threads`` = 0 uses all cores; the result is bit-identical for a
    given seed regardless of thread count (the core shards the batch
    deterministically and merges in shard order).
    """
    table = encode_strategy_table(strategy, rules)
    report = cardsharp_core.simulate_batch(
        make_core_rules(rules),
        table,
        num_rounds,
        seed=seed % (2**64),
        n_players=n_players,
        initial_bankroll=initial_bankroll,
        threads=threads,
    )
    return SimulationStats.from_dict(report)


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
            rules, strategy, num_rounds, seed, n_players, initial_bankroll, threads
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
