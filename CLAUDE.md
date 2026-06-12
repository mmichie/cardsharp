# CLAUDE.md

**Note**: This project uses [bd (beads)](https://github.com/steveyegge/beads) for issue tracking. Use `bd` commands instead of markdown TODOs. See AGENTS.md for workflow details.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development Setup
```bash
# Install dependencies with uv
uv sync

# Install with dev dependencies
uv sync --all-extras
```

### Running Tests
```bash
# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=cardsharp

# Run specific test modules
uv run pytest tests/api/test_event_cleanup.py -v

# Run tests in parallel
uv run pytest -n auto
```

### Linting and Code Quality
```bash
# Run ruff linter
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .

# Format code with black
uv run black .

# Run pylint
uv run pylint cardsharp
```

### Running Simulations
```bash
# Run blackjack simulation
uv run python cardsharp/blackjack/blackjack.py --simulate --num_games 10000

# Run with visualization
uv run python cardsharp/blackjack/blackjack.py --simulate --num_games 10000 --vis

# Run strategy analysis
uv run python cardsharp/blackjack/blackjack.py --analysis --num_games 5000

# Interactive console mode
uv run python cardsharp/blackjack/blackjack.py --console

# Performance profiling
uv run python cardsharp/blackjack/blackjack.py --simulate --profile --num_games 1000
```

## Architecture Overview

### Event-Driven Architecture
CardSharp uses a phased modernization architecture with these key components:

1. **Event System** - Core components communicate through events
   - `EventEmitter` in `cardsharp/events/emitter.py` - Handles event pub/sub
   - All state changes emit events for decoupling and verification
   - Supports both sync and async event handlers

2. **Adapters** - Platform-specific code isolated in adapters
   - `PlatformAdapter` interface in `cardsharp/adapters/base.py`
   - Implementations: CLI, Web, Dummy (for testing)
   - Handles rendering and user input for different platforms

3. **Immutable State** - Game state transitions via pure functions
   - State models in `cardsharp/state/models.py`
   - Transition functions in `cardsharp/state/transitions.py`
   - State is never mutated, only new states created

4. **Game Engines** - Core game logic
   - Base engine in `cardsharp/engine/base.py`
   - Game-specific engines (Blackjack, War, High Card, Durak)
   - Engines emit events and manage state transitions

5. **APIs** - High-level interfaces
   - Async APIs in `cardsharp/api/` for each game
   - Support both sync and async operation modes
   - Event-driven flow control

### Key Design Patterns

- **State Pattern**: Game flow managed through state transitions
- **Strategy Pattern**: Different playing strategies (Basic, Counting, Aggressive, Martingale)
- **Observer Pattern**: Event system for decoupled communication
- **Adapter Pattern**: Platform-specific rendering and input handling

### Performance Considerations

When optimizing blackjack simulations:
- Simulation runs on one of two engines, selected by `--engine {auto,fast,python}`:
  - The Rust fast core (`crates/cardsharp-core`, facade in `cardsharp/fastsim/`) plays
    table-encodable strategies (basic, solver tables), Hi-Lo counting (bet ramp,
    Illustrious 18 deviations, TC-based insurance), CSM shoes, and realistic shuffles
    (GSR riffle, strip) on classic rules at ~2.9M games/second on one thread and
    ~15-30M games/second across all cores depending on shoe mode (Rayon-sharded;
    results are bit-identical for a given seed regardless of thread count). It also
    provides an interactive resumable session API (`cardsharp.fastsim.open_session`:
    begin_round/apply steps over a persistent shoe) that runs the same round
    implementation as the batch paths; interactive play -- the `--console` mode
    (`cardsharp/blackjack/console.py`) and the event-driven engine behind the
    CLI/web adapters (`cardsharp/engine/blackjack.py`) -- drives sessions, with
    the old state-machine console kept only as the no-core fallback until the
    engine retires (beads-i2s.6). It is an optional accelerator built with
    `uv sync --extra fast`.
  - The fast core also runs the deal-EV control variate (`--cv`, single seat:
    the per-deal accumulator yields the exact CV moments) and CRN rule
    comparisons (`--compare_rules`).
  - The pure-Python reference engine (~50,000 games/second single-threaded, ~350,000
    via multiprocessing) handles what remains: bet-progression and custom
    strategies, composition-dependent play (`--cd_strategy`), non-classic
    variants, multi-seat control variates, and per-round visualization (`--vis`).
- `auto` (the default) uses the fast core when it is installed and the configuration
  is supported, and prints which engine ran and why.
- In the Python engine: the main loop is `play_game()`/`play_game_batch()` in
  `cardsharp/blackjack/blackjack.py`, dealing is `Shoe` in `cardsharp/common/shoe.py`,
  strategy lookups are in `cardsharp/blackjack/strategy.py`; per-round profile in
  `docs/perf/baseline-single-cpu-2026-06-09.md`
- The two engines are kept equivalent by a card-stream parity suite
  (`tests/test_fastsim_core.py`); any change to round semantics must land in both
  engines with parity proven
- The fast core is additionally regression-locked by a golden corpus
  (`tests/golden/`, replayed by `tests/test_fastsim_golden.py`): frozen
  parity-proven outputs compared exactly. Intentional semantic changes regenerate
  it (`uv run python -m cardsharp.tools.golden_corpus`) in the same commit, with
  the data diff reviewed; see `tests/golden/README.md`

**IMPORTANT**: When optimizing performance, never compromise accuracy. See `docs/optimization_principles.md` for guidelines. A fast but inaccurate simulation is worthless.

### Testing Strategy

- Unit tests for core components (cards, decks, game logic)
- Integration tests for game engines and APIs
- Event cleanup tests to prevent memory leaks
- Async tests using pytest-asyncio
- Test isolation: Each test module has its own pytest.ini configuration

### Type Checking with Pyrefly

The project uses Pyrefly for fast type checking:

```bash
# Type check a specific file
uv run pyrefly check cardsharp/blackjack/blackjack.py

# Type check the entire project
uv run pyrefly check .

# Check a code snippet
uv run pyrefly snippet "def foo(x: int) -> str: return x"

# Initialize pyrefly config (already done)
uv run pyrefly init

# Automatically add type annotations
uv run pyrefly autotype cardsharp/blackjack/strategy.py
```

Pyrefly configuration is in `pyrefly.toml` at the project root.