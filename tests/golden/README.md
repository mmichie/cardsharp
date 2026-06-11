# Golden card-stream regression corpus

This directory freezes parity-proven fast-core behavior as data
(beads-i2s.3). `tests/test_fastsim_golden.py` replays every entry through
`cardsharp_core` and asserts exact equality -- bets, hands, actions,
winners, money flow, cards consumed, batch report moments, paired CRN
moments, and shuffle epochs. Once the Python reference engine retires,
this corpus is the regression lock that replaces live parity testing.

## Contents

- `streams/<config>.jsonl` -- one file per rule configuration. Line 1 is
  the generation header; then, per card stream, a `{"stream": i,
  "cards": [...]}` line followed by one `{"stream": i, "round": j,
  "record": {...}}` line per completed round. One line per round keeps
  `git diff` granular: a semantic change diffs exactly the affected
  rounds.
- `batches.json` -- `simulate_batch` report dicts: end-to-end shoe
  machinery (penetration, burn cards, CSM, riffle/strip shuffles,
  counting, conditional settlement, multi-shard merges) that stream
  injection cannot reach. Reports are bit-identical for a given seed
  regardless of thread count, which is what makes them golden-able.
- `paired.json` -- `simulate_paired` CRN comparison outputs.
- `shoe_traces.json` -- `trace_shoe` shuffle/exhaustion epochs (cut-card
  semantics).
- `MANIFEST.json` -- engine version and corpus counts, for provenance.

The corpus is self-contained: card streams are stored, not re-derived
from RNG seeds, so replay does not depend on Python's `random` module
remaining stable.

## Update procedure

Regenerate with:

    uv run python -m cardsharp.tools.golden_corpus

Regeneration is idempotent: on an engine whose semantics are unchanged
it rewrites byte-identical files. `git diff --stat tests/golden` after a
regen is therefore exactly the semantic delta of your change.

Policy:

1. Goldens change ONLY for an intended semantic change to the engine
   (or a deliberate corpus extension), in the same commit as the code
   change, with the data diff reviewed round by round.
2. Never regenerate to silence a failing golden test you do not
   understand. The failure message names the config, stream, round, and
   cards; reproduce it with `play_card_stream` and explain the
   divergence first.
3. When adding a rule or feature to the core, add configurations here
   (and to the parity suite, while it exists) in the same change.
