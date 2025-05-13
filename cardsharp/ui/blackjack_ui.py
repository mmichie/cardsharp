"""
Modern Blackjack UI implementation for Cardsharp.

This module provides a Streamlit-based UI for playing Blackjack using
the new engine and API pattern.
"""

import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import time
import asyncio
import threading
from typing import Dict, Any, List, Optional
import uuid

from cardsharp.api import BlackjackGame
from cardsharp.adapters import DummyAdapter, WebAdapter
from cardsharp.blackjack.action import Action
from cardsharp.events import EventBus, EngineEventType
from cardsharp.blackjack.state import GameStage


class BlackjackUI:
    """
    Streamlit-based UI for Blackjack using the new engine pattern.

    This class provides a web interface for playing Blackjack using
    the new engine and API pattern.
    """

    def __init__(self):
        """Initialize the BlackjackUI."""
        # Initialize session state for storing game state
        if "game_initialized" not in st.session_state:
            st.session_state.game_initialized = False
            st.session_state.game_state = None
            st.session_state.players = []
            st.session_state.events = []
            st.session_state.earnings_data = {}
            st.session_state.game_id = str(uuid.uuid4())
            st.session_state.round_number = 0

        # Create a web adapter
        self.adapter = WebAdapter(use_websockets=False)

        # Create lock for thread safety
        self.lock = threading.Lock()

        # Event bus for listening to game events
        self.event_bus = EventBus.get_instance()

        # Create the game instance
        self.game = None

    async def initialize_game(self):
        """Initialize the Blackjack game."""
        # Create the game with our adapter
        config = {
            "dealer_rules": {"stand_on_soft_17": True, "peek_for_blackjack": True},
            "deck_count": 6,
            "rules": {
                "blackjack_pays": 1.5,
                "deck_count": 6,
                "dealer_hit_soft_17": False,
                "offer_insurance": True,
                "allow_surrender": True,
                "allow_double_after_split": True,
                "min_bet": 5.0,
                "max_bet": 1000.0,
            },
        }

        self.game = BlackjackGame(adapter=self.adapter, config=config, auto_play=False)

        # Initialize the game
        await self.game.initialize()

        # Start the game
        await self.game.start_game()

        # Update session state
        with self.lock:
            st.session_state.game_initialized = True

        # Get initial state
        state = await self.game.get_state()
        self.update_game_state(state)

        # Set up state monitoring
        self.setup_state_monitoring()

    def update_game_state(self, state):
        """
        Update the game state in the session state.

        Args:
            state: Current game state
        """
        with self.lock:
            st.session_state.game_state = state.to_dict()
            st.session_state.game_id = state.id
            st.session_state.round_number = state.round_number

    def setup_state_monitoring(self):
        """Set up state monitoring thread."""
        # Create a thread to monitor the adapter's state queue
        self.monitor_thread = threading.Thread(target=self._monitor_state, daemon=True)
        self.monitor_thread.start()

    def _monitor_state(self):
        """Monitor the adapter's state queue for updates."""
        while True:
            state = self.adapter.get_next_state(timeout=0.1)
            if state:
                with self.lock:
                    st.session_state.game_state = state

            # Also check for events
            event = self.adapter.get_next_event(timeout=0.1)
            if event:
                event_type, event_data = event
                with self.lock:
                    st.session_state.events.append((event_type, event_data))

                    # Handle specific events
                    if event_type == "ACTION_REQUEST":
                        st.session_state.pending_action = event_data
                    elif (
                        event_type == "GAME_EVENT"
                        and event_data.get("type") == "ROUND_ENDED"
                    ):
                        # Update earnings data for visualization
                        if "earnings_data" not in st.session_state:
                            st.session_state.earnings_data = {}

                        for player_id, result in (
                            event_data.get("data", {}).get("results", {}).items()
                        ):
                            if player_id not in st.session_state.earnings_data:
                                st.session_state.earnings_data[player_id] = []

                            balance = result.get("balance", 0)
                            st.session_state.earnings_data[player_id].append(balance)

            # Sleep to avoid busy waiting
            time.sleep(0.1)

    async def add_player(self, name, balance=1000.0):
        """
        Add a player to the game.

        Args:
            name: Player name
            balance: Initial balance

        Returns:
            Player ID
        """
        player_id = await self.game.add_player(name, balance)

        with self.lock:
            st.session_state.players.append(
                {"id": player_id, "name": name, "balance": balance}
            )

        return player_id

    async def place_bet(self, player_id, amount):
        """
        Place a bet for a player.

        Args:
            player_id: Player ID
            amount: Bet amount

        Returns:
            True if bet was placed successfully
        """
        return await self.game.place_bet(player_id, amount)

    async def execute_action(self, player_id, action):
        """
        Execute a player action.

        Args:
            player_id: Player ID
            action: Action to execute

        Returns:
            True if action was executed successfully
        """
        return await self.game.execute_action(player_id, action)

    async def auto_play_round(self, default_bet=10.0):
        """
        Auto play a round of Blackjack.

        Args:
            default_bet: Default bet amount

        Returns:
            Round results
        """
        return await self.game.auto_play_round(default_bet)

    async def shutdown(self):
        """Shutdown the game."""
        if self.game:
            await self.game.shutdown()

    def run_simulation(self, num_rounds=100, players=None, default_bet=10.0):
        """
        Run a simulation of Blackjack games.

        Args:
            num_rounds: Number of rounds to simulate
            players: List of player names, or None to use existing players
            default_bet: Default bet amount

        Returns:
            Simulation results
        """

        async def _run():
            # Create a new game with a dummy adapter for simulation
            adapter = DummyAdapter()
            game = BlackjackGame(adapter=adapter, auto_play=True)

            # Initialize
            await game.initialize()
            await game.start_game()

            # Add players
            player_ids = []
            if players:
                for name in players:
                    player_id = await game.add_player(name, 1000.0)
                    player_ids.append(player_id)
            else:
                for player in st.session_state.players:
                    player_id = await game.add_player(player["name"], player["balance"])
                    player_ids.append(player_id)

            # Play rounds
            results = []
            for i in range(num_rounds):
                result = await game.auto_play_round(default_bet)
                results.append(result)

            # Get final state
            final_state = await game.get_state()

            # Shutdown
            await game.shutdown()

            return {"results": results, "final_state": final_state.to_dict()}

        # Run the simulation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()


def run_streamlit_app():
    """Run the Streamlit app."""
    st.set_page_config(page_title="Cardsharp Blackjack", layout="wide")

    st.title("Cardsharp Blackjack")

    # Create UI instance
    ui = BlackjackUI()

    # Check if game is initialized
    if not st.session_state.get("game_initialized", False):
        # Initialize the game
        if st.button("Start Game"):
            with st.spinner("Initializing game..."):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(ui.initialize_game())
                finally:
                    loop.close()
    else:
        # Game is initialized, show the game UI
        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("Game State")

            # Display game info
            game_state = st.session_state.get("game_state", {})
            if game_state:
                st.write(f"Game ID: {game_state.get('id', 'Unknown')}")
                st.write(f"Round: {game_state.get('round_number', 0)}")
                st.write(f"Stage: {game_state.get('stage', 'Unknown')}")

                # Display dealer info
                dealer = game_state.get("dealer", {})
                dealer_hand = dealer.get("hand", {})
                dealer_cards = dealer_hand.get("cards", [])
                st.write(f"Dealer: {', '.join(str(c) for c in dealer_cards)}")

                # Display player info
                st.subheader("Players")
                for player in game_state.get("players", []):
                    st.write(
                        f"**{player.get('name')}** (Balance: ${player.get('balance', 0)})"
                    )

                    for hand in player.get("hands", []):
                        cards = hand.get("cards", [])
                        st.write(f"Hand: {', '.join(str(c) for c in cards)}")
                        st.write(f"Value: {hand.get('value', 0)}")
                        st.write(f"Bet: ${hand.get('bet', 0)}")

                        if hand.get("outcome"):
                            st.write(f"Outcome: {hand.get('outcome')}")

                        if hand.get("payout"):
                            st.write(f"Payout: ${hand.get('payout')}")

            # Check for pending action requests
            pending_action = st.session_state.get("pending_action")
            if pending_action:
                st.subheader("Action Required")
                player_name = pending_action.get("player_name", "Unknown")
                valid_actions = pending_action.get("valid_actions", [])

                st.write(f"Player {player_name} needs to take an action")

                # Create buttons for each valid action
                cols = st.columns(len(valid_actions))
                request_id = pending_action.get("request_id")
                player_id = pending_action.get("player_id")

                for i, action in enumerate(valid_actions):
                    with cols[i]:
                        if st.button(action):
                            # Submit the action
                            ui.adapter.submit_action(action, request_id)

                            # Clear the pending action
                            st.session_state.pending_action = None

                            # Rerun the app to update the UI
                            st.experimental_rerun()

        with col2:
            st.subheader("Controls")

            # Add player
            with st.form("add_player_form"):
                st.write("Add Player")
                player_name = st.text_input("Name")
                player_balance = st.number_input(
                    "Balance", min_value=10.0, value=1000.0, step=10.0
                )

                submit = st.form_submit_button("Add Player")
                if submit and player_name:
                    with st.spinner("Adding player..."):
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            loop.run_until_complete(
                                ui.add_player(player_name, player_balance)
                            )
                        finally:
                            loop.close()

            # Place bet
            if game_state.get("stage") == "PLACING_BETS":
                with st.form("place_bet_form"):
                    st.write("Place Bet")

                    # Get list of players
                    players = st.session_state.get("players", [])
                    player_options = {p["name"]: p["id"] for p in players}

                    player_name = st.selectbox(
                        "Player", options=list(player_options.keys())
                    )
                    bet_amount = st.number_input(
                        "Bet Amount", min_value=5.0, value=10.0, step=5.0
                    )

                    submit = st.form_submit_button("Place Bet")
                    if submit and player_name:
                        player_id = player_options[player_name]
                        with st.spinner("Placing bet..."):
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                loop.run_until_complete(
                                    ui.place_bet(player_id, bet_amount)
                                )
                            finally:
                                loop.close()

            # Auto play round
            if st.button("Auto Play Round"):
                with st.spinner("Auto playing round..."):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(ui.auto_play_round())
                    finally:
                        loop.close()

            # Simulation controls
            st.subheader("Simulation")

            with st.form("simulation_form"):
                st.write("Run Simulation")
                num_rounds = st.number_input(
                    "Number of Rounds", min_value=1, value=100, step=10
                )
                default_bet = st.number_input(
                    "Default Bet", min_value=5.0, value=10.0, step=5.0
                )

                submit = st.form_submit_button("Run Simulation")
                if submit:
                    with st.spinner(f"Running simulation for {num_rounds} rounds..."):
                        results = ui.run_simulation(num_rounds, default_bet=default_bet)

                        # Store simulation results
                        st.session_state.simulation_results = results

                        # Show results
                        st.subheader("Simulation Results")
                        final_state = results.get("final_state", {})

                        # Show player results
                        for player in final_state.get("players", []):
                            name = player.get("name", "Unknown")
                            initial_balance = 1000.0  # Assuming initial balance is 1000
                            final_balance = player.get("balance", 0)
                            net_earnings = final_balance - initial_balance

                            st.write(f"**{name}**")
                            st.write(f"Final Balance: ${final_balance:.2f}")
                            st.write(f"Net Earnings: ${net_earnings:.2f}")

                        # Create a visualization of earnings over time
                        if st.session_state.get("earnings_data"):
                            st.subheader("Earnings Over Time")

                            fig, ax = plt.subplots(figsize=(10, 6))

                            for (
                                player_id,
                                earnings,
                            ) in st.session_state.earnings_data.items():
                                # Find player name
                                player_name = "Unknown"
                                for player in st.session_state.players:
                                    if player["id"] == player_id:
                                        player_name = player["name"]
                                        break

                                ax.plot(
                                    range(1, len(earnings) + 1),
                                    earnings,
                                    label=player_name,
                                )

                            ax.set_xlabel("Rounds")
                            ax.set_ylabel("Balance ($)")
                            ax.set_title("Player Earnings Over Time")
                            ax.legend()
                            ax.grid(True)

                            st.pyplot(fig)


if __name__ == "__main__":
    run_streamlit_app()
