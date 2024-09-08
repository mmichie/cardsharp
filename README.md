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

## 📁 Project Structure

- `cardsharp/`
  - `blackjack/`: Blackjack-specific implementations
  - `common/`: Shared utilities and base classes
  - `war/`: War card game implementation
  - `high_card/`: High Card game implementation
  - `roulette/`: Roulette game implementation (in progress)

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
