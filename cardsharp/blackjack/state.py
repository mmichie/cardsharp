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

from cardsharp.common.card import Rank
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
        min_bet = game.rules.min_bet
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
        self.deal(game)
        game.set_state(OfferInsuranceState())

    def deal(self, game):
        """
        Handles the card dealing and notifies the interface.
        """
        for _ in range(2):
            for player in game.players + [game.dealer]:
                card = game.shoe.deal()
                player.add_card(card)
                game.add_visible_card(card)
                if player != game.dealer:
                    game.io_interface.output(f"Dealt {card} to {player.name}.")

    def check_blackjack(self, game):
        """Checks for blackjack for dealer and players, handles payouts appropriately."""
        dealer_has_blackjack = game.dealer.current_hand.is_blackjack

        # First, check if the dealer has blackjack
        if dealer_has_blackjack:
            game.io_interface.output("Dealer got a blackjack!")

            # Handle insurance bets
            for player in game.players:
                if player.insurance > 0:
                    # Payout insurance bet at 2:1 (player receives 3 times the insurance bet)
                    insurance_payout = player.insurance * 3
                    player.payout_insurance(insurance_payout)
                    game.io_interface.output(
                        f"{player.name} wins insurance bet of ${player.insurance:.2f}."
                    )

            # Now, handle players' hands
            for player in game.players:
                if player.current_hand.is_blackjack:
                    # Push - return the original bet
                    bet = player.bets[0]
                    player.payout(0, bet)
                    player.winner = ["draw"]
                    game.io_interface.output(
                        f"{player.name} and dealer both have blackjack. Push."
                    )
                else:
                    # Dealer wins, player loses bet
                    player.winner = ["dealer"]
                    game.io_interface.output(
                        f"{player.name} loses to dealer's blackjack."
                    )
        else:
            # Dealer does not have blackjack
            # Handle insurance bets: players lose insurance bets
            for player in game.players:
                if player.insurance > 0:
                    game.io_interface.output(
                        f"{player.name} loses insurance bet of ${player.insurance:.2f}."
                    )
                    # Insurance bet was already deducted when bought; no further action needed

            # Check for player blackjacks
            for player in game.players:
                if player.current_hand.is_blackjack:
                    game.io_interface.output(f"{player.name} got a blackjack!")
                    bet = player.bets[0]  # Use the bet for the first hand
                    # Use precise arithmetic for correct payout
                    payout_amount = bet + (bet * game.rules.blackjack_payout)
                    player.payout(0, payout_amount)  # Payout for hand index 0
                    player.blackjack = True
                    player.winner = [
                        "player"
                    ]  # Since there's only one hand at this point
                    player.hand_done[player.current_hand_index] = True


class OfferInsuranceState(GameState):
    """
    The game state where insurance is offered if the dealer has an Ace,
    and the dealer checks for blackjack if appropriate.
    """

    def handle(self, game):
        """
        Offers insurance to the players if the dealer's upcard is an Ace.
        If the dealer's upcard is an Ace or a ten-value card, checks for dealer blackjack
        after insurance decisions are made. If the dealer has blackjack, resolves bets immediately.
        Otherwise, checks for player blackjacks and proceeds to the players' turns.
        """
        # Offer insurance to each player if the dealer has an Ace
        for player in game.players:
            self.offer_insurance(game, player)

        # Show the dealer's face-up card
        game.io_interface.output(
            "Dealer's face-up card is: " + str(game.dealer.current_hand.cards[0])
        )

        # Get the dealer's upcard rank
        dealer_up_rank = game.dealer.current_hand.cards[0].rank

        # Initialize dealer_has_blackjack flag
        dealer_has_blackjack = False

        # Check if dealer peek is allowed
        if game.rules.should_dealer_peek():
            # Dealer peeks only if the upcard is an Ace or ten-value card
            if dealer_up_rank == Rank.ACE or dealer_up_rank.rank_value == 10:
                dealer_has_blackjack = game.dealer.current_hand.is_blackjack
                if dealer_has_blackjack:
                    self.handle_dealer_blackjack(game)
                    game.set_state(EndRoundState())
                    return
        else:
            # In games without dealer peek, insurance is only offered if the upcard is an Ace
            if dealer_up_rank == Rank.ACE:
                # Offer insurance and proceed without checking for dealer blackjack
                pass  # Already handled above

        # If dealer does not have blackjack, handle insurance bets and check for player blackjacks
        if not dealer_has_blackjack:
            # Handle insurance bets: players lose insurance bets
            for player in game.players:
                if player.insurance > 0:
                    game.io_interface.output(
                        f"{player.name} loses insurance bet of ${player.insurance:.2f}."
                    )
                    # Insurance bet was already deducted when bought; no further action needed
                    player.insurance = 0  # Reset insurance bet

            # Check for player blackjacks
            for player in game.players:
                if player.current_hand.is_blackjack:
                    game.io_interface.output(f"{player.name} got a blackjack!")
                    bet = player.bets[0]  # Use the bet for the first hand
                    # Calculate the payout for blackjack
                    payout_amount = bet + (bet * game.rules.blackjack_payout)
                    player.payout(0, payout_amount)  # Payout for hand index 0
                    player.blackjack = True
                    player.winner = [
                        "player"
                    ]  # Since there's only one hand at this point
                    player.hand_done[player.current_hand_index] = True

        # Proceed to players' turns
        game.set_state(PlayersTurnState())

    def offer_insurance(self, game, player):
        """
        Offers insurance to a player if the dealer's upcard is an Ace.
        """
        if game.dealer.has_ace():
            game.io_interface.output("Dealer has an Ace!")
            # Use the player's strategy to decide whether to buy insurance
            wants_insurance = player.strategy.decide_insurance(player)
            if wants_insurance:
                # Calculate the insurance bet amount (usually half of the original bet)
                insurance_bet = player.bets[0] / 2
                player.buy_insurance(insurance_bet)
                game.io_interface.output(f"{player.name} has bought insurance.")

    def handle_dealer_blackjack(self, game):
        """
        Handles the scenario where the dealer has blackjack.
        Resolves insurance bets and player bets accordingly.
        """
        game.io_interface.output("Dealer has blackjack!")

        # Handle insurance payouts
        for player in game.players:
            if player.insurance > 0:
                # Payout insurance bets at 2:1
                insurance_payout = player.insurance * 3
                player.payout_insurance(insurance_payout)
                game.io_interface.output(
                    f"{player.name} wins insurance bet of ${player.insurance:.2f}."
                )
                player.insurance = 0  # Reset insurance bet

        # Resolve player bets
        for player in game.players:
            if player.current_hand.is_blackjack:
                # If the player also has blackjack, it's a push
                bet = player.bets[0]
                player.payout(0, bet)  # Return the original bet
                player.winner = ["draw"]
                game.io_interface.output(
                    f"{player.name} and dealer both have blackjack. Push."
                )
            else:
                # Dealer wins; player loses their bet
                player.winner = ["dealer"]
                game.io_interface.output(f"{player.name} loses to dealer's blackjack.")


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
                    valid_actions = self.get_valid_actions(game, player, hand_index)
                    action = player.decide_action(dealer_up_card=dealer_up_card)
                    if action in valid_actions:
                        self.player_action(game, player, action)
                    else:
                        game.io_interface.output(
                            f"Invalid action {action}. Standing instead."
                        )
                        player.stand()
                        player.hand_done[hand_index] = True
                    if player.is_busted() or player.is_done():
                        break  # Exit the loop if player is busted or done
        game.set_state(DealersTurnState())

    def get_valid_actions(self, game, player, hand_index):
        """Determines the valid actions for the current hand."""
        valid_actions = [Action.HIT, Action.STAND]
        hand = player.hands[hand_index]

        if len(hand.cards) == 2:
            if game.can_double_down(hand):
                if hand_index == 0 or game.rules.can_double_after_split():
                    valid_actions.append(Action.DOUBLE)

            if (
                game.can_split(hand) and len(player.hands) < 4
            ):  # Limit splits to 3 times
                valid_actions.append(Action.SPLIT)

            if game.can_surrender(hand):
                valid_actions.append(Action.SURRENDER)

        return valid_actions

    def player_action(self, game, player, action):
        """Handles a player action and notifies the interface."""
        if action == Action.HIT:
            card = game.shoe.deal()
            player.hit(card)
            game.add_visible_card(card)
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
            card = game.shoe.deal()
            player.hit(card)
            game.io_interface.output(f"{player.name} doubles down and gets {card}.")
            if player.is_busted():
                game.io_interface.output(f"{player.name} has busted.")
            # Mark the current hand as done
            player.hand_done[player.current_hand_index] = True
        elif action == Action.SPLIT:
            player.split()
            game.io_interface.output(f"{player.name} splits.")
            # After splitting, deal a card to each new hand
            for i in range(player.current_hand_index, player.current_hand_index + 2):
                card = game.shoe.deal()
                player.hands[i].add_card(card)
                game.add_visible_card(card)
                game.io_interface.output(f"{player.name}'s hand {i + 1} gets {card}.")
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
        """Handles the dealer's actions and changes the game state to EndRoundState."""
        all_players_busted = all(player.is_busted() for player in game.players)

        while not all_players_busted and game.dealer.should_hit(game.rules):
            self.dealer_action(game)

        game.io_interface.output("Dealer stands.")
        game.set_state(EndRoundState())

    def dealer_action(self, game):
        """
        Handles a dealer action and notifies the interface.
        """
        card = game.shoe.deal()
        game.dealer.add_card(card)
        game.add_visible_card(card)
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
        game.visible_cards = []
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
                    if player.blackjack:
                        # Use the blackjack payout from the rules
                        payout_multiplier = game.get_blackjack_payout()
                        payout_amount = bet_for_hand + (
                            bet_for_hand * payout_multiplier
                        )
                    else:
                        payout_amount = bet_for_hand * 2  # Regular win pays 1:1
                    player.payout(hand_index, payout_amount)
                elif winner == "draw":
                    payout_amount = bet_for_hand
                    player.payout(hand_index, payout_amount)
                else:
                    # Player loses bet; no payout
                    player.bets[hand_index] = 0  # Reset bet for this hand
