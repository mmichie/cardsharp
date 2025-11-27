# BlackjackEngine: Pure Functional Blackjack Engine

## Executive Summary

This document outlines the design and implementation of a pure, testable BlackjackEngine with provable correctness and fairness, applying the same principles successfully used in the RouletteEngine refactoring.

**Goal**: Replace the existing state machine-based blackjack implementation with a pure functional engine that is:
- **Testable**: Pure functions, injectable dependencies, deterministic
- **Correct**: Comprehensive tests prove all rules work
- **Fair**: Cryptographically secure RNG, provable fairness
- **Maintainable**: Clear architecture, type-safe, well-documented
- **Developer-Friendly**: REPL-friendly API, intuitive usage, self-documenting

**Migration Strategy**: Big bang replacement - implement full feature set, comprehensive testing, then cutover in one release.

---

## Design Philosophy

### Core Principles

1. **Pure Functions** - No side effects, deterministic behavior
2. **Injectable Dependencies** - Deterministic testing via Protocol interfaces
3. **Immutable Results** - Frozen dataclasses prevent tampering
4. **Type Safety** - Enums and strong typing throughout
5. **Functional Composition** - Replace state machine with pure functional composition
6. **Developer Experience** - API designed for human readability and ease of use
7. **Performance Through Purity** - Accept some performance hit for correctness guarantees

### API Design Requirements

The BlackjackEngine must be designed with developer experience as a first-class concern:

1. **REPL-Friendly**: Easy to import and use interactively in IPython, Jupyter, or Python REPL
2. **Human-Readable**: Clear method names, intuitive types, self-documenting code
3. **Scenario Construction**: First-class API for building deterministic test scenarios
4. **Platform-Independent**: Usable in Discord bots, web apps, CLIs, or data analysis
5. **One Style**: Single consistent API (no shorthand aliases)
6. **Poker Notation**: Primary card format is poker notation (e.g., "AS KH")

### Lessons from RouletteEngine

Apply successful patterns from the roulette refactoring:

✅ **What Worked**:
- Pure engine with zero I/O, zero platform code
- Injectable RNG via Protocol for deterministic testing
- Immutable results (frozen dataclasses)
- Comprehensive fairness tests
- Clear separation from platform adapters

✅ **Apply to Blackjack**:
- Same purity guarantees
- Same testability approach
- Same fairness verification
- Scaled up for blackjack's complexity (100+ tests vs. 53)

---

## Architecture Overview

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
│              BlackjackEngine (Pure Logic)                  │
│  - Hand evaluation (pure functions)                        │
│  - Dealer logic (pure functions)                           │
│  - Outcome determination (pure functions)                  │
│  - Payout calculation (pure functions)                     │
│  - Round orchestration (functional composition)            │
│  - Injectable RNG/Shoe                                     │
│  - NO side effects, NO I/O, NO platform code              │
└────────────────────────────────────────────────────────────┘
```

### Functional Composition Over State Machine

**Current Approach** (State Machine):
```python
# Complex state machine with 7 states
class BettingState(GameState):
    def handle(self, game) -> None:
        # Mutates game object
        game.transition_to(DealingState())
```

**New Approach** (Pure Functional):
```python
# Pure functional composition
def play_round(
    shoe: Shoe,
    bet_amounts: list[float],
    rules: Rules
) -> RoundResult:
    """Pure function - no state machine needed."""
    # Deal initial cards
    hands = deal_initial_hands(shoe, num_players=len(bet_amounts))

    # Play player hands (pure function composition)
    player_results = [
        play_player_hand(hand, shoe, rules)
        for hand in hands
    ]

    # Play dealer hand
    dealer_result = play_dealer_hand(hands.dealer, shoe, rules)

    # Determine outcomes
    outcomes = [
        determine_outcome(player, dealer_result)
        for player in player_results
    ]

    # Calculate payouts
    payouts = [
        calculate_payout(outcome, bet, rules)
        for outcome, bet in zip(outcomes, bet_amounts)
    ]

    return RoundResult(
        player_hands=player_results,
        dealer_hand=dealer_result,
        outcomes=outcomes,
        payouts=payouts,
        net_winnings=sum(payouts)
    )
```

---

## Core Type System

### Enums

```python
from enum import Enum

class Action(Enum):
    """Player actions available in blackjack."""
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    SURRENDER = "surrender"
    INSURANCE = "insurance"

class Outcome(Enum):
    """Possible outcomes for a hand."""
    WIN = "win"
    LOSE = "lose"
    PUSH = "push"
    BLACKJACK = "blackjack"
    SURRENDER = "surrender"
    INSURANCE_WIN = "insurance_win"
    INSURANCE_LOSE = "insurance_lose"
```

### Immutable Results

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class HandResult:
    """Result of evaluating a single hand.

    Attributes:
        cards: The cards in the hand (poker notation, e.g., ["AS", "KH"])
        value: The numeric value of the hand (0-21, or >21 if bust)
        is_soft: True if hand contains an ace counted as 11
        is_blackjack: True if natural blackjack (ace + 10-value in 2 cards)
        is_bust: True if value > 21
    """
    cards: tuple[str, ...]
    value: int
    is_soft: bool
    is_blackjack: bool
    is_bust: bool

    def __str__(self) -> str:
        """Human-readable string representation."""
        cards_str = " ".join(self.cards)
        status = []
        if self.is_blackjack:
            status.append("Blackjack!")
        elif self.is_bust:
            status.append("Bust")
        elif self.is_soft:
            status.append("Soft")

        status_str = f" ({', '.join(status)})" if status else ""
        return f"{cards_str} = {self.value}{status_str}"

@dataclass(frozen=True)
class RoundResult:
    """Result of a complete blackjack round.

    Attributes:
        player_hands: Results for each player hand (may be >1 if split)
        dealer_hand: Result of dealer's hand
        outcomes: Outcome for each player hand
        payouts: Payout for each player hand
        net_winnings: Total net winnings for the round
    """
    player_hands: tuple[HandResult, ...]
    dealer_hand: HandResult
    outcomes: tuple[Outcome, ...]
    payouts: tuple[float, ...]
    net_winnings: float

@dataclass(frozen=True)
class Rules:
    """Immutable game rules configuration.

    All blackjack rule variations are configured here.
    """
    blackjack_payout: float = 1.5  # 3:2 payout
    dealer_hit_soft_17: bool = True
    allow_split: bool = True
    allow_resplit: bool = True
    max_splits: int = 3
    allow_double_down: bool = True
    allow_double_after_split: bool = True
    allow_insurance: bool = True
    allow_surrender: bool = True
    allow_late_surrender_only: bool = True
    num_decks: int = 6
    min_bet: float = 1.0
    max_bet: float = 1000.0
    penetration: float = 0.75  # Deal 75% of shoe before reshuffling
```

### Injectable Dependencies

```python
from typing import Protocol

class RandomProtocol(Protocol):
    """Protocol for random number generation."""
    def random(self) -> float:
        """Return random float in [0.0, 1.0)."""
        ...

class ShuffleProtocol(Protocol):
    """Protocol for shuffling implementations."""
    def shuffle(self, cards: list[str]) -> list[str]:
        """Shuffle cards and return shuffled deck."""
        ...
```

---

## Core API Design

### BlackjackEngine Class

```python
class BlackjackEngine:
    """Pure functional blackjack engine.

    All methods are pure functions or functional compositions.
    No state is maintained between method calls.
    """

    def __init__(
        self,
        rules: Rules | None = None,
        rng: RandomProtocol | None = None,
        shuffle_fn: ShuffleProtocol | None = None
    ):
        """Initialize engine with rules and optional injectable dependencies.

        Args:
            rules: Game rules configuration (uses standard Vegas rules if None)
            rng: Random number generator (uses SecureRNG if None)
            shuffle_fn: Shuffle algorithm (uses FisherYates if None)
        """
        self.rules = rules or Rules()
        self._rng = rng or SecureRNG()
        self._shuffle_fn = shuffle_fn or FisherYatesShuffle(self._rng)

    # ===================================================================
    # Pure Hand Evaluation Functions
    # ===================================================================

    @staticmethod
    def evaluate_hand(cards: list[str]) -> HandResult:
        """Evaluate a hand to determine value, soft/hard, blackjack, bust.

        Args:
            cards: List of cards in poker notation (e.g., ["AS", "KH"])

        Returns:
            HandResult with all hand properties

        Examples:
            >>> engine = BlackjackEngine()
            >>> result = engine.evaluate_hand(["AS", "KH"])
            >>> print(result)
            AS KH = 21 (Blackjack!)

            >>> result = engine.evaluate_hand(["AS", "6H"])
            >>> print(result)
            AS 6H = 17 (Soft)

            >>> result = engine.evaluate_hand(["10S", "6H", "5C"])
            >>> print(result)
            10S 6H 5C = 21
        """
        # Implementation: Pure function, no side effects
        ...

    @staticmethod
    def can_split(cards: list[str]) -> bool:
        """Check if hand can be split.

        Args:
            cards: List of cards in poker notation

        Returns:
            True if hand is a pair and can be split

        Examples:
            >>> BlackjackEngine.can_split(["8S", "8H"])
            True
            >>> BlackjackEngine.can_split(["KS", "QH"])
            True  # Both 10-value cards
            >>> BlackjackEngine.can_split(["AS", "KH"])
            False  # Not a pair
        """
        ...

    @staticmethod
    def can_double(cards: list[str], rules: Rules) -> bool:
        """Check if hand can be doubled.

        Args:
            cards: List of cards in poker notation
            rules: Game rules configuration

        Returns:
            True if hand can be doubled according to rules

        Examples:
            >>> rules = Rules(allow_double_down=True)
            >>> BlackjackEngine.can_double(["AS", "6H"], rules)
            True  # Soft 17, 2 cards
            >>> BlackjackEngine.can_double(["10S", "6H", "5C"], rules)
            False  # More than 2 cards
        """
        ...

    # ===================================================================
    # Pure Dealer Logic Functions
    # ===================================================================

    @staticmethod
    def should_dealer_hit(cards: list[str], rules: Rules) -> bool:
        """Determine if dealer should hit based on rules.

        Args:
            cards: Dealer's cards in poker notation
            rules: Game rules configuration

        Returns:
            True if dealer should hit

        Examples:
            >>> rules = Rules(dealer_hit_soft_17=True)
            >>> BlackjackEngine.should_dealer_hit(["AS", "6H"], rules)
            True  # Soft 17, dealer must hit

            >>> rules = Rules(dealer_hit_soft_17=False)
            >>> BlackjackEngine.should_dealer_hit(["AS", "6H"], rules)
            False  # Soft 17, dealer stands

            >>> BlackjackEngine.should_dealer_hit(["10S", "6H"], rules)
            True  # Hard 16, always hit

            >>> BlackjackEngine.should_dealer_hit(["10S", "7H"], rules)
            False  # Hard 17, always stand
        """
        ...

    # ===================================================================
    # Pure Outcome Determination Functions
    # ===================================================================

    @staticmethod
    def determine_outcome(
        player_hand: HandResult,
        dealer_hand: HandResult
    ) -> Outcome:
        """Determine outcome by comparing player vs dealer.

        Args:
            player_hand: Player's hand result
            dealer_hand: Dealer's hand result

        Returns:
            Outcome enum value

        Examples:
            >>> player = HandResult(["AS", "KH"], 21, True, True, False)
            >>> dealer = HandResult(["10S", "9H", "2C"], 21, False, False, False)
            >>> BlackjackEngine.determine_outcome(player, dealer)
            <Outcome.BLACKJACK: 'blackjack'>  # Natural beats 21

            >>> player = HandResult(["10S", "9H"], 19, False, False, False)
            >>> dealer = HandResult(["10S", "8H"], 18, False, False, False)
            >>> BlackjackEngine.determine_outcome(player, dealer)
            <Outcome.WIN: 'win'>

            >>> player = HandResult(["10S", "9H"], 19, False, False, False)
            >>> dealer = HandResult(["10S", "9H"], 19, False, False, False)
            >>> BlackjackEngine.determine_outcome(player, dealer)
            <Outcome.PUSH: 'push'>
        """
        ...

    @staticmethod
    def calculate_payout(
        outcome: Outcome,
        bet_amount: float,
        rules: Rules
    ) -> float:
        """Calculate payout for an outcome.

        Args:
            outcome: The outcome (win/lose/push/blackjack)
            bet_amount: The original bet amount
            rules: Game rules (for blackjack payout ratio)

        Returns:
            Net winnings (positive for win, negative for loss, 0 for push)

        Examples:
            >>> rules = Rules(blackjack_payout=1.5)
            >>> BlackjackEngine.calculate_payout(Outcome.BLACKJACK, 100, rules)
            150.0  # Win $150 (3:2 payout)

            >>> BlackjackEngine.calculate_payout(Outcome.WIN, 100, rules)
            100.0  # Win $100 (1:1 payout)

            >>> BlackjackEngine.calculate_payout(Outcome.PUSH, 100, rules)
            0.0  # No change

            >>> BlackjackEngine.calculate_payout(Outcome.LOSE, 100, rules)
            -100.0  # Lose $100
        """
        ...

    # ===================================================================
    # Game Flow (Functional Composition)
    # ===================================================================

    def play_round(
        self,
        bet_amounts: list[float],
        shoe: Shoe | None = None
    ) -> RoundResult:
        """Play a complete round using functional composition.

        This is the main entry point for playing blackjack.
        Composes pure functions to execute a complete round.

        Args:
            bet_amounts: Bet amount for each player
            shoe: Optional shoe (creates new one if None)

        Returns:
            RoundResult with complete outcome

        Examples:
            >>> engine = BlackjackEngine()
            >>> result = engine.play_round(bet_amounts=[100])
            >>> print(result.player_hands[0])
            10S 9H = 19
            >>> print(result.dealer_hand)
            KH 8C = 18
            >>> print(result.outcomes[0])
            Outcome.WIN
            >>> print(result.payouts[0])
            100.0
        """
        ...

    def play_dealer_hand(
        self,
        initial_cards: list[str],
        shoe: Shoe
    ) -> HandResult:
        """Play out dealer's hand according to rules.

        Pure functional composition of dealer logic.

        Args:
            initial_cards: Dealer's initial cards
            shoe: Shoe to deal from

        Returns:
            Final dealer hand result

        Examples:
            >>> engine = BlackjackEngine()
            >>> shoe = Shoe.from_cards(["3C", "4D", "5H"])
            >>> result = engine.play_dealer_hand(["10S", "6H"], shoe)
            >>> print(result)
            10S 6H 3C = 19  # Dealer hit 16, got 3, stands on 19
        """
        ...
```

---

## Scenario Construction API

### HandBuilder - First-Class API

```python
class HandBuilder:
    """Fluent builder for constructing specific hands.

    This is a first-class API feature (not just for testing).
    Use it anywhere you need to construct deterministic scenarios:
    - Testing
    - Discord bots
    - Web applications
    - Data analysis
    - Strategy verification
    """

    def __init__(self):
        """Start building a hand."""
        self._cards: list[str] = []

    def card(self, rank: str, suit: str) -> HandBuilder:
        """Add a specific card.

        Args:
            rank: Card rank ("A", "2"-"10", "J", "Q", "K")
            suit: Card suit ("S", "H", "D", "C")

        Returns:
            Self for method chaining

        Examples:
            >>> hand = (HandBuilder()
            ...     .card("A", "S")
            ...     .card("K", "H")
            ...     .build())
            >>> print(hand)
            ['AS', 'KH']
        """
        self._cards.append(f"{rank}{suit}")
        return self

    def ace(self, suit: str = "S") -> HandBuilder:
        """Add an ace.

        Examples:
            >>> hand = HandBuilder().ace().ten().build()
            ['AS', '10S']
        """
        return self.card("A", suit)

    def ten(self, suit: str = "S") -> HandBuilder:
        """Add a 10.

        Examples:
            >>> hand = HandBuilder().ten("H").ten("D").build()
            ['10H', '10D']
        """
        return self.card("10", suit)

    def face(self, face: str = "K", suit: str = "S") -> HandBuilder:
        """Add a face card (J, Q, K).

        Args:
            face: Face card rank ("J", "Q", "K")
            suit: Card suit

        Examples:
            >>> hand = HandBuilder().face("K").face("Q", "H").build()
            ['KS', 'QH']
        """
        return self.card(face, suit)

    def value(self, value: int, suit: str = "S") -> HandBuilder:
        """Add a card with specific value.

        Args:
            value: Card value (1-10, where 1=Ace, 10=any 10-value)
            suit: Card suit

        Examples:
            >>> hand = HandBuilder().value(11).value(10).build()  # Ace + Ten
            ['AS', '10S']
        """
        if value == 1 or value == 11:
            return self.ace(suit)
        elif value == 10:
            return self.ten(suit)
        else:
            return self.card(str(value), suit)

    @classmethod
    def from_notation(cls, notation: str) -> list[str]:
        """Parse poker notation string.

        Args:
            notation: Space-separated cards (e.g., "AS KH")

        Returns:
            List of cards

        Examples:
            >>> HandBuilder.from_notation("AS KH")
            ['AS', 'KH']
            >>> HandBuilder.from_notation("10S 6H 5C")
            ['10S', '6H', '5C']
        """
        return notation.split()

    @classmethod
    def from_values(cls, values: list[int]) -> list[str]:
        """Create hand from just values.

        Args:
            values: List of card values (1=Ace, 2-10, 11=Ace)

        Returns:
            List of cards with default suits

        Examples:
            >>> HandBuilder.from_values([11, 10])
            ['AS', '10S']
            >>> HandBuilder.from_values([10, 6, 5])
            ['10S', '6H', '5D']
        """
        suits = ["S", "H", "D", "C"]
        builder = cls()
        for i, value in enumerate(values):
            builder.value(value, suits[i % 4])
        return builder.build()

    def build(self) -> list[str]:
        """Build the final hand.

        Returns:
            List of cards in poker notation
        """
        return self._cards.copy()
```

### Scenario - First-Class API

```python
@dataclass
class ScenarioData:
    """Data for a complete game scenario."""
    player_hands: list[list[str]]
    dealer_hand: list[str]
    bet_amounts: list[float]
    actions: list[list[Action]]  # Actions for each player

class Scenario:
    """Builder for complete game scenarios.

    First-class API for constructing deterministic scenarios.
    """

    def __init__(self):
        """Start building a scenario."""
        self._player_hands: list[list[str]] = []
        self._dealer_hand: list[str] = []
        self._bet_amounts: list[float] = []
        self._actions: list[list[Action]] = []

    def player_hand(self, *cards: str) -> Scenario:
        """Set a player's cards.

        Args:
            cards: Cards in poker notation

        Returns:
            Self for method chaining

        Examples:
            >>> scenario = (Scenario()
            ...     .player_hand("AS", "KH")
            ...     .dealer_hand("10D", "9C")
            ...     .bet(100)
            ...     .build())
        """
        self._player_hands.append(list(cards))
        return self

    def dealer_hand(self, *cards: str) -> Scenario:
        """Set dealer's cards.

        Args:
            cards: Cards in poker notation

        Returns:
            Self for method chaining
        """
        self._dealer_hand = list(cards)
        return self

    def dealer_showing(self, card: str) -> Scenario:
        """Set dealer's up card.

        Args:
            card: Dealer's visible card

        Returns:
            Self for method chaining

        Examples:
            >>> scenario = (Scenario()
            ...     .dealer_showing("AD")
            ...     .dealer_hole("KH")
            ...     .build())
        """
        if not self._dealer_hand:
            self._dealer_hand = [card]
        else:
            self._dealer_hand[0] = card
        return self

    def dealer_hole(self, card: str) -> Scenario:
        """Set dealer's hole card.

        Args:
            card: Dealer's hidden card

        Returns:
            Self for method chaining
        """
        if len(self._dealer_hand) < 2:
            self._dealer_hand.append(card)
        else:
            self._dealer_hand[1] = card
        return self

    def bet(self, amount: float) -> Scenario:
        """Add a bet amount.

        Args:
            amount: Bet amount for the last added player

        Returns:
            Self for method chaining
        """
        self._bet_amounts.append(amount)
        return self

    def action(self, *actions: Action) -> Scenario:
        """Add player actions.

        Args:
            actions: Actions for the last added player

        Returns:
            Self for method chaining

        Examples:
            >>> scenario = (Scenario()
            ...     .player_hand("10S", "10H")
            ...     .action(Action.SPLIT)
            ...     .build())
        """
        self._actions.append(list(actions))
        return self

    def build(self) -> ScenarioData:
        """Build the scenario.

        Returns:
            ScenarioData with all scenario information
        """
        return ScenarioData(
            player_hands=self._player_hands,
            dealer_hand=self._dealer_hand,
            bet_amounts=self._bet_amounts,
            actions=self._actions
        )
```

---

## Interactive Usage Examples

### Quick Start - IPython/Jupyter

```python
# Start IPython
>>> from cardsharp.engine import BlackjackEngine, HandBuilder, Scenario

# Create engine with standard rules
>>> engine = BlackjackEngine()

# Or customize rules
>>> engine = BlackjackEngine(
...     rules=Rules(
...         blackjack_payout=1.5,
...         dealer_hit_soft_17=True,
...         num_decks=6
...     )
... )

# Evaluate any hand instantly
>>> result = engine.evaluate_hand(["AS", "KH"])
>>> print(result)
AS KH = 21 (Blackjack!)

>>> result = engine.evaluate_hand(["10S", "6H", "5C"])
>>> print(result)
10S 6H 5C = 21

>>> result = engine.evaluate_hand(["AS", "AH", "9C"])
>>> print(result)
AS AH 9C = 21 (Soft)

# Check dealer behavior
>>> engine.should_dealer_hit(["AS", "6H"], engine.rules)
True  # Soft 17, dealer hits

>>> engine.should_dealer_hit(["10S", "7H"], engine.rules)
False  # Hard 17, dealer stands

# Compare hands
>>> player = engine.evaluate_hand(["10S", "10H"])
>>> dealer = engine.evaluate_hand(["10S", "9H"])
>>> outcome = engine.determine_outcome(player, dealer)
>>> print(outcome)
Outcome.WIN

# Calculate payout
>>> payout = engine.calculate_payout(Outcome.BLACKJACK, 100, engine.rules)
>>> print(f"${payout:.2f}")
$150.00  # 3:2 payout
```

### Building Test Scenarios

```python
# Build specific hands easily
>>> hand = (HandBuilder()
...     .ace("S")
...     .ten("H")
...     .build())
>>> result = engine.evaluate_hand(hand)
>>> print(result)
AS 10H = 21 (Blackjack!)

# Or use fluent API
>>> hand = (HandBuilder()
...     .card("A", "S")
...     .card("6", "H")
...     .card("4", "C")
...     .build())
>>> result = engine.evaluate_hand(hand)
>>> print(result)
AS 6H 4C = 21 (Soft)

# Or use notation
>>> hand = HandBuilder.from_notation("AS 6H 4C")
>>> hand = HandBuilder.from_values([11, 6, 4])

# Build complete scenarios
>>> scenario = (Scenario()
...     .player_hand("AS", "KH")
...     .dealer_hand("10D", "9C")
...     .bet(100)
...     .build())

>>> # Play the scenario
>>> result = engine.play_scenario(scenario)
>>> print(result.player_hands[0])
AS KH = 21 (Blackjack!)
>>> print(result.dealer_hand)
10D 9C = 19
>>> print(result.outcomes[0])
Outcome.BLACKJACK
>>> print(f"Payout: ${result.payouts[0]:.2f}")
Payout: $150.00
```

### Edge Case Testing

```python
# Test multiple aces
>>> hand = (HandBuilder()
...     .ace("S")
...     .ace("H")
...     .ace("C")
...     .ace("D")
...     .build())
>>> result = engine.evaluate_hand(hand)
>>> print(result)
AS AH AC AD = 14 (Soft)
>>> assert result.value == 14  # 11 + 1 + 1 + 1

# Test soft hand going hard
>>> hand = HandBuilder.from_notation("AS 5H 10C")
>>> result = engine.evaluate_hand(hand)
>>> print(result)
AS 5H 10C = 16
>>> assert result.value == 16  # Ace forced to 1
>>> assert not result.is_soft

# Test dealer blackjack
>>> scenario = (Scenario()
...     .player_hand("10S", "10H")
...     .dealer_hand("AD", "KC")  # Dealer blackjack
...     .bet(100)
...     .build())
>>> result = engine.play_scenario(scenario)
>>> assert result.outcomes[0] == Outcome.LOSE
>>> assert result.payouts[0] == -100
```

---

## Testing Strategy

### Test Philosophy

**Primary Approach**: HandBuilder for readable, scenario-based tests
**Secondary Approach**: DeterministicRNG for fairness and statistical tests

**Why HandBuilder First?**
- Readable test code
- Clear intent
- Easy to maintain
- Documents expected behavior
- Works for 90% of tests

**When to Use DeterministicRNG?**
- Fairness proofs (shuffle uniformity)
- Statistical validation (house edge)
- Reproducibility tests
- Performance benchmarking

### Unit Tests Structure

#### 1. Hand Evaluation Tests (~30 tests)

```python
class TestHandEvaluation:
    """Test all hand evaluation logic."""

    def test_blackjack_ace_ten(self):
        """Test natural blackjack detection."""
        hand = HandBuilder().ace().ten().build()
        result = BlackjackEngine.evaluate_hand(hand)

        assert result.value == 21
        assert result.is_blackjack
        assert result.is_soft
        assert not result.is_bust

    def test_soft_17(self):
        """Test soft 17 evaluation."""
        hand = HandBuilder().ace().card("6", "H").build()
        result = BlackjackEngine.evaluate_hand(hand)

        assert result.value == 17
        assert result.is_soft
        assert not result.is_blackjack

    def test_hard_17(self):
        """Test hard 17 evaluation."""
        hand = HandBuilder.from_notation("10S 7H")
        result = BlackjackEngine.evaluate_hand(hand)

        assert result.value == 17
        assert not result.is_soft
        assert not result.is_blackjack

    def test_bust(self):
        """Test bust detection."""
        hand = HandBuilder.from_notation("10S 10H 5C")
        result = BlackjackEngine.evaluate_hand(hand)

        assert result.value == 25
        assert result.is_bust

    def test_multiple_aces(self):
        """Test multiple aces handling."""
        hand = (HandBuilder()
            .ace("S")
            .ace("H")
            .ace("C")
            .card("8", "D")
            .build())
        result = BlackjackEngine.evaluate_hand(hand)

        assert result.value == 21  # 11 + 1 + 1 + 8
        assert result.is_soft
        assert not result.is_blackjack

    # ... 25 more hand evaluation tests
```

#### 2. Dealer Logic Tests (~20 tests)

```python
class TestDealerLogic:
    """Test all dealer decision logic."""

    def test_dealer_hits_16(self):
        """Test dealer must hit on 16."""
        hand = HandBuilder.from_notation("10S 6H")
        rules = Rules()

        assert BlackjackEngine.should_dealer_hit(hand, rules)

    def test_dealer_stands_17(self):
        """Test dealer stands on hard 17."""
        hand = HandBuilder.from_notation("10S 7H")
        rules = Rules(dealer_hit_soft_17=False)

        assert not BlackjackEngine.should_dealer_hit(hand, rules)

    def test_dealer_hits_soft_17_when_required(self):
        """Test dealer hits soft 17 when rules require."""
        hand = HandBuilder.from_notation("AS 6H")
        rules = Rules(dealer_hit_soft_17=True)

        assert BlackjackEngine.should_dealer_hit(hand, rules)

    def test_dealer_stands_soft_17_when_not_required(self):
        """Test dealer stands on soft 17 when rules allow."""
        hand = HandBuilder.from_notation("AS 6H")
        rules = Rules(dealer_hit_soft_17=False)

        assert not BlackjackEngine.should_dealer_hit(hand, rules)

    # ... 16 more dealer logic tests
```

#### 3. Outcome Tests (~15 tests)

```python
class TestOutcomes:
    """Test outcome determination."""

    def test_player_blackjack_beats_dealer_21(self):
        """Test natural blackjack beats dealer 21."""
        player = engine.evaluate_hand(["AS", "KH"])
        dealer = engine.evaluate_hand(["10S", "6H", "5C"])

        outcome = BlackjackEngine.determine_outcome(player, dealer)
        assert outcome == Outcome.BLACKJACK

    def test_player_bust_loses(self):
        """Test bust always loses."""
        player = engine.evaluate_hand(["10S", "10H", "5C"])
        dealer = engine.evaluate_hand(["10S", "10H"])

        outcome = BlackjackEngine.determine_outcome(player, dealer)
        assert outcome == Outcome.LOSE

    def test_push_on_equal_values(self):
        """Test push when values are equal."""
        player = engine.evaluate_hand(["10S", "9H"])
        dealer = engine.evaluate_hand(["10D", "9C"])

        outcome = BlackjackEngine.determine_outcome(player, dealer)
        assert outcome == Outcome.PUSH

    # ... 12 more outcome tests
```

#### 4. Payout Tests (~10 tests)

```python
class TestPayouts:
    """Test payout calculations."""

    def test_blackjack_pays_3_to_2(self):
        """Test blackjack pays 3:2 (1.5x)."""
        rules = Rules(blackjack_payout=1.5)
        payout = BlackjackEngine.calculate_payout(
            Outcome.BLACKJACK,
            bet_amount=100,
            rules=rules
        )
        assert payout == 150

    def test_regular_win_pays_1_to_1(self):
        """Test regular win pays 1:1."""
        payout = BlackjackEngine.calculate_payout(
            Outcome.WIN,
            bet_amount=100,
            rules=Rules()
        )
        assert payout == 100

    def test_push_returns_bet(self):
        """Test push returns original bet."""
        payout = BlackjackEngine.calculate_payout(
            Outcome.PUSH,
            bet_amount=100,
            rules=Rules()
        )
        assert payout == 0

    # ... 7 more payout tests
```

#### 5. Shuffle Fairness Tests (~15 tests)

```python
class TestShuffleFairness:
    """Test shuffle fairness using DeterministicRNG."""

    def test_fisher_yates_uniform_distribution(self):
        """Test Fisher-Yates produces uniform permutations."""
        rng = DeterministicRNG(seed=42)
        shuffler = FisherYatesShuffle(rng)

        # Shuffle small deck many times
        deck = ["AS", "2H"]
        permutations = []

        for _ in range(10000):
            shuffled = shuffler.shuffle(deck.copy())
            permutations.append(tuple(shuffled))

        # Both permutations should appear roughly equally
        from collections import Counter
        counts = Counter(permutations)
        assert len(counts) == 2

        # Chi-squared test for uniformity
        expected = 5000
        tolerance = 300  # 6% tolerance
        for count in counts.values():
            assert abs(count - expected) < tolerance

    # ... 14 more fairness tests
```

#### 6. Complete Round Tests (~20 tests)

```python
class TestCompleteRound:
    """Test complete round scenarios."""

    def test_deterministic_round_with_fixed_rng(self):
        """Test complete round with deterministic RNG."""
        rng = DeterministicRNG(seed=42)
        engine = BlackjackEngine(rng=rng)

        result1 = engine.play_round(bet_amounts=[100])

        # Reset with same seed
        rng = DeterministicRNG(seed=42)
        engine = BlackjackEngine(rng=rng)

        result2 = engine.play_round(bet_amounts=[100])

        # Results should be identical
        assert result1 == result2

    def test_scenario_based_round(self):
        """Test round with HandBuilder scenario."""
        scenario = (Scenario()
            .player_hand("AS", "KH")
            .dealer_hand("10D", "9C")
            .bet(100)
            .build())

        result = engine.play_scenario(scenario)

        assert result.outcomes[0] == Outcome.BLACKJACK
        assert result.payouts[0] == 150

    # ... 18 more round tests
```

### Test Coverage Goals

**Minimum Viable (Phase 1)**:
- ~50 tests covering core hand evaluation and dealer logic
- All pure functions tested

**Complete (Phase 3)**:
- 100+ tests covering all scenarios
- Splits, doubles, insurance, surrender
- Edge cases and fairness proofs

---

## Migration Plan

### Big Bang Strategy

**Approach**: Complete implementation, comprehensive testing, then single cutover

**Rationale**:
- Blackjack is complex - incremental migration risks inconsistency
- Full test suite proves correctness before cutover
- Clean break avoids maintaining two implementations
- Allows complete architectural rethink

### Phase 1: Core Engine (Weeks 1-2)

**Goals**:
- Implement `BlackjackEngine` class
- Implement all pure functions (evaluate, dealer logic, outcomes, payouts)
- Implement `HandBuilder` and `Scenario` classes
- Write 50+ unit tests
- All core logic tests passing

**Deliverables**:
- `cardsharp/engine/blackjack_engine.py` (new, ~800 lines)
- `cardsharp/engine/hand_builder.py` (new, ~200 lines)
- `cardsharp/engine/scenario.py` (new, ~150 lines)
- `tests/engine/test_blackjack_engine.py` (new, 50+ tests)
- All tests green

**Success Criteria**:
- ✅ All hand evaluation edge cases tested
- ✅ All dealer logic scenarios tested
- ✅ All outcome permutations tested
- ✅ All payout calculations verified
- ✅ No dependencies on existing state machine

### Phase 2: Secure RNG & Shuffle (Week 3)

**Goals**:
- Create `SecureRNG` class (cryptographically secure)
- Create `FisherYatesShuffle` class (provably fair)
- Create `SecureShoe` class (injectable RNG)
- Prove shuffle fairness via statistical tests
- Implement `DeterministicRNG` for testing

**Deliverables**:
- `cardsharp/common/secure_rng.py` (new, ~100 lines)
- `cardsharp/common/secure_shuffle.py` (new, ~150 lines)
- `cardsharp/common/secure_shoe.py` (new, ~200 lines)
- `tests/common/test_shuffle_fairness.py` (new, 15+ tests)
- Fairness proof document

**Success Criteria**:
- ✅ Shuffle uniformity proven statistically
- ✅ RNG independence verified
- ✅ Deterministic testing works
- ✅ Performance acceptable

### Phase 3: Complete Round Logic (Week 4)

**Goals**:
- Implement full round orchestration (functional composition)
- Support single player (multi-player in later phase)
- Support all actions: hit, stand, double, split, surrender, insurance
- Comprehensive round tests
- Performance benchmarking

**Deliverables**:
- Complete `BlackjackEngine.play_round()` implementation
- Complete `BlackjackEngine.play_scenario()` implementation
- 30+ round simulation tests
- Performance benchmarks
- All 100+ tests passing

**Success Criteria**:
- ✅ All game features implemented (splits, doubles, etc.)
- ✅ All edge cases tested
- ✅ Performance meets or exceeds current (22k+ games/sec)
- ✅ No regressions

### Phase 4: Integration & Cutover (Week 5)

**Goals**:
- Replace existing blackjack implementation
- Update all platform adapters to use new engine
- Migrate all existing tests
- Backward compatibility where needed

**Deliverables**:
- Updated `cardsharp/blackjack/blackjack.py` (uses new engine)
- All existing functionality preserved
- All existing tests passing
- Migration complete

**Success Criteria**:
- ✅ Zero breaking changes for users
- ✅ All existing tests pass
- ✅ All new tests pass
- ✅ Performance maintained or improved

### Phase 5: Multi-Player & Documentation (Week 6)

**Goals**:
- Add multi-player support to `play_round()`
- Comprehensive API documentation
- Performance benchmarks
- Fairness validation reports
- Migration guide for contributors

**Deliverables**:
- Multi-player support implemented
- `BLACKJACK_ENGINE.md` (this document) ✅
- `FAIRNESS_PROOF.md` (mathematical proofs)
- Performance comparison report
- API documentation
- Example notebooks

**Success Criteria**:
- ✅ Multi-player fully tested
- ✅ Documentation complete
- ✅ Fairness proven
- ✅ Ready for production

---

## Success Criteria

### Correctness ✅

- [ ] 100+ unit tests covering all game rules
- [ ] All hand evaluation edge cases tested
- [ ] All dealer logic scenarios tested
- [ ] All outcome permutations tested
- [ ] All payout calculations verified
- [ ] All action types (hit/stand/double/split/surrender/insurance) tested
- [ ] Edge cases: multiple aces, soft hands going hard, blackjack vs 21

### Fairness ✅

- [ ] Shuffle fairness proven via statistical tests
- [ ] House edge verified mathematically
- [ ] Blackjack probability verified (~4.83%)
- [ ] No way to game the system (proven)
- [ ] Cryptographically secure RNG (using `secrets` module)
- [ ] Fisher-Yates shuffle implementation
- [ ] Independence tests for consecutive shuffles

### Testability ✅

- [ ] All core logic is pure functions
- [ ] Deterministic tests possible via DeterministicRNG
- [ ] No mocking required for unit tests
- [ ] HandBuilder makes scenarios readable
- [ ] 100% test coverage of engine
- [ ] Fast test execution (<5 seconds for full suite)

### Maintainability ✅

- [ ] Clear separation of concerns (engine vs platform)
- [ ] Single source of truth for rules (Rules dataclass)
- [ ] Type-safe implementation (enums, dataclasses)
- [ ] Comprehensive documentation
- [ ] Easy to extend (new rules, new variants)
- [ ] No state machine complexity

### Performance ✅

- [ ] Performance acceptable (willing to accept some hit for purity)
- [ ] Maintain 20k+ games/second for simulations
- [ ] Pure functions enable future optimizations
- [ ] Benchmarks in place for regression detection
- [ ] Profiling done to identify bottlenecks

### Developer Experience ✅

- [ ] REPL-friendly (easy to import and use interactively)
- [ ] Human-readable API (clear method names)
- [ ] One consistent style (no shorthand confusion)
- [ ] Poker notation primary (AS KH format)
- [ ] HandBuilder/Scenario first-class features
- [ ] Self-documenting types and methods
- [ ] Excellent autocomplete support

---

## Implementation Notes

### Key Architectural Decisions

#### 1. Pure Functions vs. State Machine

**Decision**: Replace state machine entirely with pure functional composition

**Rationale**:
- State machine adds complexity without benefits
- Pure functions are easier to test and reason about
- Functional composition is more maintainable
- No performance penalty for purity
- Aligns with overall design philosophy

#### 2. Injectable Dependencies

**Decision**: Inject RNG and shuffle algorithm via Protocol

**Rationale**:
- Enables deterministic testing
- Proves fairness via tests
- Maintains flexibility (can swap implementations)
- No runtime performance penalty
- Standard pattern from RouletteEngine

#### 3. Immutable Results

**Decision**: All results are frozen dataclasses

**Rationale**:
- Prevents accidental tampering
- Thread-safe by default
- Easier to reason about
- Matches roulette pattern
- Functional programming best practice

#### 4. Separation of Concerns

**Decision**: Engine has zero I/O, zero platform code

**Rationale**:
- Pure logic is testable
- Can be used in any platform (Discord, web, CLI, etc.)
- Easy to verify correctness
- Reduces complexity
- Clear boundaries

#### 5. One API Style

**Decision**: Single consistent API, no shorthand methods

**Rationale**:
- Reduces API surface area
- Less cognitive load
- Better autocomplete
- Clearer documentation
- Easier to maintain

#### 6. Poker Notation Primary

**Decision**: Poker notation ("AS KH") is the primary card format

**Rationale**:
- Standard in programming
- Easy to type
- ASCII-safe
- Clear and unambiguous
- Works everywhere (terminals, logs, etc.)

#### 7. HandBuilder/Scenario First-Class

**Decision**: Promote to main API, not just test helpers

**Rationale**:
- Useful in production (Discord bots, web apps)
- Makes API more powerful
- Encourages scenario-based thinking
- Better developer experience
- Not just for testing

---

## Conclusion

This BlackjackEngine design achieves:

✅ **Testable**: Pure functions, injectable dependencies, HandBuilder for scenarios
✅ **Correct**: 100+ tests prove all rules work correctly
✅ **Fair**: Cryptographically secure RNG, provable fairness
✅ **Maintainable**: Clear architecture, type-safe, well-documented
✅ **Developer-Friendly**: REPL-friendly, human-readable, first-class scenario API

The increased complexity of blackjack (compared to roulette) is managed through:
- Pure functional composition (no state machine)
- Comprehensive test coverage (100+ tests)
- HandBuilder for readable test scenarios
- Big bang migration strategy
- Clear documentation

**Next Steps**:
1. ✅ Review and approve this unified plan
2. Create bd issues for each phase
3. Start Phase 1: Core Engine implementation
4. Iterate based on testing and feedback

**Success Metric**: Same level of confidence in correctness and fairness as RouletteEngine, with a superior developer experience and maintainable pure functional architecture.
