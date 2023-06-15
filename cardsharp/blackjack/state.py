import asyncio
from abc import ABC


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
    async def handle(self, game):
        while len(game.players) < game.minimum_players:
            await asyncio.sleep(1)
        game.set_state(PlacingBetsState())

    async def add_player(self, game, player):
        game.players.append(player)
        game.io_interface.output(f"{player.name} has joined the game.")


class PlacingBetsState(GameState):
    def handle(self, game):
        for player in game.players:
            self.place_bet(game, player, 10)
        game.set_state(DealingState())

    def place_bet(self, game, player, amount):
        player.place_bet(amount)
        game.io_interface.output(f"{player.name} has placed a bet of {amount}.")


class DealingState(GameState):
    def handle(self, game):
        self.deal(game)
        game.set_state(OfferInsuranceState())

    def deal(self, game):
        game.deck.shuffle()
        for _ in range(2):
            for player in game.players + [game.dealer]:
                card = game.deck.deal()
                player.add_card(card)
                if player != game.dealer:
                    game.io_interface.output(f"Dealt {card} to {player.name}.")


class OfferInsuranceState(GameState):
    def handle(self, game):
        for player in game.players:
            self.offer_insurance(game, player)
        game.io_interface.output(
            "Dealer's face up card is: " + str(game.dealer.current_hand.cards[0])
        )
        game.set_state(PlayersTurnState())

    def offer_insurance(self, game, player):
        if game.dealer.has_ace():
            game.io_interface.output("Dealer has an Ace!")
            player.buy_insurance(10)
            game.io_interface.output(f"{player.name} has bought insurance.")


class PlayersTurnState(GameState):
    def handle(self, game):
        for player in game.players:
            while not player.is_done() and not player.is_busted():
                game.io_interface.output(f"{player.name}'s turn.")
                action = player.decide_action()
                self.player_action(game, player, action)
                if player.is_busted():
                    game.io_interface.output(f"{player.name} has busted.")
                    player.stand()
                elif (
                    not player.is_done()
                ):  # Add this condition to break the loop if player is done
                    break  # Exit the loop and move to the next player
        game.set_state(DealersTurnState())


class DealersTurnState(GameState):
    def handle(self, game):
        while game.dealer.should_hit():
            self.dealer_action(game)
        game.set_state(EndRoundState())

    def dealer_action(self, game):
        card = game.deck.deal()
        game.dealer.add_card(card)
        game.io_interface.output(f"Dealer hits and gets {card}.")


class EndRoundState(GameState):
    def handle(self, game):
        self.calculate_winner(game)
        game.set_state(PlacingBetsState())

    def calculate_winner(self, game):
        dealer_hand_value = game.dealer.current_hand.value()
        dealer_cards = ", ".join(str(card) for card in game.dealer.current_hand.cards)
        game.io_interface.output(f"Dealer's final cards: {dealer_cards}")
        game.io_interface.output(f"Dealer's final hand value: {dealer_hand_value}")

        for player in game.players:
            player_hand_value = player.current_hand.value()
            player_cards = ", ".join(str(card) for card in player.current_hand.cards)
            game.io_interface.output(f"{player.name}'s final cards: {player_cards}")
            game.io_interface.output(
                f"{player.name}'s final hand value: {player_hand_value}"
            )

            if player_hand_value > 21:
                game.io_interface.output(f"{player.name} busts. Dealer wins!")
            elif dealer_hand_value > 21 or player_hand_value > dealer_hand_value:
                game.io_interface.output(f"{player.name} wins the round!")
                player.payout(
                    player.bet * 2
                )  # If player wins, they get twice their bet
            elif player_hand_value < dealer_hand_value:
                game.io_interface.output(f"Dealer wins against {player.name}!")
            else:  # Ties go to the player in this version
                game.io_interface.output(
                    f"{player.name} and Dealer tie! {player.name} wins on tie."
                )
                player.payout(player.bet * 2)

        game.set_state(PlacingBetsState())
