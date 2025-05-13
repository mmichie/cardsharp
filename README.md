# CardSharp: Advanced Card Game Simulation Framework

CardSharp is a powerful Python package for simulating, analyzing, and playing
card games. While it currently focuses on Blackjack, its flexible architecture
allows for easy extension to other card games.

[![GitHub stars](https://img.shields.io/github/stars/mmichie/cardsharp.svg)](https://github.com/mmichie/cardsharp/stargazers)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Versions](https://img.shields.io/pypi/pyversions/cardsharp.svg)](https://pypi.org/project/cardsharp/)

## 🚀 Key Features

- 🃏 Robust Blackjack simulation with multiple strategies
- 📊 Real-time visualization of game statistics
- ⚙️ Highly configurable game rules and parameters
- 🧪 Extensible framework for implementing new card games
- 🖥️ Support for both CLI and programmatic usage
- 🧮 Advanced statistical analysis of game outcomes
- 🔄 Event-driven architecture for improved modularity
- 🔌 Platform adapters for multi-platform support

## 🛠️ Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/cardsharp.git
cd cardsharp

# Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`

# Install dependencies
pip install poetry
poetry install
```

## 🎮 Usage

CardSharp offers various modes of operation to suit different needs:

### Blackjack Simulation

Run a batch simulation of Blackjack games:

```bash
python cardsharp/blackjack/blackjack.py --simulate --num_games 10000 --vis
```

This command simulates 10,000 games of Blackjack and displays a real-time visualization of the results.

### Strategy Analysis

Compare different Blackjack strategies:

```bash
python cardsharp/blackjack/blackjack.py --analysis --num_games 5000
```

This runs a comparative analysis of Basic, Counting, Aggressive, and Martingale strategies over 5,000 games.

### Interactive Console Mode

Play Blackjack interactively in the console:

```bash
python cardsharp/blackjack/blackjack.py --console
```

### Event System Demo

Try the new event system:

```bash
python examples/event_system_demo.py
```

### Platform Adapter Demo

Experience the platform adapter system:

```bash
python examples/adapter_demo.py
```

### Immutable State Demo

See how immutable state transitions work:

```bash
python examples/immutable_state_demo.py
```

### BlackjackEngine Demo

Experience the new engine with immutable state:

```bash
python examples/blackjack_engine_demo.py
```

### Asynchronous API Demo

See the new Phase 3 asynchronous API in action:

```bash
python examples/async_api_demo.py
```

This demo showcases:
- High-level BlackjackGame interface
- Event-driven flow control
- Synchronous and asynchronous operation modes
- Auto-play capabilities

### Full CLI Blackjack Game

Play the complete blackjack game using the new architecture:

```bash
python examples/cli_blackjack.py
```

You can customize your game experience with these options:
```bash
# Play with 3 players
python examples/cli_blackjack.py --players 3

# Start with a custom bankroll
python examples/cli_blackjack.py --bankroll 500

# Play a fixed number of rounds
python examples/cli_blackjack.py --rounds 5
```

## 📁 Project Structure

- `cardsharp/`
  - `blackjack/`: Blackjack-specific implementations
  - `common/`: Shared utilities and base classes
  - `events/`: Event system for event-driven architecture
  - `adapters/`: Platform adapters for different environments
  - `state/`: Immutable state models and transition functions
  - `engine/`: Core game engine implementation
  - `war/`: War card game implementation
  - `high_card/`: High Card game implementation
  - `roulette/`: Roulette game implementation (in progress)
  - `verification/`: Game verification and event recording

## 🏗️ Architecture

CardSharp has undergone a phased modernization to an event-driven, adapter-based architecture:

- **Event System**: Core components communicate through a robust event system
- **Adapters**: Platform-specific code is isolated in adapters
- **Immutable State**: Game state transitions via pure functions
- **Asynchronous API**: Clean, platform-agnostic API with rich event-driven flow control
- **Dual Mode**: Support for both synchronous and asynchronous operation

The architecture modernization plan has completed three phases:
1. ✅ Phase 1: Event System and Adapters
2. ✅ Phase 2: Immutable State
3. ✅ Phase 3: Asynchronous API

Check out the [architecture documentation](docs/architecture_modernization.md) for details.

## 🧪 Testing

Run the test suite to ensure everything is working correctly:

```bash
pytest tests/
```

## 🤝 Contributing

We welcome contributions! Here's how you can help:

1. Fork the repository
2. Create a new branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests to ensure no regressions
5. Commit your changes (`git commit -am 'Add some amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🌟 Star Us!

If you find CardSharp useful, please consider giving it a star on GitHub. It helps us gain visibility and encourages further development!

[![GitHub stars](https://img.shields.io/github/stars/mmichie/cardsharp.svg?style=social&label=Star)](https://github.com/mmichie/cardsharp)

## 📬 Contact

For questions, suggestions, or discussions, please open an issue on GitHub or
contact the maintainers directly.

Happy gaming and may the odds be ever in your favor! 🎰🃏
