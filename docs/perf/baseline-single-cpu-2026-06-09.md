# Single-CPU Simulation Baseline (2026-06-09)

Baseline profile of the pure-Python engine before any fast-core work
(beads-9ro.1). All numbers from this machine (Apple Silicon, macOS,
CPython 3.14.3) at commit afad393, 6-deck H17 defaults, seed 12345.

## Headline numbers

| Run | Command | Throughput |
|---|---|---|
| Native | `--simulate --single_cpu --num_games 100000 --seed 12345` | 51,843 games/s (19.3 us/round) |
| Under pyinstrument | same, 200k games | ~21,500 games/s (sampler overhead ~2.4x) |
| Under cProfile | `--profile`, 50k games | ~16,700 games/s (instrumentation ~3x) |

The 22k games/s figure in `docs/optimization_principles.md` is stale for
this hardware; use 51.8k games/s as the comparison base for speedup
claims.

## Artifacts

- `flame-single-cpu-2026-06-09.svg` -- flame graph rendered from the
  cProfile run via flameprof (`uv run python -m cProfile -o sim.prof
  cardsharp/blackjack/blackjack.py --simulate --single_cpu --num_games
  50000 --seed 12345 && uvx flameprof sim.prof > flame.svg`).
- Tooling notes: py-spy requires root on macOS (`task_for_pid`), so a
  sampled flame graph needs `sudo uv run py-spy record --rate 250 -o
  flame.svg -- python cardsharp/blackjack/blackjack.py --simulate
  --single_cpu --num_games 500000 --seed 12345`. pyinstrument 5.x was
  also tried and could not capture stacks below `play_game` on CPython
  3.14 (4-frame profiles even with `--show-all`), so its output was
  discarded; its wall-clock throughput figure remains valid.

## Where a round goes (cProfile, 50k rounds, play_game cum = 2.99s)

| Share | Component | Evidence |
|---|---|---|
| 28% | PlayersTurnState.handle | get_valid_actions rebuilds a list per decision (0.30s cum); player_action 0.20s; unconditional f-strings and decision_logger arg construction in the loop |
| 19% | DealingState.handle | 0.57s cum, of which Shoe.deal is only 0.06s -- dealing is cheap, the wrapping (hand adds, visible-card tracking, blackjack checks) is not |
| 12% | Per-round object churn | BlackjackGame, Player, Dealer constructed every round (0.28s cum combined); 201,071 BlackjackHand allocations (4 per round) |
| 10% | OfferInsuranceState.handle | 2nd-highest self-time of any function (0.144s) despite insurance being rare: full body runs every round, f-string at state.py:209 every round, and the blackjack announcement at state.py:269 is outside its `if` so it formats for every player every round; should_dealer_peek() called 3x per round |
| 10% | EndRoundState.handle | calculate_winner 0.12s, handle_payouts 0.06s |
| 8% | DealersTurnState.handle | dealer draw loop |
| 7% | Stats round-trip | report() -> dict -> from_dict() -> merge() per round (0.20s) instead of scalar accumulation per batch |
| 4% | Strategy decide_action | 0.13s cum -- the lookup itself is already cheap (nested lists, int indices) |
| 4% | Shuffling and PRNG | 1,143 reshuffles; random.shuffle + _randbelow + getrandbits ~0.12s |

Cross-cutting costs visible in the counts (50k rounds):

- `hand.value()` called 627,813 times (12.6 per round); the dict-based
  cache spends 1,000,000 `dict.get` calls just on cache reads, plus
  271k `_invalidate_cache` dict writes.
- `game.output()` called 463,647 times (9.3 per round) -- every one a
  no-op through DummyIOInterface, but each call site still built its
  f-string first.
- `current_hand` property resolved 1.28M times.
- `is_blackjack` builds a set of Rank enums per call: 233,685 enum
  `__hash__` invocations.

## Hypothesis verdicts (from the epic)

| Hypothesis | Verdict |
|---|---|
| Per-round Player/BlackjackGame construction is significant | Confirmed, ~12% direct plus allocator/GC pressure |
| Per-round stats dict round-trip is significant | Confirmed, ~7% |
| Unconditional f-string/logging construction costs | Confirmed, embedded in the ~18% combined self-time of state handlers |
| Dict-based hand cache is costly | Confirmed, 1M dict.gets per 50k rounds for cache reads alone |
| Strategy lookup is cheap | Confirmed, ~4% |
| Shoe/dealing is cheap | Confirmed, ~2% |

## Implication

There is no single hotspot: the cost is smeared across CPython object
machinery (state dispatch, property resolution, dict caches, f-string
construction, per-round allocation). Targeted micro-optimization of the
existing engine plausibly buys 1.5-2x; the actual blackjack math is a
negligible fraction of runtime. This is exactly the profile that
justifies the Rust core (beads-9ro.3): the per-round work is trivial,
so a compiled engine with int-encoded cards should land in the
microsecond-or-below range per round.
