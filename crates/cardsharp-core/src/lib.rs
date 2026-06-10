//! cardsharp-core: the Rust fast core for the cardsharp blackjack simulator.
//!
//! The round engine (beads-9ro.3) plays classic blackjack with the exact
//! semantics of the Python reference engine -- including its quirks --
//! so that card-stream parity (beads-9ro.5) can assert identical
//! decisions, payouts, and card consumption. Strategy charts are compiled
//! to a 370-byte table on the Python side
//! (`cardsharp.fastsim.encoding.encode_strategy_table`).

mod card;
mod hand;
mod round;
mod rules;
mod shoe;
mod sim;
mod stats;
mod strategy;

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
    m.add_function(wrap_pyfunction!(sim::simulate_batch, m)?)?;
    m.add_function(wrap_pyfunction!(sim::play_card_stream, m)?)?;
    m.add_class::<rules::Rules>()?;
    m.add_class::<sim::RoundRecord>()?;
    m.add_class::<sim::PlayerRecord>()?;
    m.add("STRATEGY_TABLE_BYTES", strategy::TABLE_BYTES)?;
    Ok(())
}
