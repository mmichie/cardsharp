# CardSharp

A Python framework for simulating and analyzing card games. Currently supports
Blackjack, War, High Card, Baccarat, Dragon Tiger, and Durak.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Installation

```bash
git clone https://github.com/mmichie/cardsharp.git
cd cardsharp
uv sync
```

## Usage

### Simulation

```bash
# Run 10,000 blackjack games with visualization
uv run python cardsharp/blackjack/blackjack.py --simulate --num_games 10000 --vis

# Compare strategies (Basic, Counting, Aggressive, Martingale)
uv run python cardsharp/blackjack/blackjack.py --analysis --num_games 5000

# Performance profiling
uv run python cardsharp/blackjack/blackjack.py --simulate --profile --num_games 1000
```

### Interactive Play

```bash
# Console blackjack
uv run python cardsharp/blackjack/blackjack.py --console

# Full CLI game with options
uv run python examples/cli_blackjack.py --players 3 --bankroll 500 --rounds 5
```

### Examples

```bash
uv run python examples/async_api_demo.py        # Async API with event-driven flow
uv run python examples/blackjack_engine_demo.py  # Engine with immutable state
uv run python examples/adapter_demo.py           # Platform adapter system
uv run python examples/modern_blackjack_ui.py    # Streamlit web UI
```

See `examples/` for the full set of demos.

## Architecture

CardSharp uses an event-driven architecture with immutable state transitions:

- **Events** -- Components communicate through pub/sub (`cardsharp/events/`)
- **Immutable State** -- Game state transitions via pure functions (`cardsharp/state/`)
- **Engines** -- Game logic per game type (`cardsharp/engine/`, `cardsharp/blackjack/`, etc.)
- **Adapters** -- Platform-specific rendering and input (`cardsharp/adapters/`)
- **APIs** -- High-level sync/async interfaces (`cardsharp/api/`)

## Testing

```bash
uv run pytest                              # Run all tests
uv run pytest --cov=cardsharp              # With coverage
uv run pytest tests/api/test_event_cleanup.py -v  # Specific module
uv run pytest -n auto                      # Parallel
```

## License

MIT
