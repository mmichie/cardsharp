"""Smoke tests for the optional cardsharp_core Rust extension.

The extension is an optional accelerator built with `uv sync --extra fast`
(requires a Rust toolchain). When it is not installed these tests skip,
so the pure-Python path stays green without it.
"""

import pytest

cardsharp_core = pytest.importorskip(
    "cardsharp_core",
    reason="cardsharp-core extension not built (uv sync --extra fast)",
)


def test_engine_version_reports_crate_version():
    version = cardsharp_core.engine_version()
    assert isinstance(version, str)
    assert version.count(".") == 2


def test_ping_round_trips_arguments():
    assert cardsharp_core.ping(41) == 42
    assert cardsharp_core.ping(0) == 1
