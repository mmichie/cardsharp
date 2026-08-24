# GPU engine benchmark (2026-08-24)

Hardware: Apple M5 (10 CPU cores, 10-core GPU, Metal), macOS 25.6.0.
Build: `uv sync --extra fast` (maturin release build, gpu feature on).
Command: `uv run python cardsharp/blackjack/blackjack.py --simulate
--strat {basic|count} --num_games N --engine {fast|gpu} --seed 7`.

Reports are bit-identical between `--engine fast` and `--engine gpu` for
the same seed (asserted by `tests/test_fastsim_gpu.py` and the golden
corpus replay); the numbers below differ only in wall clock.

## Flat-bet basic strategy (6 decks, pen 0.75, H17)

| rounds | fast (CPU, all cores) | gpu | speedup |
|--------|----------------------:|----:|--------:|
| 5M     | 11.9M rounds/s | 21.0M rounds/s | 1.8x |
| 100M   | 15.3M rounds/s | 65.6M rounds/s | 4.3x |
| 1B     | 16.2M rounds/s | 75.9M rounds/s | 4.7x |

Phase breakdown at 100M (CARDSHARP_GPU_TIMING=1): generate 0.48s
(host-side shuffle orderings, rayon), gpu 0.76s (kernel + transfers),
replay 0.25s (host f64 money/stats replay, rayon). The phases run
serially per wave; overlapping them (beads-f7n.6) is the next win.

## Hi-Lo counting (bet ramp, I18 deviations, insurance)

| rounds | fast (CPU, all cores) | gpu | speedup |
|--------|----------------------:|----:|--------:|
| 100M   | 15.7M rounds/s | 15.9M rounds/s | 1.0x |
| 1B     | 15.5M rounds/s | 16.0M rounds/s | 1.0x |

Counting runs one GPU thread per 250k-round shard (the running count
carries across shoe boundaries, so shoes cannot be played in parallel),
which leaves the GPU under-occupied: expect parity with the CPU core,
not a speedup. One practical difference: the GPU run leaves the CPU
almost idle (43 CPU-seconds vs ~9 CPU-minutes for the same 1B-round
counting run), so counting on the GPU is useful when the CPU is needed
for other work.

## Why the results are identical

The GPU engine reuses the CPU core's shard layout and per-shard RNG. In
the classic (non-CSM) shoe, RNG is consumed only during shuffles, so the
host pre-generates the exact shuffle orderings the shoe would deal
(`shoe.rs OrderingGen`, sharing the shoe's shuffle code). The WGSL kernel
plays rounds in pure integer arithmetic -- true-count thresholds compare
via exact integer cross-multiplication, money affordability via an
eighth-unit lattice -- and emits packed outcome records. The host replays
every monetary operation and Welford update in f64, expression-for-
expression and in the engine's order. Shards the kernel cannot reproduce
exactly (mid-round shoe exhaustion consumes RNG mid-round) are replayed
wholesale on the CPU shard runner, which is exact because shards are
independent.

Configurations the GPU engine refuses (CSM shoes, conditional
settlement/--cv, per-deal accumulation, >7 seats, max_splits > 3, money
values that are not multiples of 0.25): `--engine gpu` errors loudly with
the reason; `--engine auto` continues to use the CPU core.
