# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

* The fast core builds as an rlib as well as a cdylib, and all of PyO3
  sits behind a non-default `python` feature that only maturin enables
  -- so a Rust project can depend on the round engine, the rules, the
  shoe and the strategy table with no libpython in its graph. The wheel
  is unchanged; `RELEASING.md` records the pin-by-tag policy
* Interactive sessions run on a native, `Send` round state machine
  (`machine::RoundMachine`, `step(answer) -> Step`) instead of a worker
  thread and two channels per session. `cardsharp_core.Session` is now
  a thin wrapper over it and is no longer `unsendable`; the round
  implementation, the `Decider` seam and every observable session
  behaviour are unchanged
* Optional `serde` feature: derives on `Rules`, `RoundRecord`,
  `PlayerRecord`, `SeatSnapshot` and the step/answer types, for
  persistence and fixture generation
* `Rules.digest()`: a stable 64-bit fingerprint over a canonical field
  order, so a stored round can prove it resumes under the rules it was
  dealt with. Adding a rule field changes every digest, deliberately

## 0.7.0

* Rust fast core (crates/cardsharp-core): classic blackjack at ~2.9M
  games/second single-threaded, ~15-30M games/second Rayon-sharded with
  bit-identical results for a given seed regardless of thread count
* Hi-Lo counting (bet ramp, Illustrious 18 deviations, TC insurance),
  CSM shoes, and GSR riffle/strip shuffles on the fast core
* Card-stream parity suite proving round-for-round identity with the
  Python engine across the rule surface, plus a rules-surface tripwire
* Golden card-stream regression corpus (tests/golden/): frozen
  parity-proven outputs replayed exactly in CI
* Conditional dealer settlement (Rao-Blackwellized, validated and off
  by default) and CRN rule comparisons (--compare_rules, ~9.6x tighter
  CIs) on the core
* Per-deal EV diagnostic fast leg (100M 1-deck rounds in ~17s) and the
  deal-EV control variate (--cv) on the core via exact CV-moment
  reconstruction from per-deal cells
* Interactive resumable session API (cardsharp.fastsim.open_session);
  the console mode and the event-driven engine behind the CLI/web
  adapters now drive core sessions (fixes the dealer-ace insurance
  crash in console mode and the dealer hole-card leak to adapters)
* WoO benchmark fast leg; 1B-round statistical validation recorded in
  the accuracy chain
* The pure-Python round engine is FROZEN and deprecated: a
  DeprecationWarning fires on every entry, and the engine, the parity
  suite, and the fallback branches are scheduled for deletion in the
  next release (single-engine end state, beads-i2s)

## 0.6.0

* Exact probabilistic solver with fast/exact/combinatorial modes,
  finite-deck support, correlated split evaluation, resplit support,
  and --solve CLI; pinned against the Wizard of Odds within ~1 bp
* 5x simulation speedup (17K -> 92K hands/s) plus state-machine and
  strategy-lookup optimizations
* Professional card counting with play deviations, shuffle detection,
  and a counting-beats-basic same-shoe validation
* European no-peek with OBO, double_on/resplit_aces/hit_split_aces
  rules, five-card charlie, penetration/cut-card and burn cards
* Blackjack variant architecture with Spanish 21; Durak, Baccarat, and
  Dragon Tiger implementations
* Scenario-based testing with RiggedShoe; pyrefly type checking;
  migration from Poetry to uv; Python 3.14

## 0.5.0

* Fix event handler cleanup in WarGame and HighCardGame to match BlackjackGame implementation
* Add standalone test script for API tests that doesn't rely on pytest
* Add proper pytest tests for event handler cleanup and BlackjackGame functionality
* Reorganize test files to follow proper structure
* Rename example scripts to clarify they are demos, not tests
* Add new BlackjackGame API demo
* Update architecture documentation to highlight resource management benefits
* Migrate UI implementation to use modern architecture (renamed blackjack_ui_new.py to blackjack_ui.py)

## 0.4.0

* Complete Phase 4 of architecture modernization
* Add WebSocket support for real-time updates
* Add immutable state verification system
* Implement high-level game APIs for all game types
* Add new example scripts for demonstration

## 0.3.0

* Vastly increased performance, removed async from main path
* Add async io compatibility layer

## 0.2.0

* Multiprocessing Capability
* Basic profiling support

## 0.1.0

* Initial Release
