import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import time
from copy import deepcopy

from cardsharp.blackjack.actor import Dealer, Player
from cardsharp.blackjack.state import PlacingBetsState, WaitingForPlayersState, EndRoundState
from cardsharp.blackjack.stats import SimulationStats
from cardsharp.blackjack.strategy import BasicStrategy, CountingStrategy, AggressiveStrategy, MartingaleStrategy
from cardsharp.common.deck import Deck
from cardsharp.common.io_interface import DummyIOInterface

class BlackjackGame:
    def __init__(self, rules, io_interface):
        self.players = []
        self.io_interface = io_interface
        self.dealer = Dealer("Dealer", io_interface)
        self.rules = rules
        self.deck = Deck()
        self.current_state = WaitingForPlayersState()
        self.stats = SimulationStats()

    def set_state(self, state):
        self.current_state = state

    def add_player(self, player):
        if self.current_state is not None:
            self.current_state.add_player(self, player)

    def play_round(self):
        while not isinstance(self.current_state, EndRoundState):
            self.current_state.handle(self)
        self.current_state.handle(self)

    def reset(self):
        self.deck = Deck()
        for player in self.players:
            player.reset()
        self.dealer.reset()

def play_game_and_record(rules, io_interface, player_names, strategy):
    players = [Player(name, io_interface, strategy) for name in player_names]
    game = BlackjackGame(rules, io_interface)
    
    for player in players:
        game.add_player(player)

    game.set_state(PlacingBetsState())
    
    initial_deck = deepcopy(game.deck)
    
    game.play_round()

    earnings = sum(player.money - 1000 for player in game.players)
    
    return earnings, game.stats.report(), initial_deck

def replay_game_with_strategy(rules, io_interface, player_names, strategy, initial_deck):
    players = [Player(name, io_interface, strategy) for name in player_names]
    game = BlackjackGame(rules, io_interface)
    
    for player in players:
        game.add_player(player)

    game.set_state(PlacingBetsState())
    
    game.deck = initial_deck
    
    game.play_round()

    earnings = sum(player.money - 1000 for player in game.players)
    
    return earnings, game.stats.report()

def run_strategy_analysis(num_games, strategies, rules):
    results = {strategy: {"net_earnings": 0, "wins": 0, "losses": 0, "draws": 0, "bankrupt": False} for strategy in strategies}
    player_names = ["Bob"]
    earnings_data = {strategy: [] for strategy in strategies}

    progress_bar = st.progress(0)
    status_text = st.empty()

    for game_number in range(num_games):
        _, _, initial_deck = play_game_and_record(rules, DummyIOInterface(), player_names, BasicStrategy())

        for strategy_name, strategy in strategies.items():
            if not results[strategy_name]["bankrupt"]:
                earnings, result = replay_game_with_strategy(rules, DummyIOInterface(), player_names, strategy, deepcopy(initial_deck))

                results[strategy_name]["net_earnings"] += earnings
                results[strategy_name]["wins"] += result["player_wins"]
                results[strategy_name]["losses"] += result["dealer_wins"]
                results[strategy_name]["draws"] += result["draws"]
                earnings_data[strategy_name].append(results[strategy_name]["net_earnings"])

                if results[strategy_name]["net_earnings"] <= -1000:
                    results[strategy_name]["bankrupt"] = True

        progress_bar.progress((game_number + 1) / num_games)
        status_text.text(f"Simulating game {game_number + 1} of {num_games}")

    status_text.text("Simulation complete!")
    return results, earnings_data

st.set_page_config(page_title="Blackjack Strategy Simulator", layout="wide")

st.title("Blackjack Strategy Simulator")

st.sidebar.header("Simulation Parameters")
num_games = st.sidebar.slider("Number of Games", 100, 10000, 1000)
selected_strategies = st.sidebar.multiselect(
    "Select Strategies",
    ["Basic", "Counting", "Aggressive", "Martingale"],
    default=["Basic", "Counting"]
)

if st.sidebar.button("Run Simulation"):
    rules = {
        "blackjack_payout": 1.5,
        "allow_insurance": True,
        "min_players": 1,
        "min_bet": 10,
        "max_players": 6,
    }

    strategies = {
        "Basic": BasicStrategy(),
        "Counting": CountingStrategy(),
        "Aggressive": AggressiveStrategy(),
        "Martingale": MartingaleStrategy(),
    }

    selected_strategy_objects = {name: strategies[name] for name in selected_strategies}

    start_time = time.time()
    results, earnings_data = run_strategy_analysis(num_games, selected_strategy_objects, rules)
    end_time = time.time()
    duration = end_time - start_time

    st.header("Simulation Results")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Strategy Performance")
        for strategy_name, result in results.items():
            st.write(f"**{strategy_name} Strategy**")
            st.write(f"Net Earnings: ${result['net_earnings']:,.2f}")
            st.write(f"Wins: {result['wins']}")
            st.write(f"Losses: {result['losses']}")
            st.write(f"Draws: {result['draws']}")
            st.write(f"Bankrupt: {'Yes' if result['bankrupt'] else 'No'}")

            total_games = result['wins'] + result['losses'] + result['draws']
            if total_games > 0:
                win_rate = result['wins'] / total_games
                st.write(f"Win Rate: {win_rate:.2%}")
            st.write("---")

    with col2:
        st.subheader("Performance Visualization")
        fig, ax = plt.subplots(figsize=(10, 6))
        for strategy, earnings in earnings_data.items():
            ax.plot(range(1, len(earnings) + 1), earnings, label=strategy)
        ax.set_xlabel("Games Played")
        ax.set_ylabel("Net Earnings ($)")
        ax.set_title("Strategy Performance Over Time")
        ax.legend()
        ax.grid(True)
        st.pyplot(fig)

    st.header("Simulation Statistics")
    st.write(f"Total simulation time: {duration:.2f} seconds")
    st.write(f"Games simulated per second: {num_games/duration:.2f}")

    st.header("Earnings Data")
    df = pd.DataFrame(earnings_data)
    st.dataframe(df)

st.sidebar.markdown("---")
st.sidebar.header("How to Use")
st.sidebar.markdown("""
1. Adjust the number of games using the slider.
2. Select the strategies you want to compare.
3. Click 'Run Simulation' to start.
4. View the results, visualization, and earnings data below.
""")