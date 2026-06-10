# Optimization Principles for Simulations

## Golden Rule: Never Compromise Accuracy for Speed

A simulation that doesn't accurately model the system is worthless, regardless of speed.

## Legitimate Optimizations (Preserve Accuracy)

### ✅ Data Structure Improvements
- Use integers instead of objects for cards
- Pre-compute lookup tables
- Use numpy arrays for better memory layout

### ✅ Algorithm Efficiency
- O(1) lookups instead of O(n) searches
- Pre-allocate memory to avoid runtime allocation
- Cache frequently accessed values

### ✅ Reduce Overhead
- Minimize object creation
- Avoid string operations in hot paths
- Direct function calls vs polymorphism

### ✅ Parallelization
- Use multiple CPU cores
- Batch processing
- SIMD operations

## Illegitimate "Optimizations" (Break Accuracy)

### ❌ Simplifying Game Rules
- Removing splits, insurance, or surrender
- Using simplified strategy
- Changing payout ratios

### ❌ Statistical Approximation
- Generating outcomes from probability distributions
- Not actually playing hands
- Using predetermined results

### ❌ Incomplete Implementation
- Not handling edge cases
- Ignoring rule variations
- Taking shortcuts in game logic

## The Right Approach

1. **Profile First**: Identify actual bottlenecks
2. **Optimize Implementation**: Make the same logic faster
3. **Verify Accuracy**: Results must match original
4. **Document Assumptions**: Be clear about what's included

## Example: Blackjack Optimization

### Good Optimization
```python
# Original: Object creation
card = Card(Suit.HEARTS, Rank.ACE)
value = card.get_value()

# Optimized: Direct lookup
card = 0  # Ace of spades as int
value = CARD_VALUES[card]
```

### Bad "Optimization"
```python
# Original: Implement splits
if can_split(hand):
    return split_hand(hand)

# Wrong: Skip splits entirely
# Just don't implement splitting
```

## Performance vs Accuracy Trade-off

There is NO trade-off. A fast but inaccurate simulation is useless.

The goal is to make the SAME simulation run faster, not to create a different, simpler simulation.

## Testing Optimization Correctness

1. Run both versions with same seed
2. Compare every decision point
3. Verify identical outcomes
4. Check edge cases thoroughly

## Accuracy Validation Chain

The simulator's accuracy is anchored end to end:

1. The combinatorial solver is pinned against the Wizard of Odds
   calculator (tests/blackjack/solver/test_engine.py::TestWoOReference)
   within 10 bp, sub-bp at 2+ decks.
2. `strategy_house_edge(result, rules)` computes the exact EV of playing
   the collapsed total-dependent strategy table; `result.house_edge` is
   the composition-dependent optimum. The simulator's convergence target
   is the former when playing the table, the latter when constructed
   with `SolverStrategy(sol, use_ev_table=True)` (CLI: `--cd_strategy`).
3. Fresh-shoe mode (`--penetration 0.01` reshuffles before every round)
   matches the solver's per-round composition model. Measured agreement
   on 2026-06-09 at 20M rounds (`--cd_strategy --cv --penetration 0.01`):
   6-deck H17 within -2.2 bp +/- 4.5 bp.
4. The solver and the WoO calculator agree within ~1 bp at every
   pinned config (1d/2d/6d, H17/S17) -- both compute the full
   composition-dependent optimum. The fresh-shoe simulator sits
   slightly above both: ~+6 bp at 1-2 decks, ~+1.5 bp at 6 decks
   (cardsharp/tools/woo_benchmark.py, 40M games per config plus a
   160M-game 6-deck precision run, 2026-06-09). This is expected,
   not a defect: the solver's best_ev re-optimizes stand-vs-hit
   composition-dependently at every post-hit card, a strictly
   stronger optimum than any table-driven player (simulator or
   human) can express, and the effect dilutes with deck count. A
   12M-round decomposition (cardsharp/tools/deal_ev_diagnostic.py)
   attributes the entire 1-deck residual to this play-EV difference
   and none to deal distribution.
5. At real penetrations the simulator's edge sits above the solver value
   by the cut-card effect; that is correct behavior, not a bug.
6. The Rust fast core (crates/cardsharp-core, --engine fast) is held to
   the same chain two ways. (a) Equivalence: the card-stream parity suite
   (tests/test_fastsim_parity.py, in CI) proves round-for-round identity
   with the Python engine -- money flow, per-hand outcomes, and cards
   consumed over fuzzed and adversarial streams across 19 rule
   configurations, plus consumption-count shuffle-epoch equality for
   cut-card and mid-round-exhaustion semantics. (b) Statistics: a
   200M-games-per-config woo_benchmark --engine fast run (2026-06-09,
   ~1B rounds total at 1.2-2.3M games/s on a single core, pre-Rayon)
   playing the pure solver table at fresh shoe measured sim-WoO of
   +8.3/+11.5 bp at 1 deck, +4.6 bp at 2 decks, and +3.3/+4.3 bp at 6
   decks -- the documented achievability gap, slightly wider than item
   4's CD-first bands because the core plays the table at every
   decision. Against strategy_house_edge (table first decisions, optimal
   continuations) the residual isolates the post-hit continuation gap:
   +6.3/+7.6 bp (1d), +3.9 (2d), +2.9/+4.1 (6d), each +/-1.6 bp. This
   confirms item 4's structural account while correcting the magnitude
   guess in strategy_house_edge's docstring: the continuation residual
   is not an order of magnitude smaller than the first-decision effect
   -- at every pinned config it is larger.

Simulation mechanics that this chain guards (all have regression tests):

- The cut card never interrupts a round; the shoe shuffles between
  rounds (Shoe.begin_round/end_round). A mid-round exhaustion reshuffles
  only the discards: a card on the table can never also be in the shoe.
- The dealer completes their hand only while at least one player hand is
  live (not busted, surrendered, or already settled), as in a real pit.
- Hard 17 vs Ace surrenders in H17 games (worth ~0.5 bp of EV); the
  surrender fallback when the action is unavailable is stand on hard
  17+, hit otherwise (the published Rh/Rs distinction).

## Running Performance Benchmarks

### Fast Core (default when built)
```bash
# Rust fast core: ~30M games/second across all cores, ~2.9M on one thread
# (Apple Silicon, 14 logical cores, 2026-06). Seeded results are
# bit-identical regardless of thread count.
# Built with: uv sync --extra fast
uv run python cardsharp/blackjack/blackjack.py --simulate --num_games 100000000
```

### Reference Engine (Multiprocessing)
```bash
# Pure-Python engine across all cores: ~350,000 games/second
uv run python cardsharp/blackjack/blackjack.py --simulate --num_games 100000 --engine python
```

### Reference Engine (Single-threaded)
```bash
# Pure-Python engine, one thread: ~50,000 games/second
uv run python cardsharp/blackjack/blackjack.py --simulate --num_games 100000 --engine python --single_cpu
```

### Performance Profiling
```bash
# Profile the simulation to identify bottlenecks
uv run python cardsharp/blackjack/blackjack.py --profile --num_games 1000
```

### Benchmark Output Example
```
Simulation completed.
Games played (excluding pushes): 9,137
Player wins: 4,368
Dealer wins: 4,973
Draws: 863
Net Earnings: $-1,890.00
Total Bets: $110,280.00
House Edge: 1.71%
Player win rate: 47.81%
Dealer win rate: 54.43%

Duration of simulation: 0.45 seconds
Games simulated per second: 22,056.42
```

## Conclusion

Speed without accuracy is meaningless. The fastest simulation is the one that gives correct results in the least time, not the one that gives wrong results quickly.