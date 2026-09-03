//! cardsharp-core: the Rust fast core for the cardsharp blackjack simulator.
//!
//! The round engine (beads-9ro.3) plays classic blackjack with the exact
//! semantics of the Python reference engine -- including its quirks --
//! so that card-stream parity (beads-9ro.5) can assert identical
//! decisions, payouts, and card consumption. Strategy charts are compiled
//! to a 370-byte table on the Python side
//! (`cardsharp.fastsim.encoding.encode_strategy_table`).
//!
//! # Two consumers, one engine
//!
//! The crate builds as a **cdylib** (the `cardsharp_core` Python extension
//! module, built by maturin) and as an **rlib** (a plain Rust dependency).
//! Everything PyO3 sits behind the non-default `python` feature, which
//! only maturin enables, so a Rust consumer links the rules with no
//! libpython:
//!
//! ```text
//! cardsharp-core = { git = "...", default-features = false }
//! ```
//!
//! The Rust surface is the round engine ([`round::play_round`] and the
//! [`round::Decider`] seam), the rule set ([`rules::Rules`]), the shoe
//! ([`shoe`]), the strategy table ([`strategy`]), the Hi-Lo counter
//! ([`counting`]) and the resumable round state machine
//! ([`machine::RoundMachine`]). The `session` module -- the pyclass
//! wrapper over that machine -- is the one module that exists only under
//! `python`.

pub mod card;
pub mod counting;
#[cfg(feature = "gpu")]
mod gpu;
pub mod hand;
pub mod machine;
pub mod round;
pub mod rules;
#[cfg(feature = "python")]
mod session;
pub mod settle;
pub mod shoe;
pub mod sim;
pub mod stats;
pub mod strategy;

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// Version of the compiled core, for the Python facade to report and to
/// check against the expected interface version.
#[cfg_attr(feature = "python", pyfunction)]
pub fn engine_version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Trivial round trip used by the smoke test to prove argument and
/// return-value conversion across the extension boundary.
#[cfg(feature = "python")]
#[pyfunction]
fn ping(value: u64) -> u64 {
    value.wrapping_add(1)
}

#[cfg(feature = "python")]
#[pymodule]
fn cardsharp_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(engine_version, m)?)?;
    m.add_function(wrap_pyfunction!(ping, m)?)?;
    m.add_function(wrap_pyfunction!(sim::simulate_batch, m)?)?;
    m.add_function(wrap_pyfunction!(sim::simulate_paired, m)?)?;
    m.add_function(wrap_pyfunction!(sim::play_card_stream, m)?)?;
    m.add_function(wrap_pyfunction!(sim::trace_shoe, m)?)?;
    m.add_class::<rules::Rules>()?;
    m.add_class::<counting::CountingConfig>()?;
    m.add_class::<sim::RoundRecord>()?;
    m.add_class::<sim::PlayerRecord>()?;
    m.add_class::<session::Session>()?;
    m.add_class::<session::SessionStep>()?;
    m.add_class::<machine::SeatSnapshot>()?;
    m.add("STRATEGY_TABLE_BYTES", strategy::TABLE_BYTES)?;
    // GPU engine surface: present only when the crate was built with the
    // `gpu` feature; availability is still a runtime question (gpu_probe).
    m.add("GPU_SUPPORT", cfg!(feature = "gpu"))?;
    #[cfg(feature = "gpu")]
    {
        m.add_function(wrap_pyfunction!(gpu::simulate_batch_gpu, m)?)?;
        m.add_function(wrap_pyfunction!(gpu::gpu_probe, m)?)?;
    }
    Ok(())
}
