//! cardsharp-core: the Rust fast core for the cardsharp blackjack simulator.
//!
//! Scaffold only (beads-9ro.2). The round engine lands in beads-9ro.3; this
//! module exposes just enough surface to prove the build pipeline and the
//! Python <-> Rust round trip end to end. The Python facade treats this
//! extension as an optional accelerator and falls back to the pure-Python
//! engine when it is absent.

use pyo3::prelude::*;

/// Version of the compiled core, for the Python facade to report and to
/// check against the expected interface version.
#[pyfunction]
fn engine_version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Trivial round trip used by the smoke test to prove argument and
/// return-value conversion across the extension boundary.
#[pyfunction]
fn ping(value: u64) -> u64 {
    value.wrapping_add(1)
}

#[pymodule]
fn cardsharp_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(engine_version, m)?)?;
    m.add_function(wrap_pyfunction!(ping, m)?)?;
    Ok(())
}
