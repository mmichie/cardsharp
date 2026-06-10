"""Optional Rust-accelerated simulation core.

This package is the Python side of the `cardsharp_core` extension
(crates/cardsharp-core): `cardsharp.fastsim.encoding` compiles strategy
charts and rules for the core, and `cardsharp.fastsim.runner` exposes the
run surface with transparent fallback to the pure-Python reference engine
when the extension is missing or a feature is unsupported.

The extension is built with `uv sync --extra fast` and requires a Rust
toolchain. Everything in cardsharp works without it.
"""

from cardsharp.fastsim.encoding import (
    CORE_AVAILABLE,
    encode_counting_config,
    encode_strategy_table,
    make_core_rules,
    rules_kwargs,
)
from cardsharp.fastsim.runner import (
    EngineChoice,
    SimulationRun,
    resolve_engine,
    run_fast_batch,
    simulate,
    strategy_is_encodable,
)

__all__ = [
    "CORE_AVAILABLE",
    "EngineChoice",
    "SimulationRun",
    "encode_counting_config",
    "encode_strategy_table",
    "make_core_rules",
    "resolve_engine",
    "rules_kwargs",
    "run_fast_batch",
    "simulate",
    "strategy_is_encodable",
]
