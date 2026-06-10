"""Optional Rust-accelerated simulation core.

This package is the Python side of the `cardsharp_core` extension
(crates/cardsharp-core). Phase 3 (beads-9ro.3) ships the encoding layer
and the raw entry points; the full run-surface facade with transparent
fallback to the pure-Python engine lands in Phase 4 (beads-9ro.4).

The extension is built with `uv sync --extra fast` and requires a Rust
toolchain. Everything in cardsharp works without it.
"""

from cardsharp.fastsim.encoding import (
    CORE_AVAILABLE,
    encode_strategy_table,
    make_core_rules,
    rules_kwargs,
)

__all__ = [
    "CORE_AVAILABLE",
    "encode_strategy_table",
    "make_core_rules",
    "rules_kwargs",
]
