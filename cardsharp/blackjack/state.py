import asyncio
from abc import ABC

from cardsharp.blackjack.action import Action


class GameState(ABC):
    def handle(self, game):
        pass

    def add_player(self, game, player):
        pass

    def remove_player(self, game, player):
        pass

    def place_bet(self, game, player, amount):
        pass

    def deal(self, game):
        pass

    def offer_insurance(self, game):
        pass

    def player_action(self, game, player, action):
        pass

    def dealer_action(self, game):
        pass

    def calculate_winner(self, game):
        pass

    def end_round(self, game):
        pass


class WaitingForPlayersState(GameState):
    """
    The game state while the game is waiting for players to join.
    """

    async def handle(self, game):
        """
        Continuously checks if the minimum number of players have joined.
        If so, it changes the game state to PlacingBetsState.
        """
        while len(game.players) < game.minimum_players:
            await asyncio.sleep(1)
        await game.set_state(PlacingBetsState())

    async def add_player(self, game, player):
        """
        Adds a player to the game and notifies the interface.
        """
        game.players.append(player)
        await game.io_interface.output(f"{player.name} has joined the game.")

    def __str__(self):
        return "WaitingForPlayersState"


class PlacingBetsState(GameState):
    """
    The game state where players are placing their bets.
    """

    async def handle(self, game):
        """
        Handles the player bets and changes the game state to DealingState.
        """
        for player in game.players:
            await self.place_bet(game, player, 10)
        await game.set_state(DealingState())

    async def place_bet(self, game, player, amount):
        """
        Handles the bet placement of a player and notifies the interface.
        """
        player.place_bet(amount)
        await game.io_interface.output(f"{player.name} has placed a bet of {amount}.")

    def __str__(self):
        return "PlacingBetsState"


class DealingState(GameState):
    """
    The game state where the dealer is dealing the cards.
    """

    async def handle(self, game):
        """
        Handles the card dealing, checks for blackjack, and changes the game state to OfferInsuranceState.
        """
        game.deck.reset()
        await self.deal(game)
        await self.check_blackjack(game)
        await game.set_state(OfferInsuranceState())

    async def deal(self, game):
        """
        Handles the card dealing and notifies the interface.
        """
        game.deck.shuffle()
        for _ in range(2):
            for player in game.players + [game.dealer]:
                card = game.deck.deal()
                player.add_card(card)
                if player != game.dealer:
                    await game.io_interface.output(f"Dealt {card} to {player.name}.")

    async def check_blackjack(self, game):
        """
        Checks for blackjack for all players and handles the payouts.
        """
        for player in game.players:
            if player.current_hand.value() == 21:
                await game.io_interface.output(f"{player.name} got a blackjack!")
                player.payout(player.bet * 1.5)  # Blackjacks typically pay 3:2
                player.blackjack = True
                player.winner = "player"

        # Check for dealer's blackjack
        if game.dealer.current_hand.value() == 21:
            await game.io_interface.output(f"Dealer got a blackjack!")
            dealer_win = True
            for player in game.players:
                if player.blackjack:  # If the player also has a blackjack, it's a draw
                    game.stats.draws += 1
                    dealer_win = False
                else:  # If the player doesn't have a blackjack, dealer wins
                    player.winner = "dealer"
            if dealer_win:
                game.dealer.winner = "dealer"

    def __str__(self):
        return "DealingState"


class OfferInsuranceState(GameState):
    """
    The game state where insurance is offered if the dealer has an Ace.
    """

    async def handle(self, game):
        """
        Offers insurance to the players if the dealer has an Ace, and changes the game state to PlayersTurnState.
        """
        for player in game.players:
            await self.offer_insurance(game, player)
        await game.io_interface.output(
            "Dealer's face up card is: " + str(game.dealer.current_hand.cards[0])
        )
        await game.set_state(PlayersTurnState())

    async def offer_insurance(self, game, player):
        """
        Offers insurance to a player and handles the insurance purchase.
        """
        if game.dealer.has_ace():
            await game.io_interface.output("Dealer has an Ace!")
            player.buy_insurance(10)
            await game.io_interface.output(f"{player.name} has bought insurance.")

    def __str__(self):
        return "OfferInsuranceState"


class PlayersTurnState(GameState):
    """
    The game state where it's the players' turn to play.
    """

    async def handle(self, game):
        """
        Handles the players' actions and changes the game state to DealersTurnState.
        """
        dealer_up_card = game.dealer.current_hand.cards[0]
        for player in game.players:
            while not player.is_done():
                await game.io_interface.output(f"{player.name}'s turn.")
                action = player.decide_action(dealer_up_card=dealer_up_card)

                if action == Action.HIT:
                    await self.player_action(game, player, action)

                    if player.is_busted():
                        await game.io_interface.output(f"{player.name} has busted.")
                        player.stand()
                        break

                    if player.current_hand.value() == 21:
                        await game.io_interface.output(
                            f"{player.name} has a blackjack."
                        )
                        player.stand()
                        break

                elif action == Action.STAND:
                    await self.player_action(game, player, action)
                    break  # Exit the loop and move to the next player

        await game.set_state(DealersTurnState())

    async def player_action(self, game, player, action):
        """
        Handles a player action and notifies the interface.
        """
        if action == Action.HIT:
            card = game.deck.deal()
            player.add_card(card)
            await game.io_interface.output(f"{player.name} hits and gets {card}.")

        elif action == Action.STAND:
            player.stand()
            await game.io_interface.output(f"{player.name} stands.")

        elif action == Action.DOUBLE:
            player.double_down()
            card = game.deck.deal()
            player.add_card(card)
            await game.io_interface.output(
                f"{player.name} doubles down and gets {card}."
            )
            if player.is_busted():
                await game.io_interface.output(f"{player.name} has busted.")

    def __str__(self):
        return "PlayersTurnState"


class DealersTurnState(GameState):
    """
    The game state where it's the dealer's turn to play.
    """

    async def handle(self, game):
        """
        Handles the dealer's actions and changes the game state to EndRoundState.
        """
        all_players_busted = all(player.is_busted() for player in game.players)

        while not all_players_busted and game.dealer.should_hit():
            await self.dealer_action(game)

        await game.io_interface.output("Dealer stands.")
        await game.set_state(EndRoundState())

    async def dealer_action(self, game):
        """
        Handles a dealer action and notifies the interface.
        """
        card = game.deck.deal()
        game.dealer.add_card(card)
        await game.io_interface.output(f"Dealer hits and gets {card}.")

    def __str__(self):
        return "DealersTurnState"


class EndRoundState(GameState):
    """
    The game state where the round is ending.
    """

    async def handle(self, game):
        """
        Handles the calculation of the winner, updates the statistics, and changes the game state to PlacingBetsState.
        """
        await self.calculate_winner(game)
        await game.stats.update(game)

    async def calculate_winner(self, game):
        """
        Calculates the winner of the round and handles the payouts.
        """
        dealer_hand_value = game.dealer.current_hand.value()
        dealer_cards = ", ".join(str(card) for card in game.dealer.current_hand.cards)
        await game.io_interface.output(f"Dealer's final cards: {dealer_cards}")
        await game.io_interface.output(
            f"Dealer's final hand value: {dealer_hand_value}"
        )

        for player in game.players:
            player_hand_value = player.current_hand.value()
            player_cards = ", ".join(str(card) for card in player.current_hand.cards)
            await game.io_interface.output(
                f"{player.name}'s final cards: {player_cards}"
            )
            await game.io_interface.output(
                f"{player.name}'s final hand value: {player_hand_value}"
            )

            if player_hand_value > 21:
                await game.io_interface.output(f"{player.name} busts. Dealer wins!")
                player.winner = "dealer"
            elif dealer_hand_value > 21 or player_hand_value > dealer_hand_value:
                await game.io_interface.output(f"{player.name} wins the round!")
                player.payout(player.bet * 2)
                player.winner = "player"
            elif player_hand_value < dealer_hand_value:
                await game.io_interface.output(f"Dealer wins against {player.name}!")
                player.winner = "dealer"
            else:
                await game.io_interface.output(
                    f"{player.name} and Dealer tie! It's a push."
                )
                player.payout(player.bet)
                player.winner = "draw"

        await game.set_state(PlacingBetsState())

    def __str__(self):
        return "EndRoundState"
