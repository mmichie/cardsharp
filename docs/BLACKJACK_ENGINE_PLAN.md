# Blackjack Engine Refactoring Plan

## Executive Summary

This document outlines a comprehensive plan to refactor the cardsharp blackjack engine using the same testability, correctness, and fairness principles successfully applied to the wintermute roulette engine.

**Goal**: Create a pure, testable BlackjackEngine with provable correctness and fairness.

---

## Current Architecture Analysis

### Codebase Overview

**Location**: `~/src/cardsharp/cardsharp/blackjack/`

**Size**: ~9,676 lines of Python code across 28 files

**Key Components**:
- `blackjack.py` (36KB) - Main game orchestration
- `state.py` (32KB) - Game state machine
- `environment.py` (38KB) - Game environment/simulation
- `casino.py` (28KB) - Casino-level operations
- `bankroll.py` (23KB) - Bet management
- `strategy.py` (22KB) - Playing strategies
- `rules.py` (12KB) - Game rules configuration
- `hand.py` (5KB) - BlackjackHand implementation
- `actor.py` (13KB) - Player/Dealer classes

**Testing**: 52 test files, including unit and integration tests

### Current Architecture Strengths

✅ **Event-Driven Design**
- Events system for decoupling (`cardsharp/events/emitter.py`)
- State changes emit events for verification
- Supports both sync and async handlers

✅ **Immutable State Pattern**
- State models in `cardsharp/state/models.py`
- Transitions via pure functions in `cardsharp/state/transitions.py`
- State never mutated, only new states created

✅ **Adapter Pattern**
- Platform isolation (`PlatformAdapter` interface)
- CLI, Web, Dummy adapters
- Good separation of rendering from logic

✅ **Strategy Pattern**
- Multiple playing strategies (Basic, Counting, Aggressive, Martingale)
- Pluggable strategy system

✅ **Performance Focus**
- Optimized caching in `BlackjackHand`
- Fast simulation mode (~22k games/second)
- Multiprocessing support (~350k games/second)

### Current Architecture Weaknesses

#### 1. **Testability Issues**

❌ **Tightly Coupled State Machine**
```python
# state.py has monolithic game state classes
class GameState(ABC):
    def handle(self, game) -> None:
        # Directly mutates game object
        # Hard to test in isolation
```
- State classes depend on entire game context
- Hard to test individual state transitions
- Mocking required for unit tests

❌ **Non-Injectable Dependencies**
```python
# shoe.py uses random.shuffle() directly
def shuffle(self):
    # Uses global random - can't inject for deterministic tests
    random.shuffle(self.cards)
```
- RNG not injectable (uses global `random`)
- Can't create deterministic tests
- Hard to verify fairness

❌ **Mixed Concerns**
```python
# blackjack.py mixes simulation, I/O, and game logic
def play_game(self, io_interface: IOInterface):
    # Game logic + I/O + statistics all mixed
```
- Game rules mixed with I/O
- Simulation logic mixed with game logic
- Hard to test rules in isolation

#### 2. **Correctness Challenges**

❌ **Complex State Dependencies**
- 7 different game states with complex transitions
- State transitions depend on mutable game object
- Hard to verify all state paths are correct

❌ **Implicit Game Rules**
- Rules scattered across state classes
- Dealer behavior in `DealersTurnState`
- Player options in `PlayersTurnState`
- No single source of truth for game mechanics

❌ **Side Effects Everywhere**
- State changes modify game object
- Hand evaluation has side effects (caching)
- Hard to reason about correctness

#### 3. **Fairness Verification**

❌ **Non-Verifiable RNG**
```python
# Using standard random module
import random
random.shuffle(self.cards)
```
- Not cryptographically secure
- Can't prove independence of shuffles
- Can't verify uniform distribution easily

❌ **Shuffle Implementation**
- Multiple shuffle types (perfect, riffle, strip)
- Riffle shuffle may not be truly random (only 4 shuffles by default)
- No tests proving shuffle fairness

❌ **No Fairness Proofs**
- No tests verifying correct probabilities
- No tests verifying house edge
- No tests proving non-gameability

#### 4. **Complexity**

❌ **Many Moving Parts**
- State machine + Events + Adapters + Strategies
- 28 files in blackjack module alone
- High cognitive load to understand flow

❌ **Performance Optimizations Complicate Logic**
- Caching in `BlackjackHand` adds complexity
- Fast path vs. accurate path tradeoffs
- Hard to verify optimizations don't break correctness

---

## Proposed Architecture: Pure BlackjackEngine

### API Design Requirements

The BlackjackEngine must be designed with developer experience and usability as first-class concerns:

1. **REPL-Friendly**: Easy to import and use interactively in IPython, Jupyter, or Python REPL
2. **Human-Readable**: Clear method names, intuitive types, self-documenting code
3. **Test Hand Construction**: Simple builder API for creating specific test scenarios
4. **Interactive Verification**: Built-in helpers for hand-by-hand accuracy testing
5. **Platform-Independent**: Usable in Discord bots, web apps, CLIs, or data analysis

See **BLACKJACK_API_DESIGN.md** for complete API design, usage examples, and interactive testing patterns.

### Design Philosophy (From Roulette Success)

Apply the same principles that made RouletteEngine successful:

1. **Pure Functions** - No side effects, deterministic
2. **Injectable RNG** - Deterministic testing via Protocol
3. **Immutable Results** - Frozen dataclasses prevent tampering
4. **Type Safety** - Enums and strong typing
5. **Separation of Concerns** - Engine vs. Platform
6. **Comprehensive Tests** - Prove correctness and fairness

### Layer Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Platform Layer                          │
│  - Discord/Web/CLI adapters                                │
│  - User interaction                                        │
│  - Visualization/Graphics                                  │
│  - Database/Persistence                                    │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────┐
│                 BlackjackEngine (Pure Logic)               │
│  - Game rules                                              │
│  - Hand evaluation                                         │
│  - Dealer play logic                                       │
│  - Win/loss determination                                  │
│  - Payout calculation                                      │
│  - Injectable RNG/Shoe                                     │
│  - NO side effects, NO I/O, NO platform code              │
└────────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. **BlackjackEngine** (New)

**Purpose**: Pure business logic for Blackjack

**Characteristics**:
- **Stateless**: Each method is independent
- **Deterministic**: Given same inputs, produces same outputs
- **Injectable**: RNG and Shoe can be injected for testing
- **Immutable**: All results are frozen dataclasses
- **Type-Safe**: Uses enums and strong types

**Core Types**:
```python
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

class Action(Enum):
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    SURRENDER = "surrender"
    INSURANCE = "insurance"

class HandOutcome(Enum):
    WIN = "win"
    LOSE = "lose"
    PUSH = "push"
    BLACKJACK = "blackjack"
    BUST = "bust"

@dataclass(frozen=True)
class HandResult:
    """Result of evaluating a single hand."""
    value: int
    is_soft: bool
    is_blackjack: bool
    is_bust: bool

@dataclass(frozen=True)
class RoundResult:
    """Result of a complete blackjack round."""
    player_hands: list[HandResult]
    dealer_hand: HandResult
    outcomes: list[HandOutcome]
    payouts: list[float]
    net_winnings: float

class ShuffleProtocol(Protocol):
    """Protocol for shuffling implementations."""
    def shuffle(self, cards: list[Card]) -> list[Card]: ...

class RandomProtocol(Protocol):
    """Protocol for random number generation."""
    def random(self) -> float: ...
```

**API Design**:
```python
class BlackjackEngine:
    """Pure business logic for Blackjack."""

    def __init__(
        self,
        rules: Rules,
        shuffle_fn: ShuffleProtocol | None = None,
        rng: RandomProtocol | None = None
    ):
        """Initialize engine with rules and optional injectable dependencies."""
        self.rules = rules
        self._shuffle_fn = shuffle_fn or SecureShuffler()
        self._rng = rng or SecureRNG()

    # Pure functions for hand evaluation
    @staticmethod
    def evaluate_hand(hand: list[Card]) -> HandResult:
        """Evaluate a hand to determine value, soft/hard, blackjack, bust."""
        ...

    @staticmethod
    def can_split(hand: list[Card]) -> bool:
        """Check if hand can be split."""
        ...

    @staticmethod
    def can_double(hand: list[Card], rules: Rules) -> bool:
        """Check if hand can be doubled."""
        ...

    # Pure functions for dealer logic
    @staticmethod
    def should_dealer_hit(hand: list[Card], rules: Rules) -> bool:
        """Determine if dealer should hit based on rules."""
        ...

    # Pure functions for outcomes
    @staticmethod
    def determine_outcome(
        player_hand: HandResult,
        dealer_hand: HandResult
    ) -> HandOutcome:
        """Determine outcome (win/lose/push)."""
        ...

    @staticmethod
    def calculate_payout(
        outcome: HandOutcome,
        bet_amount: float,
        rules: Rules
    ) -> float:
        """Calculate payout for an outcome."""
        ...

    # Main game flow
    def play_round(
        self,
        num_players: int = 1,
        bet_amounts: list[float] | None = None
    ) -> RoundResult:
        """Play a complete round and return results."""
        ...

    # Dealer simulation
    def play_dealer_hand(
        self,
        dealer_hand: list[Card],
        shoe: Shoe
    ) -> HandResult:
        """Play out dealer's hand according to rules."""
        ...
```

#### 2. **SecureShoe** (New)

**Purpose**: Cryptographically secure card dealing

```python
class SecureShoe:
    """Cryptographically secure shoe with injectable RNG."""

    def __init__(
        self,
        num_decks: int,
        rng: RandomProtocol | None = None,
        shuffle_fn: ShuffleProtocol | None = None
    ):
        self._rng = rng or SecureRNG()
        self._shuffle_fn = shuffle_fn or FisherYatesShuffle(self._rng)
        self._cards = self._build_shoe(num_decks)
        self._shuffle()

    def deal(self) -> Card:
        """Deal a single card."""
        if not self._cards:
            raise ValueError("Shoe is empty")
        return self._cards.pop()

    def _shuffle(self) -> None:
        """Shuffle the shoe using injected shuffler."""
        self._cards = self._shuffle_fn.shuffle(self._cards)
```

**Key Features**:
- Injectable RNG (can use `secrets` for production, deterministic for testing)
- Injectable shuffle algorithm (Fisher-Yates for true randomness)
- Provably fair shuffling
- Testable with deterministic RNG

#### 3. **Rules** (Enhanced)

Keep existing `Rules` class but make it immutable:

```python
@dataclass(frozen=True)
class Rules:
    """Immutable game rules configuration."""
    blackjack_payout: float = 1.5
    dealer_hit_soft_17: bool = True
    allow_split: bool = True
    allow_double_down: bool = True
    allow_insurance: bool = True
    allow_surrender: bool = True
    num_decks: int = 1
    min_bet: float = 1.0
    max_bet: float = 100.0
    # ... all other rules
```

---

## Testing Strategy

### Unit Tests (Target: 100+ tests)

#### 1. **Hand Evaluation Tests** (~30 tests)
```python
class TestHandEvaluation:
    def test_blackjack_ace_ten():
        """Test natural blackjack detection."""
        cards = [Card(Rank.ACE, Suit.SPADES), Card(Rank.TEN, Suit.HEARTS)]
        result = BlackjackEngine.evaluate_hand(cards)
        assert result.value == 21
        assert result.is_blackjack
        assert result.is_soft
        assert not result.is_bust

    def test_soft_17():
        """Test soft 17 evaluation."""
        cards = [Card(Rank.ACE, Suit.SPADES), Card(Rank.SIX, Suit.HEARTS)]
        result = BlackjackEngine.evaluate_hand(cards)
        assert result.value == 17
        assert result.is_soft
        assert not result.is_blackjack  # Not 2 cards only

    def test_hard_17():
        """Test hard 17 evaluation."""
        cards = [Card(Rank.TEN, Suit.SPADES), Card(Rank.SEVEN, Suit.HEARTS)]
        result = BlackjackEngine.evaluate_hand(cards)
        assert result.value == 17
        assert not result.is_soft
        assert not result.is_blackjack

    def test_bust():
        """Test bust detection."""
        cards = [
            Card(Rank.TEN, Suit.SPADES),
            Card(Rank.TEN, Suit.HEARTS),
            Card(Rank.FIVE, Suit.CLUBS)
        ]
        result = BlackjackEngine.evaluate_hand(cards)
        assert result.value == 25
        assert result.is_bust

    # Test all edge cases: multiple aces, face cards, soft hands going hard, etc.
```

#### 2. **Dealer Logic Tests** (~20 tests)
```python
class TestDealerLogic:
    def test_dealer_hits_16():
        """Test dealer must hit on 16."""
        hand = [Card(Rank.TEN, Suit.SPADES), Card(Rank.SIX, Suit.HEARTS)]
        rules = Rules(dealer_hit_soft_17=True)
        assert BlackjackEngine.should_dealer_hit(hand, rules)

    def test_dealer_stands_17():
        """Test dealer stands on hard 17."""
        hand = [Card(Rank.TEN, Suit.SPADES), Card(Rank.SEVEN, Suit.HEARTS)]
        rules = Rules(dealer_hit_soft_17=False)
        assert not BlackjackEngine.should_dealer_hit(hand, rules)

    def test_dealer_hits_soft_17_when_required():
        """Test dealer hits soft 17 when rules require."""
        hand = [Card(Rank.ACE, Suit.SPADES), Card(Rank.SIX, Suit.HEARTS)]
        rules = Rules(dealer_hit_soft_17=True)
        assert BlackjackEngine.should_dealer_hit(hand, rules)

    def test_dealer_stands_soft_17_when_not_required():
        """Test dealer stands on soft 17 when rules allow."""
        hand = [Card(Rank.ACE, Suit.SPADES), Card(Rank.SIX, Suit.HEARTS)]
        rules = Rules(dealer_hit_soft_17=False)
        assert not BlackjackEngine.should_dealer_hit(hand, rules)
```

#### 3. **Outcome Tests** (~15 tests)
```python
class TestOutcomes:
    def test_player_blackjack_beats_dealer_21():
        """Test natural blackjack beats dealer 21."""
        player = HandResult(value=21, is_soft=True, is_blackjack=True, is_bust=False)
        dealer = HandResult(value=21, is_soft=False, is_blackjack=False, is_bust=False)
        outcome = BlackjackEngine.determine_outcome(player, dealer)
        assert outcome == HandOutcome.BLACKJACK

    def test_player_bust_loses():
        """Test bust always loses."""
        player = HandResult(value=23, is_soft=False, is_blackjack=False, is_bust=True)
        dealer = HandResult(value=20, is_soft=False, is_blackjack=False, is_bust=False)
        outcome = BlackjackEngine.determine_outcome(player, dealer)
        assert outcome == HandOutcome.LOSE

    def test_push_on_equal_values():
        """Test push when values are equal."""
        player = HandResult(value=19, is_soft=False, is_blackjack=False, is_bust=False)
        dealer = HandResult(value=19, is_soft=False, is_blackjack=False, is_bust=False)
        outcome = BlackjackEngine.determine_outcome(player, dealer)
        assert outcome == HandOutcome.PUSH
```

#### 4. **Payout Tests** (~10 tests)
```python
class TestPayouts:
    def test_blackjack_pays_3_to_2():
        """Test blackjack pays 3:2 (1.5x)."""
        rules = Rules(blackjack_payout=1.5)
        payout = BlackjackEngine.calculate_payout(
            HandOutcome.BLACKJACK, bet_amount=100, rules=rules
        )
        assert payout == 150  # Win 150, total return 250

    def test_regular_win_pays_1_to_1():
        """Test regular win pays 1:1."""
        payout = BlackjackEngine.calculate_payout(
            HandOutcome.WIN, bet_amount=100, rules=Rules()
        )
        assert payout == 100  # Win 100, total return 200

    def test_push_returns_bet():
        """Test push returns original bet."""
        payout = BlackjackEngine.calculate_payout(
            HandOutcome.PUSH, bet_amount=100, rules=Rules()
        )
        assert payout == 0  # No change

    def test_loss_loses_bet():
        """Test loss forfeits bet."""
        payout = BlackjackEngine.calculate_payout(
            HandOutcome.LOSE, bet_amount=100, rules=Rules()
        )
        assert payout == -100
```

#### 5. **Shuffle Fairness Tests** (~15 tests)
```python
class TestShuffleFairness:
    def test_fisher_yates_uniform_distribution():
        """Test Fisher-Yates produces uniform permutations."""
        rng = DeterministicRNG(seed=42)
        shuffler = FisherYatesShuffle(rng)

        # Shuffle small deck many times
        deck = [Card(Rank.ACE, Suit.SPADES), Card(Rank.TWO, Suit.HEARTS)]
        permutations = []

        for _ in range(10000):
            shuffled = shuffler.shuffle(deck.copy())
            permutations.append(tuple(shuffled))

        # Both permutations should appear roughly equally
        from collections import Counter
        counts = Counter(permutations)
        assert len(counts) == 2  # Two possible orderings

        # Chi-squared test for uniformity
        expected = 5000
        tolerance = 300  # 6% tolerance
        for count in counts.values():
            assert abs(count - expected) < tolerance

    def test_secure_rng_independence():
        """Test that consecutive shuffles are independent."""
        shoe1 = SecureShoe(num_decks=1)
        shoe2 = SecureShoe(num_decks=1)

        # Deal cards and compare
        cards1 = [shoe1.deal() for _ in range(10)]
        cards2 = [shoe2.deal() for _ in range(10)]

        # Should be different (probability of same is astronomical)
        assert cards1 != cards2
```

#### 6. **Complete Round Tests** (~20 tests)
```python
class TestCompleteRound:
    def test_deterministic_round_with_fixed_rng():
        """Test complete round with deterministic RNG."""
        # Fixed seed produces same shuffle
        rng = DeterministicRNG(seed=42)
        engine = BlackjackEngine(rules=Rules(), rng=rng)

        result1 = engine.play_round(num_players=1, bet_amounts=[100])

        # Reset with same seed
        rng = DeterministicRNG(seed=42)
        engine = BlackjackEngine(rules=Rules(), rng=rng)

        result2 = engine.play_round(num_players=1, bet_amounts=[100])

        # Results should be identical
        assert result1 == result2

    def test_multiple_hands_split():
        """Test round with split hands."""
        # Create scenario where player has pair
        # ... (set up deterministic deck)
        # Verify split logic works correctly
```

### Integration Tests (~30 tests)

Test engine integration with existing components:
- Shoe integration
- Strategy integration
- Multi-player scenarios
- Edge cases (insurance, surrender, etc.)

### Fairness Tests (~10 tests)

```python
class TestFairness:
    def test_house_edge_single_deck():
        """Verify house edge matches mathematical expectation for single deck."""
        engine = BlackjackEngine(rules=Rules(num_decks=1))

        rounds = 100000
        total_wagered = rounds * 100
        total_won = 0

        for _ in range(rounds):
            result = engine.play_round(num_players=1, bet_amounts=[100])
            total_won += result.net_winnings + 100  # Add back bet

        return_rate = total_won / total_wagered
        expected_rate = 0.995  # ~0.5% house edge for basic strategy

        # Allow 1% tolerance for variance
        assert abs(return_rate - expected_rate) < 0.01

    def test_blackjack_probability():
        """Verify blackjack occurs at correct frequency."""
        # Mathematical probability: (4/13) * (16/52 - 4/13) ≈ 4.83%
        # For single deck
        ...
```

---

## Migration Plan

### Phase 1: Core Engine (Weeks 1-2)

**Goals**:
- Create `BlackjackEngine` class
- Implement pure hand evaluation functions
- Implement dealer logic
- Implement outcome determination
- Implement payout calculation
- Write 50+ unit tests

**Deliverables**:
- `cardsharp/engine/blackjack_engine.py` (new)
- `tests/engine/test_blackjack_engine.py` (new)
- All core logic tests passing

### Phase 2: Secure RNG & Shuffle (Week 3)

**Goals**:
- Create `SecureRNG` class
- Create `FisherYatesShuffle` class
- Create `SecureShoe` class
- Prove shuffle fairness via tests

**Deliverables**:
- `cardsharp/common/secure_rng.py` (new)
- `cardsharp/common/secure_shuffle.py` (new)
- `cardsharp/common/secure_shoe.py` (new)
- Fairness tests passing

### Phase 3: Round Simulation (Week 4)

**Goals**:
- Implement complete round logic
- Support multiple players
- Support splits, doubles, insurance
- Comprehensive round tests

**Deliverables**:
- Complete `BlackjackEngine.play_round()`
- 20+ round simulation tests
- Integration tests with existing components

### Phase 4: Adapter Integration (Week 5)

**Goals**:
- Update existing adapters to use new engine
- Maintain backward compatibility
- Update simulations to use new engine

**Deliverables**:
- Updated `blackjack.py` to use engine
- Backward compatible API
- All existing tests still passing

### Phase 5: Documentation & Validation (Week 6)

**Goals**:
- Comprehensive documentation
- Performance benchmarks
- Fairness validation reports
- Migration guide

**Deliverables**:
- `BLACKJACK_ENGINE.md` (architecture doc)
- `BLACKJACK_API_DESIGN.md` (API design and usage examples) ✅ **COMPLETED**
- `FAIRNESS_PROOF.md` (mathematical proofs)
- Performance comparison report
- Migration guide for users

---

## Key Architectural Decisions

### 1. **Pure Functions vs. State Machine**

**Decision**: Use pure functions for core logic, keep state machine for orchestration

**Rationale**:
- Pure functions are easier to test
- State machine still useful for game flow
- State machine delegates to pure functions
- Best of both worlds

### 2. **Injectable Dependencies**

**Decision**: Inject RNG and shuffle algorithm via Protocol

**Rationale**:
- Enables deterministic testing
- Proves fairness via tests
- Maintains flexibility
- No performance penalty

### 3. **Immutable Results**

**Decision**: All results are frozen dataclasses

**Rationale**:
- Prevents tampering
- Thread-safe
- Easier to reason about
- Matches roulette pattern

### 4. **Separation of Concerns**

**Decision**: Engine has zero I/O, zero platform code

**Rationale**:
- Pure logic is testable
- Can be used in any platform
- Easy to verify correctness
- Reduces complexity

### 5. **Keep Existing Architecture**

**Decision**: Don't replace event system, adapters, or strategies

**Rationale**:
- Those components work well
- Focus on core game logic
- Minimize disruption
- Incremental improvement

---

## Success Criteria

### Correctness ✅
- [ ] 100+ unit tests covering all game rules
- [ ] All hand evaluation edge cases tested
- [ ] All dealer logic scenarios tested
- [ ] All outcome permutations tested
- [ ] All payout calculations verified

### Fairness ✅
- [ ] Shuffle fairness proven via statistical tests
- [ ] House edge verified mathematically
- [ ] Blackjack probability verified
- [ ] No way to game the system (proven)
- [ ] Cryptographically secure RNG

### Testability ✅
- [ ] All core logic is pure functions
- [ ] Deterministic tests possible
- [ ] No mocking required for unit tests
- [ ] 100% test coverage of engine
- [ ] Fast test execution (<5 seconds)

### Maintainability ✅
- [ ] Clear separation of concerns
- [ ] Single source of truth for rules
- [ ] Type-safe implementation
- [ ] Comprehensive documentation
- [ ] Easy to extend

### Performance ✅
- [ ] No performance regression
- [ ] Maintain 20k+ games/second
- [ ] Pure functions can be optimized
- [ ] Benchmarks in place

---

## Comparison to Roulette Refactoring

### Similarities

| Aspect | Roulette | Blackjack |
|--------|----------|-----------|
| Pure engine | ✅ RouletteEngine | ✅ BlackjackEngine |
| Injectable RNG | ✅ Via Protocol | ✅ Via Protocol |
| Immutable results | ✅ SpinResult, BetOutcome | ✅ HandResult, RoundResult |
| Type safety | ✅ BetType, Color enums | ✅ Action, HandOutcome enums |
| Comprehensive tests | ✅ 53 tests | ✅ 100+ tests |
| Fairness proofs | ✅ Via tests | ✅ Via tests |
| Documentation | ✅ ROULETTE_ARCHITECTURE.md | ✅ BLACKJACK_ENGINE.md |

### Differences (Due to Blackjack Complexity)

| Aspect | Roulette | Blackjack |
|--------|----------|-----------|
| **Game Complexity** | Simple (single spin) | Complex (multi-decision) |
| **State Management** | Stateless | Multi-hand state |
| **Number of Tests** | 53 | 100+ (more complex) |
| **Core Logic Size** | ~300 lines | ~800 lines (estimated) |
| **Edge Cases** | Few (38 numbers) | Many (splits, doubles, etc.) |
| **Existing Architecture** | Minimal | Event-driven, state machine |
| **Migration Effort** | Low (new code) | Medium (integration) |

### Challenges Specific to Blackjack

1. **Multiple Hands**: Splits create multiple hands per player
2. **Sequential Decisions**: Hit/stand/double/split are sequential
3. **Dealer Logic**: Complex rules for dealer play
4. **Insurance**: Side bet with different payout
5. **Surrender**: Early/late variations
6. **Variants**: Multiple rule variations (European, Spanish 21, etc.)

**Solution**: Keep complexity in engine but make it testable via:
- Pure functions for each decision point
- Immutable hand state
- Clear separation of player vs. dealer logic
- Comprehensive test coverage for all paths

---

## Estimated Effort

**Total Effort**: 6 weeks (1 developer, part-time)

| Phase | Effort | Risk |
|-------|--------|------|
| Phase 1: Core Engine | 2 weeks | Low |
| Phase 2: RNG & Shuffle | 1 week | Low |
| Phase 3: Round Simulation | 1 week | Medium |
| Phase 4: Adapter Integration | 1 week | Medium |
| Phase 5: Documentation | 1 week | Low |

**Risk Factors**:
- Integration with existing event system (Medium)
- Performance regression (Low - pure functions are fast)
- Breaking existing tests (Medium - need careful migration)
- Missed edge cases (Low - comprehensive testing will catch)

---

## Conclusion

By applying the same principles used in the successful RouletteEngine refactoring, we can create a BlackjackEngine that is:

✅ **Testable**: Pure functions, injectable dependencies, deterministic
✅ **Correct**: Comprehensive tests prove all rules work
✅ **Fair**: Cryptographically secure RNG, provable fairness
✅ **Maintainable**: Clear architecture, type-safe, well-documented

The increased complexity of blackjack (compared to roulette) is manageable through:
- Breaking down into pure functions
- Comprehensive test coverage (100+ tests)
- Incremental migration (keep existing architecture)
- Clear documentation

**Next Steps**:
1. Review and approve this plan
2. Review the API design in `BLACKJACK_API_DESIGN.md`
3. Create GitHub issue/project for tracking
4. Start Phase 1: Core Engine implementation
5. Iterate based on feedback

**Success Metric**: Same level of confidence in correctness and fairness as RouletteEngine, with provable guarantees via comprehensive tests.

---

## Additional Resources

- **BLACKJACK_API_DESIGN.md** - Comprehensive API design for REPL-friendly usage, test hand construction, and developer experience
