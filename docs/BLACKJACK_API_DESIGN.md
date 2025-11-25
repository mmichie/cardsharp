# BlackjackEngine API Design & Usability

## Design Principles

The BlackjackEngine API is designed to be:

1. **REPL-Friendly** - Perfect for IPython, Jupyter notebooks, interactive exploration
2. **Human-Readable** - Clear, intuitive method names and parameters
3. **Easy to Import** - Minimal dependencies, clean namespace
4. **Test-Friendly** - Easy to construct specific scenarios for verification
5. **Self-Documenting** - Code reads like plain English

---

## Interactive Usage (IPython/Jupyter)

### Quick Start - 30 seconds to first hand

```python
# Start IPython
>>> from cardsharp.engine import BlackjackEngine, Hand, Card
>>> from cardsharp.engine.test_helpers import HandBuilder, Scenario

# Create engine with standard rules
>>> engine = BlackjackEngine.standard()

# Or customize rules
>>> engine = BlackjackEngine(
...     blackjack_payout=1.5,
...     dealer_hits_soft_17=True,
...     num_decks=6
... )

# Play a quick hand
>>> result = engine.play_hand(bet=100)
>>> print(result)
Player: K♠ 7♥ (17)
Dealer: 10♦ 6♣ (16)
Outcome: WIN (+$100)

# Check your hand
>>> result.player_hand
HandResult(value=17, is_soft=False, is_blackjack=False, is_bust=False)

# See exactly what happened
>>> result.summary()
"""
Player dealt: K♠ 7♥
Player stands with 17
Dealer shows: 10♦
Dealer hole card: 6♣
Dealer hits: busts with 26
Player wins!
Payout: $100
"""
```

### Interactive Hand Evaluation

```python
# Evaluate any hand instantly
>>> engine.eval("A♠ K♥")
HandResult(value=21, is_soft=True, is_blackjack=True, is_bust=False)

>>> engine.eval("10♠ 6♥ 5♣")
HandResult(value=21, is_soft=False, is_blackjack=False, is_bust=False)

>>> engine.eval("A♠ A♥ 9♣")
HandResult(value=21, is_soft=True, is_blackjack=False, is_bust=False)

# What should dealer do?
>>> engine.should_dealer_hit("A♠ 6♥")  # Soft 17
True  # (if dealer_hits_soft_17 is True)

>>> engine.should_dealer_hit("10♠ 7♥")  # Hard 17
False

# Who wins?
>>> engine.compare("20", "19")  # Player has 20, dealer has 19
Outcome.WIN

>>> engine.compare("A♠K♥", "10♣9♦2♠")  # Blackjack vs 21
Outcome.BLACKJACK

>>> engine.compare("18", "18")
Outcome.PUSH
```

---

## Test Hand Builder System

### HandBuilder - Construct Specific Scenarios

```python
from cardsharp.engine.test_helpers import HandBuilder, Scenario

# Create specific hands easily
>>> hand = HandBuilder().ace().ten().build()
>>> engine.evaluate_hand(hand)
HandResult(value=21, is_soft=True, is_blackjack=True, is_bust=False)

# Fluent API for readability
>>> hand = (HandBuilder()
...     .card("A", "♠")
...     .card("6", "♥")
...     .card("4", "♣")
...     .build())
>>> engine.evaluate_hand(hand)
HandResult(value=21, is_soft=True, is_blackjack=False, is_bust=False)

# Or use shorthand
>>> hand = HandBuilder.from_string("A♠ 6♥ 4♣")
>>> hand = HandBuilder.parse("AS 6H 4C")  # Poker notation
>>> hand = HandBuilder.from_values([11, 6, 4])  # Just values
```

### Scenario Builder - Test Complete Situations

```python
# Build complete game scenarios for testing
>>> scenario = (Scenario()
...     .player_hand("A♠", "K♥")
...     .dealer_hand("10♦", "9♣")
...     .bet(100)
...     .build())

>>> result = engine.play_scenario(scenario)
>>> print(result)
Player: A♠ K♥ (Blackjack!)
Dealer: 10♦ 9♣ (19)
Outcome: BLACKJACK
Payout: $150 (3:2)

# Test specific dealer situations
>>> scenario = (Scenario()
...     .player_hand("10♠", "10♥")
...     .dealer_showing("A♦")
...     .dealer_hole("K♣")  # Dealer has blackjack
...     .bet(100)
...     .build())

>>> result = engine.play_scenario(scenario)
Player: 10♠ 10♥ (20)
Dealer: A♦ K♣ (Blackjack!)
Outcome: LOSE
Payout: -$100

# Test multi-hand scenarios (splits)
>>> scenario = (Scenario()
...     .player_hand("8♠", "8♥")  # Pair of 8s
...     .action("split")
...     .first_hand_gets("3♣")
...     .second_hand_gets("10♦")
...     .dealer_hand("10♠", "6♣")
...     .bet(100)
...     .build())

>>> result = engine.play_scenario(scenario)
Hand 1: 8♠ 3♣ (11)
Hand 2: 8♥ 10♦ (18)
Dealer: 10♠ 6♣ (busts with 26)
Outcome: [WIN, WIN]
Payout: +$200
```

### Verification Helpers - Test Engine Correctness

```python
from cardsharp.engine.test_helpers import verify

# Verify specific outcomes
>>> verify.blackjack("A♠ K♥")
✓ A♠ K♥ correctly identified as blackjack

>>> verify.not_blackjack("A♠ K♥ 0♣")  # 21 but not blackjack
✓ A♠ K♥ 0♣ correctly identified as NOT blackjack (21)

>>> verify.soft("A♠ 6♥")
✓ A♠ 6♥ correctly identified as soft 17

>>> verify.hard("10♠ 7♥")
✓ 10♠ 7♥ correctly identified as hard 17

>>> verify.value("A♠ A♥ A♣ 8♦", expected=21)
✓ A♠ A♥ A♣ 8♦ = 21 (correct)

# Verify dealer behavior
>>> verify.dealer_hits("A♠ 6♥", rules=Rules(dealer_hits_soft_17=True))
✓ Dealer correctly hits on soft 17

>>> verify.dealer_stands("10♠ 7♥")
✓ Dealer correctly stands on hard 17

# Verify outcomes
>>> verify.outcome(
...     player="20",
...     dealer="19",
...     expected=Outcome.WIN
... )
✓ Player 20 vs Dealer 19 = WIN (correct)

# Verify payouts
>>> verify.payout(
...     outcome=Outcome.BLACKJACK,
...     bet=100,
...     expected=150,
...     rules=Rules(blackjack_payout=1.5)
... )
✓ Blackjack with $100 bet pays $150 (3:2) (correct)
```

---

## Human-Readable API

### Clear Method Names

```python
# NOT this (cryptic)
>>> engine.eval_h([Card(0, 0), Card(1, 0)])
>>> engine.cmp(h1, h2)
>>> engine.should_hit(h, r)

# YES this (readable)
>>> engine.evaluate_hand([Card.ace_of_spades(), Card.ten_of_hearts()])
>>> engine.compare_hands(player_hand, dealer_hand)
>>> engine.should_dealer_hit(dealer_hand, rules)
```

### Self-Documenting Types

```python
# Rich enums instead of magic strings/numbers
class Outcome(Enum):
    WIN = "win"
    LOSE = "lose"
    PUSH = "push"
    BLACKJACK = "blackjack"
    SURRENDER = "surrender"

class Action(Enum):
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    SURRENDER = "surrender"
    INSURANCE = "insurance"

# Usage is clear
>>> if result.outcome == Outcome.BLACKJACK:
...     print("Natural 21!")
```

### Descriptive Results

```python
@dataclass(frozen=True)
class HandResult:
    """Result of evaluating a hand.

    Attributes:
        value: The numeric value of the hand (0-21, or >21 if bust)
        is_soft: True if hand contains an ace counted as 11
        is_blackjack: True if natural blackjack (ace + 10-value in 2 cards)
        is_bust: True if value > 21
        cards: The cards in the hand (for display)
    """
    value: int
    is_soft: bool
    is_blackjack: bool
    is_bust: bool
    cards: tuple[Card, ...]

    def __str__(self) -> str:
        """Human-readable string representation."""
        cards_str = " ".join(str(c) for c in self.cards)
        status = []
        if self.is_blackjack:
            status.append("Blackjack!")
        elif self.is_bust:
            status.append("Bust")
        elif self.is_soft:
            status.append("Soft")

        status_str = f" ({', '.join(status)})" if status else ""
        return f"{cards_str} = {self.value}{status_str}"

# Usage
>>> result = engine.evaluate_hand(hand)
>>> print(result)
A♠ K♥ = 21 (Blackjack!)
```

---

## Easy Integration in Other Apps

### Minimal Dependencies

```python
# cardsharp/engine/blackjack_engine.py
"""Pure blackjack engine with zero external dependencies.

This module can be imported anywhere with just Python 3.10+.
No external packages required.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
# No other imports!

class BlackjackEngine:
    """Self-contained blackjack engine."""
    # All logic here, no external dependencies
```

### Clean Imports

```python
# Everything you need in one import
from cardsharp.engine import (
    BlackjackEngine,
    HandResult,
    RoundResult,
    Outcome,
    Action,
    Rules,
    Card,
    Hand,
)

# Or import just what you need
from cardsharp.engine import BlackjackEngine
from cardsharp.engine.test_helpers import HandBuilder, Scenario
```

### Framework Integration Examples

#### Discord Bot Integration

```python
import discord
from discord.ext import commands
from cardsharp.engine import BlackjackEngine, HandBuilder

class BlackjackCog(commands.Cog):
    def __init__(self):
        self.engine = BlackjackEngine.standard()

    @commands.command()
    async def hit(self, ctx):
        """Hit in current hand."""
        # Get player's current hand from state
        player_hand = self.get_player_hand(ctx.author.id)

        # Deal a card
        card = self.shoe.deal()
        player_hand.append(card)

        # Evaluate using engine
        result = self.engine.evaluate_hand(player_hand)

        if result.is_bust:
            await ctx.send(f"💥 Bust! {result}")
        else:
            await ctx.send(f"🎴 {result}")
```

#### Flask Web App Integration

```python
from flask import Flask, jsonify, request
from cardsharp.engine import BlackjackEngine, Scenario

app = Flask(__name__)
engine = BlackjackEngine.standard()

@app.route('/api/evaluate', methods=['POST'])
def evaluate_hand():
    """Evaluate a hand from JSON."""
    cards_str = request.json['cards']  # e.g., "A♠ K♥"
    result = engine.eval(cards_str)

    return jsonify({
        'value': result.value,
        'is_soft': result.is_soft,
        'is_blackjack': result.is_blackjack,
        'is_bust': result.is_bust
    })

@app.route('/api/play', methods=['POST'])
def play_hand():
    """Play a complete hand."""
    bet = request.json['bet']
    result = engine.play_hand(bet=bet)

    return jsonify({
        'player': str(result.player_hand),
        'dealer': str(result.dealer_hand),
        'outcome': result.outcome.value,
        'payout': result.payout
    })
```

#### Jupyter Notebook Analysis

```python
# Analyze blackjack strategies in Jupyter
import pandas as pd
import matplotlib.pyplot as plt
from cardsharp.engine import BlackjackEngine, Scenario
from cardsharp.engine.simulation import simulate_many

# Run 100,000 hands
engine = BlackjackEngine.standard()
results = simulate_many(engine, num_hands=100000, bet=100)

# Analyze results
df = pd.DataFrame([
    {
        'hand': i,
        'outcome': r.outcome.value,
        'payout': r.payout,
        'cumulative': sum(rr.payout for rr in results[:i+1])
    }
    for i, r in enumerate(results)
])

# Plot
plt.figure(figsize=(12, 6))
plt.plot(df['hand'], df['cumulative'])
plt.title('Blackjack Performance over 100k Hands')
plt.xlabel('Hand Number')
plt.ylabel('Cumulative Profit/Loss ($)')
plt.grid(True)
plt.show()

# Statistics
print(f"Win Rate: {(df['outcome'] == 'win').sum() / len(df) * 100:.2f}%")
print(f"Final P/L: ${df['cumulative'].iloc[-1]:,.2f}")
print(f"House Edge: {-df['payout'].mean() / 100 * 100:.2f}%")
```

---

## Complete API Reference

### Core Engine Methods

```python
class BlackjackEngine:
    """Pure blackjack game engine."""

    # Construction
    @classmethod
    def standard(cls) -> BlackjackEngine:
        """Create engine with standard Vegas rules."""

    def __init__(self, rules: Rules | None = None, **kwargs):
        """Create engine with custom rules."""

    # Hand Evaluation (Pure Functions)
    def evaluate_hand(self, cards: list[Card] | str) -> HandResult:
        """Evaluate a hand's value, soft/hard, blackjack, bust.

        Args:
            cards: List of Card objects or string like "A♠ K♥"

        Returns:
            HandResult with all hand properties

        Examples:
            >>> engine.evaluate_hand([Card.ace(), Card.ten()])
            >>> engine.evaluate_hand("A♠ K♥")
            >>> engine.eval("10♠ 6♥ 5♣")  # Shorthand
        """

    def eval(self, cards_str: str) -> HandResult:
        """Shorthand for evaluate_hand with string input."""

    def should_dealer_hit(self, cards: list[Card] | str) -> bool:
        """Check if dealer should hit based on rules.

        Examples:
            >>> engine.should_dealer_hit("A♠ 6♥")  # Soft 17
            >>> engine.should_dealer_hit([ace, six])
        """

    def compare_hands(
        self,
        player: HandResult | list[Card] | str,
        dealer: HandResult | list[Card] | str
    ) -> Outcome:
        """Compare player vs dealer and determine outcome.

        Examples:
            >>> engine.compare_hands("20", "19")
            >>> engine.compare("A♠K♥", "10♣9♦2♠")  # Shorthand
        """

    def compare(self, player: str, dealer: str) -> Outcome:
        """Shorthand for compare_hands."""

    def calculate_payout(
        self,
        outcome: Outcome,
        bet: float
    ) -> float:
        """Calculate payout for outcome.

        Examples:
            >>> engine.calculate_payout(Outcome.BLACKJACK, 100)
            150.0  # 3:2 payout
            >>> engine.calculate_payout(Outcome.WIN, 100)
            100.0  # 1:1 payout
        """

    # Game Play
    def play_hand(
        self,
        bet: float = 100,
        player_cards: list[Card] | str | None = None,
        dealer_cards: list[Card] | str | None = None
    ) -> RoundResult:
        """Play a complete hand.

        Args:
            bet: Bet amount
            player_cards: Optional specific cards for player (for testing)
            dealer_cards: Optional specific cards for dealer (for testing)

        Returns:
            RoundResult with complete outcome

        Examples:
            >>> engine.play_hand(bet=100)  # Random hand
            >>> engine.play_hand(bet=100, player_cards="A♠ K♥")  # Fixed player
        """

    def play_scenario(self, scenario: Scenario) -> RoundResult:
        """Play a pre-defined scenario.

        Examples:
            >>> scenario = Scenario().player("A♠K♥").dealer("10♦9♣").build()
            >>> engine.play_scenario(scenario)
        """

    # Batch Operations
    def simulate(
        self,
        num_hands: int,
        bet: float = 100,
        verbose: bool = False
    ) -> SimulationResult:
        """Simulate many hands and return statistics.

        Examples:
            >>> results = engine.simulate(10000, bet=100)
            >>> print(f"Win rate: {results.win_rate:.2%}")
            >>> print(f"House edge: {results.house_edge:.2%}")
        """
```

### Test Helpers

```python
class HandBuilder:
    """Fluent builder for constructing test hands."""

    # Construction
    def __init__(self):
        """Start building a hand."""

    def card(self, rank: str, suit: str) -> HandBuilder:
        """Add a specific card."""

    def ace(self, suit: str = "♠") -> HandBuilder:
        """Add an ace."""

    def ten(self, suit: str = "♠") -> HandBuilder:
        """Add a 10-value card."""

    def face(self, face: str = "K", suit: str = "♠") -> HandBuilder:
        """Add a face card (J, Q, K)."""

    def value(self, value: int) -> HandBuilder:
        """Add a card with specific value."""

    # Shortcuts
    @classmethod
    def from_string(cls, cards: str) -> list[Card]:
        """Parse "A♠ K♥" format."""

    @classmethod
    def parse(cls, cards: str) -> list[Card]:
        """Parse "AS KH" poker notation."""

    @classmethod
    def from_values(cls, values: list[int]) -> list[Card]:
        """Create hand from just values [11, 10] -> [A, K]."""

    def build(self) -> list[Card]:
        """Build the final hand."""

class Scenario:
    """Builder for complete game scenarios."""

    def player_hand(self, *cards: str) -> Scenario:
        """Set player's cards."""

    def dealer_hand(self, *cards: str) -> Scenario:
        """Set dealer's cards."""

    def dealer_showing(self, card: str) -> Scenario:
        """Set dealer's up card."""

    def dealer_hole(self, card: str) -> Scenario:
        """Set dealer's hole card."""

    def bet(self, amount: float) -> Scenario:
        """Set bet amount."""

    def action(self, action: str) -> Scenario:
        """Add player action (hit, stand, double, split)."""

    def build(self) -> ScenarioData:
        """Build the scenario."""

class VerificationHelper:
    """Helpers for verifying engine correctness."""

    def blackjack(self, cards: str) -> None:
        """Assert cards are blackjack."""

    def not_blackjack(self, cards: str) -> None:
        """Assert cards are NOT blackjack."""

    def soft(self, cards: str) -> None:
        """Assert hand is soft."""

    def hard(self, cards: str) -> None:
        """Assert hand is hard."""

    def value(self, cards: str, expected: int) -> None:
        """Assert hand has specific value."""

    def dealer_hits(self, cards: str, rules: Rules) -> None:
        """Assert dealer should hit."""

    def dealer_stands(self, cards: str, rules: Rules) -> None:
        """Assert dealer should stand."""

    def outcome(
        self,
        player: str,
        dealer: str,
        expected: Outcome
    ) -> None:
        """Assert outcome is correct."""

    def payout(
        self,
        outcome: Outcome,
        bet: float,
        expected: float,
        rules: Rules
    ) -> None:
        """Assert payout is correct."""

# Global instance for convenience
verify = VerificationHelper()
```

---

## Usage Examples

### Example 1: Interactive Testing in IPython

```python
In [1]: from cardsharp.engine import BlackjackEngine
In [2]: from cardsharp.engine.test_helpers import HandBuilder, verify

In [3]: engine = BlackjackEngine.standard()

# Test specific scenarios interactively
In [4]: engine.eval("A♠ K♥")
Out[4]: HandResult(value=21, is_soft=True, is_blackjack=True, is_bust=False)

In [5]: engine.eval("A♠ A♥ 9♣")
Out[5]: HandResult(value=21, is_soft=True, is_blackjack=False, is_bust=False)

In [6]: engine.compare("A♠K♥", "10♣J♦")
Out[6]: <Outcome.BLACKJACK: 'blackjack'>

# Verify correctness
In [7]: verify.blackjack("A♠ K♥")
✓ A♠ K♥ correctly identified as blackjack

In [8]: verify.not_blackjack("A♠ 5♥ 5♣")
✓ A♠ 5♥ 5♣ correctly identified as NOT blackjack (21)

In [9]: verify.soft("A♠ 6♥")
✓ A♠ 6♥ correctly identified as soft 17
```

### Example 2: Building and Testing Edge Cases

```python
from cardsharp.engine import BlackjackEngine
from cardsharp.engine.test_helpers import HandBuilder, Scenario, verify

engine = BlackjackEngine.standard()

# Test the famous "four aces" edge case
hand = (HandBuilder()
    .ace("♠")
    .ace("♥")
    .ace("♣")
    .ace("♦")
    .build())

result = engine.evaluate_hand(hand)
assert result.value == 14  # A + A + A + A = 11 + 1 + 1 + 1
assert result.is_soft

# Test soft hand going hard
hand = (HandBuilder()
    .ace("♠")
    .five("♥")
    .ten("♣")
    .build())

result = engine.evaluate_hand(hand)
assert result.value == 16  # A + 5 + 10 = 1 + 5 + 10 (ace forced to 1)
assert not result.is_soft

# Test dealer behavior on soft 17
verify.dealer_hits("A♠ 6♥", rules=engine.rules)
verify.dealer_stands("10♠ 7♥", rules=engine.rules)

# Test complete scenario
scenario = (Scenario()
    .player_hand("10♠", "10♥")
    .dealer_hand("A♦", "K♣")  # Dealer blackjack
    .bet(100)
    .build())

result = engine.play_scenario(scenario)
assert result.outcome == Outcome.LOSE
assert result.payout == -100
```

### Example 3: Batch Verification

```python
from cardsharp.engine import BlackjackEngine
from cardsharp.engine.test_helpers import verify

engine = BlackjackEngine.standard()

# Test all blackjack combinations
blackjacks = [
    "A♠ 10♥", "A♥ J♣", "A♣ Q♦", "A♦ K♠",
    "10♠ A♥", "J♥ A♣", "Q♣ A♦", "K♦ A♠"
]

for hand in blackjacks:
    verify.blackjack(hand)

print("✓ All 8 blackjack combinations verified")

# Test all soft 17 variations
soft_17s = [
    "A♠ 6♥", "A♥ 2♣ 4♦", "A♣ 3♠ 3♥", "A♦ A♠ 5♣"
]

for hand in soft_17s:
    verify.soft(hand)
    verify.value(hand, 17)

print("✓ All soft 17 variations verified")
```

---

## Benefits of This API Design

### 1. **Instant Feedback** (REPL-Friendly)
- Import and use in seconds
- Test individual hands interactively
- Verify correctness immediately
- Perfect for Jupyter notebooks

### 2. **Self-Documenting** (Human-Readable)
- Method names explain what they do
- Rich types (enums) instead of magic values
- Clear parameter names
- Excellent autocomplete support

### 3. **Easy Testing** (Test-Friendly)
- HandBuilder for specific scenarios
- Scenario builder for complete games
- Verification helpers for assertions
- No mocking required

### 4. **Portable** (Easy Integration)
- Zero external dependencies
- Clean imports
- Works anywhere Python runs
- Framework-agnostic

### 5. **Production-Ready** (Well-Designed)
- Type-safe with enums and dataclasses
- Immutable results
- Pure functions
- Thoroughly tested

---

## Implementation Checklist

- [ ] Core engine with human-readable methods
- [ ] HandBuilder with fluent API
- [ ] Scenario builder for complete games
- [ ] Verification helpers for testing
- [ ] String parsing ("A♠ K♥" format)
- [ ] Shorthand methods (eval, compare)
- [ ] Rich __str__ methods for results
- [ ] Interactive examples in docs
- [ ] Jupyter notebook examples
- [ ] Integration examples (Discord, Flask)

This API design makes the BlackjackEngine as easy to use as:
```python
>>> engine.eval("A♠ K♥")
HandResult(value=21, is_soft=True, is_blackjack=True, is_bust=False)
```

Simple, readable, testable, and powerful! 🎰✨
