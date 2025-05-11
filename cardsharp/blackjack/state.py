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


class InsufficientFundsError(Exception):
    """Raised when a player does not have enough money to perform an action."""

    pass


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
        self.check_blackjack(game)
        game.set_state(OfferInsuranceState())

    def deal(self, game):
        """
        Handles the card dealing and notifies the interface.
        """
        # Skip output for simulation mode
        is_dummy_io = isinstance(game.io_interface, DummyIOInterface)

        # Optimize dealing loop - reduce method lookups by having players_with_dealer ready
        players_with_dealer = game.players + [game.dealer]

        # First round - deal one card to each player and dealer
        for player in players_with_dealer:
            card = game.shoe.deal()
            player.add_card(card)
            game.add_visible_card(card)
            if not is_dummy_io and player != game.dealer:
                game.io_interface.output(f"Dealt {card} to {player.name}.")

        # Second round - deal second card to each player and dealer
        for player in players_with_dealer:
            card = game.shoe.deal()
            player.add_card(card)
            game.add_visible_card(card)
            if not is_dummy_io and player != game.dealer:
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
                    # Calculate winnings at 2:1 odds
                    winnings = player.insurance * 2
                    # Total payout includes the original insurance bet plus winnings
                    total_payout = player.insurance + winnings
                    player.payout_insurance(total_payout)
                    game.io_interface.output(
                        f"{player.name} wins insurance bet of ${total_payout:.2f}."
                    )
                    player.insurance = 0  # Reset insurance bet

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
        Handles insurance offers, dealer blackjack checks, and resolves insurance bets.
        """
        dealer_up_card = game.dealer.current_hand.cards[0]
        game.io_interface.output(f"Dealer shows {dealer_up_card}.")

        # Offer insurance if dealer's upcard is an Ace
        if dealer_up_card.rank == Rank.ACE and game.rules.allow_insurance:
            for player in game.players:
                self.offer_insurance(game, player)

        dealer_has_blackjack = False
        # Check for dealer blackjack if dealer peeking is allowed
        if game.rules.should_dealer_peek():
            if dealer_up_card.rank == Rank.ACE or dealer_up_card.rank.rank_value == 10:
                if game.dealer.current_hand.is_blackjack:
                    dealer_has_blackjack = True
                    self.handle_dealer_blackjack(game)
                    game.set_state(EndRoundState())
                    return

        # Dealer does not have blackjack
        # Handle loss of insurance bets
        for player in game.players:
            if player.insurance > 0:
                game.io_interface.output(
                    f"{player.name} loses insurance bet of ${player.insurance:.2f}."
                )
                # Insurance bet was already deducted when bought; reset insurance amount
                player.insurance = 0  # Reset insurance bet

        # Check for player blackjacks
        for player in game.players:
            if player.current_hand.is_blackjack:
                # Player wins immediately
                bet = player.bets[0]
                payout_amount = bet + (bet * game.rules.blackjack_payout)
                player.payout(0, payout_amount)
                player.blackjack = True
                player.winner = ["player"]
                player.hand_done[player.current_hand_index] = True
                game.io_interface.output(f"{player.name} got a blackjack!")

        # Proceed to players' turns
        game.set_state(PlayersTurnState())

    def offer_insurance(self, game, player):
        """
        Offers insurance to a player if the dealer's upcard is an Ace.
        """
        wants_insurance = player.strategy.decide_insurance(player)
        if wants_insurance:
            insurance_bet = player.bets[0] / 2
            try:
                player.buy_insurance(insurance_bet)
                game.io_interface.output(f"{player.name} has bought insurance.")
            except (ValueError, InsufficientFundsError) as e:
                game.io_interface.output(str(e))
        else:
            game.io_interface.output(f"{player.name} declines insurance.")

    def handle_dealer_blackjack(self, game):
        """
        Handles the scenario where the dealer has blackjack.
        Resolves insurance bets and player bets accordingly.
        """
        game.io_interface.output("Dealer has blackjack!")

        # Handle insurance payouts
        for player in game.players:
            if player.insurance > 0:
                total_payout = player.insurance * 3  # Original bet + 2:1 payout
                player.payout_insurance(total_payout)
                game.io_interface.output(
                    f"{player.name} wins insurance bet of ${total_payout:.2f}."
                )
                player.insurance = 0  # Reset insurance bet
            else:
                game.io_interface.output(f"{player.name} did not take insurance.")

        # Resolve player bets
        for player in game.players:
            if player.current_hand.is_blackjack:
                # Push
                bet = player.bets[0]
                player.payout(0, bet)
                player.winner = ["draw"]
                game.io_interface.output(
                    f"{player.name} and dealer both have blackjack. Push."
                )
            else:
                # Dealer wins
                player.winner = ["dealer"]
                game.io_interface.output(f"{player.name} loses to dealer's blackjack.")


class PlayersTurnState(GameState):
    """The game state where it's the players' turn to play."""

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
        """Returns valid actions for the player's current hand, considering game rules."""
        valid_actions = [Action.HIT, Action.STAND]
        hand = player.hands[hand_index]

        # Check if this is a split ace hand that already has two cards
        is_split_ace = (
            hand.is_split
            and any(card.rank == Rank.ACE for card in hand.cards)
            and len(hand.cards) >= 2
        )

        if is_split_ace:
            return [Action.STAND]  # Split aces can only stand after receiving one card

        if len(hand.cards) == 2:
            # Check double down based on game rules and hand value
            if game.rules.can_double_down(hand):
                if player.can_afford(player.bets[hand_index]):
                    valid_actions.append(Action.DOUBLE)

            # Check split
            if (
                game.rules.can_split(hand)
                and game.rules.can_split_more(len(player.hands))
                and player.can_afford(player.bets[hand_index])
            ):
                valid_actions.append(Action.SPLIT)

            is_first_action = len(player.action_history[hand_index]) == 0

            if game.rules.can_surrender(hand, is_first_action) and not hand.is_split:
                valid_actions.append(Action.SURRENDER)

        return valid_actions

    def player_action(self, game, player, action):
        """Handles a player action with proper split hand tracking."""

        player.action_history[player.current_hand_index].append(action)

        if action == Action.HIT:
            # Check if this is a split ace hand before allowing the hit
            if (
                player.current_hand.is_split
                and any(card.rank == Rank.ACE for card in player.current_hand.cards)
                and len(player.current_hand.cards) > 1
            ):
                game.io_interface.output(f"{player.name} cannot hit on split aces.")
                player.hand_done[player.current_hand_index] = True
                return

            card = game.shoe.deal()
            player.hit(card)
            game.add_visible_card(card)
            game.io_interface.output(f"{player.name} hits and gets {card}.")

            # Force stand on split aces after receiving one card
            if (
                player.current_hand.is_split
                and any(card.rank == Rank.ACE for card in player.current_hand.cards)
                and len(player.current_hand.cards) == 2
            ):
                player.hand_done[player.current_hand_index] = True
                game.io_interface.output(
                    f"{player.name}'s split ace stands automatically."
                )
            elif player.is_busted():
                game.io_interface.output(f"{player.name} has busted.")
                player.hand_done[player.current_hand_index] = True

        elif action == Action.SPLIT:
            curr_index = player.current_hand_index
            is_splitting_aces = player.current_hand.cards[0].rank == Rank.ACE

            # Process the split using the player's split method
            player.split()

            game.io_interface.output(f"{player.name} splits.")

            # Deal one card to each hand
            for i in range(curr_index, curr_index + 2):
                card = game.shoe.deal()
                player.hands[i].add_card(card)
                game.add_visible_card(card)
                game.io_interface.output(f"{player.name}'s hand {i + 1} gets {card}.")

                # If splitting aces, automatically stand after dealing one card
                if is_splitting_aces:
                    player.hand_done[i] = True
                    game.io_interface.output(
                        f"Split ace hand {i + 1} stands automatically."
                    )

        elif action == Action.DOUBLE:
            # Prevent doubling down on split aces
            if player.current_hand.is_split and any(
                card.rank == Rank.ACE for card in player.current_hand.cards
            ):
                game.io_interface.output(
                    f"{player.name} cannot double down on split aces."
                )
                return

            player.double_down()
            card = game.shoe.deal()
            player.hit(card)
            game.add_visible_card(card)
            game.io_interface.output(f"{player.name} doubles down and gets {card}.")
            if player.is_busted():
                game.io_interface.output(f"{player.name} has busted.")
            player.hand_done[player.current_hand_index] = True

        elif action == Action.STAND:
            player.stand()
            player.hand_done[player.current_hand_index] = True
            game.io_interface.output(f"{player.name} stands.")

        elif action == Action.SURRENDER:
            player.surrender()
            game.io_interface.output(f"{player.name} surrenders.")
            player.hand_done[player.current_hand_index] = True


class DealersTurnState(GameState):
    """
    The game state where it's the dealer's turn to play.
    """

    def handle(self, game):
        """Handles the dealer's actions and changes the game state to EndRoundState."""
        # The dealer should always hit according to the rules, even if all players busted
        # The original logic skipped dealer actions when all players busted, which
        # could result in the dealer stopping at values below 17

        # Hit until the dealer should stand according to the rules
        while game.dealer.should_hit(game.rules):
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

                # Check for bonus payout combinations first
                bonus_combination = self.check_for_bonus_combination(hand)
                if (
                    bonus_combination and winner == "player"
                ):  # Only apply bonus for winning hands
                    bonus_multiplier = game.get_bonus_payout(bonus_combination)
                    if bonus_multiplier > 0:
                        bonus_amount = bet_for_hand * bonus_multiplier
                        # Base payout (even money) + bonus amount
                        total_payout = (bet_for_hand * 2) + bonus_amount
                        player.payout(hand_index, total_payout)
                        game.io_interface.output(
                            f"{player.name} gets a bonus payout of {bonus_amount:.2f} for {bonus_combination}!"
                        )
                        continue  # Skip regular payout processing

                # Regular payout processing
                if winner == "player":
                    if player.blackjack and not hand.is_split:
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

    def check_for_bonus_combination(self, hand):
        """
        Check if a hand matches any bonus payout combination.
        Returns the combination string if found, None otherwise.
        """
        # Example: Check for suited 6-7-8
        if len(hand.cards) == 3:
            # Sort cards by rank
            sorted_cards = sorted(hand.cards, key=lambda card: card.rank.rank_value)

            # Check for consecutive ranks (like 6-7-8)
            is_consecutive = all(
                sorted_cards[i + 1].rank.rank_value
                == sorted_cards[i].rank.rank_value + 1
                for i in range(len(sorted_cards) - 1)
            )

            # Check if all cards have the same suit
            same_suit = all(card.suit == sorted_cards[0].suit for card in sorted_cards)

            if is_consecutive and same_suit:
                # Create a key like "suited-6-7-8"
                ranks = "-".join(str(card.rank) for card in sorted_cards)
                return f"suited-{ranks}"

        # Check for three of a kind (e.g., 7-7-7)
        if len(hand.cards) == 3:
            if all(card.rank == hand.cards[0].rank for card in hand.cards):
                return f"{hand.cards[0].rank}-{hand.cards[0].rank}-{hand.cards[0].rank}"

        # Check for 21 with 5 cards or more
        if len(hand.cards) >= 5 and hand.value() == 21:
            return "five-card-21"

        # Add more patterns as needed

        return None
