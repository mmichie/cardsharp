"""
This module provides an asynchronous game state management system for a
Blackjack game. It uses the state design pattern to manage the various game
states and transitions between them. The game progresses through various states:
WaitingForPlayersState, PlacingBetsState, DealingState, OfferInsuranceState,
PlayersTurnState, DealersTurnState, and EndRoundState.

Classes:

GameState: An abstract base class for game states.
WaitingForPlayersState: The game state while the game is waiting for players to join.
PlacingBetsState: The game state where players are placing their bets.
DealingState: The game state where the dealer is dealing the cards.
OfferInsuranceState: The game state where insurance is offered if the dealer has an Ace.
PlayersTurnState: The game state where it's the players' turn to play.
DealersTurnState: The game state where it's the dealer's turn to play.
EndRoundState: The game state where the round is ending.
The handle method in each game state class is responsible for performing the
actions required in that state, notifying the interface, and transitioning to
the next state. Each game state class also overrides the str method to return
the state name.
"""

import time

from abc import ABC
from abc import abstractmethod
from cardsharp.blackjack.action import Action
from cardsharp.common.io_interface import DummyIOInterface


class GameState(ABC):
    """
    Abstract base class for game states.
    """

    @abstractmethod
    def handle(self, game) -> None:
        """The method that handles the game state."""

    def __str__(self) -> str:
        return self.__class__.__name__


class WaitingForPlayersState(GameState):
    """
    The game state while the game is waiting for players to join.
    """

    def handle(self, game):
        """
        Continuously checks if the minimum number of players have joined.
        If so, it changes the game state to PlacingBetsState.
        """
        while len(game.players) < game.minimum_players:
            time.sleep(1)
        game.set_state(PlacingBetsState())

    def add_player(self, game, player):
        """
        Adds a player to the game and notifies the interface.
        """
        game.players.append(player)
        game.io_interface.output(f"{player.name} has joined the game.")


class PlacingBetsState(GameState):
    """
    The game state where players are placing their bets.
    """

    def handle(self, game):
        """
        Handles the player bets and changes the game state to DealingState.
        """
        for player in game.players:
            self.place_bet(game, player, 10)
        game.set_state(DealingState())

    def place_bet(self, game, player, amount):
        """
        Handles the bet placement of a player and notifies the interface.
        """
        min_bet = game.rules["min_bet"]
        player.place_bet(amount, min_bet)
        game.io_interface.output(f"{player.name} has placed a bet of {amount}.")


class DealingState(GameState):
    """
    The game state where the dealer is dealing the cards.
    """

    def handle(self, game):
        """
        Handles the card dealing, checks for blackjack, and changes the game state to OfferInsuranceState.
        """
        game.deck.reset()
        self.deal(game)
        self.check_blackjack(game)
        game.set_state(OfferInsuranceState())

    def deal(self, game):
        """
        Handles the card dealing and notifies the interface.
        """
        for _ in range(2):
            for player in game.players + [game.dealer]:
                card = game.deck.deal()
                player.add_card(card)
                if player != game.dealer:
                    game.io_interface.output(f"Dealt {card} to {player.name}.")

    def check_blackjack(self, game):
        """Checks for blackjack for all players and handles the payouts."""
        for player in game.players:
            if player.current_hand.is_blackjack:
                game.io_interface.output(f"{player.name} got a blackjack!")
                bet = player.bets[0]  # Use the bet for the first hand
                payout_amount = bet + int(bet * game.rules["blackjack_payout"])
                player.payout(0, payout_amount)  # Payout for hand index 0
                player.blackjack = True
                player.winner = ["player"]  # Since there's only one hand at this point
                player.hand_done[player.current_hand_index] = True

        if game.dealer.current_hand.is_blackjack:
            game.io_interface.output("Dealer got a blackjack!")
            for player in game.players:
                if not player.blackjack:
                    player.done = True
                    player.winner = ["dealer"]
                else:
                    # Push - return the bet
                    bet = player.bets[0]
                    player.payout(0, bet)
                    player.winner = ["draw"]


class OfferInsuranceState(GameState):
    """
    The game state where insurance is offered if the dealer has an Ace.
    """

    def handle(self, game):
        """
        Offers insurance to the players if the dealer has an Ace, and changes the game state to PlayersTurnState.
        """
        for player in game.players:
            self.offer_insurance(game, player)
        game.io_interface.output(
            "Dealer's face up card is: " + str(game.dealer.current_hand.cards[0])
        )
        game.set_state(PlayersTurnState())

    def offer_insurance(self, game, player):
        """
        Offers insurance to a player and handles the insurance purchase.
        """
        if game.dealer.has_ace():
            game.io_interface.output("Dealer has an Ace!")
            player.buy_insurance(10)
            game.io_interface.output(f"{player.name} has bought insurance.")


class PlayersTurnState(GameState):
    """
    The game state where it's the players' turn to play.
    """

    def handle(self, game):
        """Handles the players' actions and changes the game state to DealersTurnState."""
        dealer_up_card = game.dealer.current_hand.cards[0]
        for player in game.players:
            if player.done:
                continue  # Skip this player
            game.io_interface.output(f"{player.name}'s turn.")
            # Iterate over each hand the player has
            for hand_index, hand in enumerate(player.hands):
                player.current_hand_index = hand_index
                if player.hand_done[hand_index]:
                    continue  # Skip hands that are already done
                game.io_interface.output(f"Playing hand {hand_index + 1}")
                while not player.hand_done[hand_index]:
                    action = player.decide_action(dealer_up_card=dealer_up_card)
                    self.player_action(game, player, action)
                    if player.is_busted() or player.is_done():
                        break  # Exit the loop if player is busted or done
        game.set_state(DealersTurnState())

    def player_action(self, game, player, action):
        """Handles a player action and notifies the interface."""
        if action == Action.HIT:
            card = game.deck.deal()
            player.hit(card)
            game.io_interface.output(f"{player.name} hits and gets {card}.")
            if player.is_busted():
                game.io_interface.output(f"{player.name} has busted.")
                # Mark the current hand as done
                player.hand_done[player.current_hand_index] = True
        elif action == Action.STAND:
            player.stand()
            # Mark the current hand as done
            player.hand_done[player.current_hand_index] = True
            game.io_interface.output(f"{player.name} stands.")
        elif action == Action.DOUBLE:
            player.double_down()
            card = game.deck.deal()
            player.hit(card)
            game.io_interface.output(f"{player.name} doubles down and gets {card}.")
            if player.is_busted():
                game.io_interface.output(f"{player.name} has busted.")
            # Mark the current hand as done
            player.hand_done[player.current_hand_index] = True
        elif action == Action.SPLIT:
            player.split()
            game.io_interface.output(f"{player.name} splits.")
            # After splitting, update the hand_done list to include the new hands
            # Note: The player will continue to play these hands in the main loop
        elif action == Action.SURRENDER:
            player.surrender()
            game.io_interface.output(f"{player.name} surrenders.")
            # Mark the current hand as done
            player.hand_done[player.current_hand_index] = True


class DealersTurnState(GameState):
    """
    The game state where it's the dealer's turn to play.
    """

    def handle(self, game):
        """
        Handles the dealer's actions and changes the game state to EndRoundState.
        """
        all_players_busted = all(player.is_busted() for player in game.players)

        while not all_players_busted and game.dealer.should_hit():
            self.dealer_action(game)

        game.io_interface.output("Dealer stands.")
        game.set_state(EndRoundState())

    def dealer_action(self, game):
        """
        Handles a dealer action and notifies the interface.
        """
        card = game.deck.deal()
        game.dealer.add_card(card)
        game.io_interface.output(f"Dealer hits and gets {card}.")


class EndRoundState(GameState):
    """
    The game state where the round is ending.
    """

    def handle(self, game):
        """
        Handles the calculation of the winner, updates the statistics, and changes the game state to PlacingBetsState.
        """
        self.calculate_winner(game)
        self.output_results(game)
        self.handle_payouts(game)
        game.stats.update(game)
        game.set_state(PlacingBetsState())

    def calculate_winner(self, game):
        """Calculates the winner of the round."""
        dealer_hand_value = game.dealer.current_hand.value()
        for player in game.players:
            player.winner = []
            for hand in player.hands:
                player_hand_value = hand.value()
                if player_hand_value > 21:
                    winner = "dealer"
                elif dealer_hand_value > 21 or player_hand_value > dealer_hand_value:
                    winner = "player"
                elif player_hand_value < dealer_hand_value:
                    winner = "dealer"
                else:
                    winner = "draw"
                player.winner.append(winner)

    def output_results(self, game):
        """Outputs the results of the round."""
        if isinstance(game.io_interface, DummyIOInterface):
            return  # Short-circuit if the interface is a dummy

        dealer_hand_value = game.dealer.current_hand.value()
        dealer_cards = ", ".join(str(card) for card in game.dealer.current_hand.cards)
        game.io_interface.output(f"Dealer's final cards: {dealer_cards}")
        game.io_interface.output(f"Dealer's final hand value: {dealer_hand_value}")

        for player in game.players:
            for hand_index, hand in enumerate(player.hands):
                player_hand_value = hand.value()
                player_cards = ", ".join(str(card) for card in hand.cards)
                game.io_interface.output(
                    f"{player.name}'s hand {hand_index + 1} final cards: {player_cards}"
                )
                game.io_interface.output(
                    f"{player.name}'s hand {hand_index + 1} final hand value: {player_hand_value}"
                )
                winner = player.winner[hand_index]
                if winner == "dealer":
                    game.io_interface.output(
                        f"{player.name}'s hand {hand_index + 1} loses. Dealer wins!"
                    )
                elif winner == "player":
                    game.io_interface.output(
                        f"{player.name}'s hand {hand_index + 1} wins the round!"
                    )
                elif winner == "draw":
                    game.io_interface.output(
                        f"{player.name}'s hand {hand_index + 1} and Dealer tie! It's a push."
                    )

    def handle_payouts(self, game):
        """Handles the payouts for the round."""
        for player in game.players:
            for hand_index, hand in enumerate(player.hands):
                winner = player.winner[hand_index]
                bet_for_hand = player.bets[hand_index]
                if bet_for_hand == 0:
                    continue  # Skip hands with no bet
                if winner == "player":
                    payout_amount = bet_for_hand * 2
                    player.payout(hand_index, payout_amount)
                elif winner == "draw":
                    payout_amount = bet_for_hand
                    player.payout(hand_index, payout_amount)
                else:
                    # Player loses bet; no payout
                    player.bets[hand_index] = 0  # Reset bet for this hand
