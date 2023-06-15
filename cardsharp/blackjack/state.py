class GameState:
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
    async def add_player(self, game, player):
        game.players.append(player)
        game.io_interface.output(f"{player.name} has joined the game.")


class PlacingBetsState(GameState):
    def place_bet(self, game, player, amount):
        player.place_bet(amount)
        game.io_interface.output(f"{player.name} has placed a bet of {amount}.")
        if all(player.has_bet() for player in game.players):
            game.set_state(DealingState())


class DealingState(GameState):
    def deal(self, game):
        game.deck.shuffle()
        for _ in range(2):
            for player in game.players + [game.dealer]:
                card = game.deck.deal()
                player.add_card(card)
                game.io_interface.output(f"Dealt {card} to {player.name}.")
        game.set_state(OfferInsuranceState())


class OfferInsuranceState(GameState):
    def offer_insurance(self, game, player):
        if game.dealer.has_ace():
            game.io_interface.output("Dealer has an Ace!")
            player.offer_insurance()
            game.io_interface.output(f"{player.name} has bought insurance.")
        game.set_state(PlayersTurnState())


class PlayersTurnState(GameState):
    def player_action(self, game, player, action):
        if action == "hit":
            card = game.deck.draw()
            player.add_card(card)
            game.io_interface.output(f"{player.name} decides to {action}.")
            game.io_interface.output(f"{player.name} draws {card}.")
            if player.is_busted():
                player.stand()  # if player busts, they're done
                game.io_interface.output(f"{player.name} has busted.")
        elif action == "stand":
            player.stand()
            game.io_interface.output(f"{player.name} decides to {action}.")
        else:
            game.io_interface.output("Invalid action.")


class DealersTurnState(GameState):
    def dealer_action(self, game):
        while game.dealer.should_hit():
            card = game.deck.deal()
            game.dealer.add_card(card)
            game.io_interface.output(f"Dealer hits and gets {card}.")
        game.set_state(EndRoundState())


class EndRoundState(GameState):
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
