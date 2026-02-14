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

## Running Performance Benchmarks

### Basic Benchmark (Multiprocessing)
```bash
# Default simulation uses multiprocessing for ~350,000 games/second
uv run python cardsharp/blackjack/blackjack.py --simulate --num_games 10000
```

### Single-threaded Benchmark
```bash
# Use --single_cpu to disable multiprocessing (~22,000 games/second)
uv run python cardsharp/blackjack/blackjack.py --simulate --num_games 10000 --single_cpu
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