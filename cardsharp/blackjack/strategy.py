from abc import ABC, abstractmethod
from cardsharp.blackjack.action import Action
from cardsharp.common.card import Rank


class Strategy(ABC):
    @abstractmethod
    def decide_action(self, player, dealer_up_card=None) -> Action:
        pass


class DealerStrategy(Strategy):
    def decide_action(self, player, dealer_up_card=None) -> Action:
        if player.is_busted():
            return Action.STAND
        if player.current_hand.value() < 17 or (
            player.current_hand.value() == 17 and player.current_hand.is_soft()
        ):
            return Action.HIT
        else:
            return Action.STAND


class BasicStrategy(Strategy):
    def decide_action(self, player, dealer_up_card) -> Action:
        if player.current_hand.is_blackjack():
            return Action.STAND

        # For simplicity, we treat Ace as 1, not 11.
        dealer_up_card_value = (
            1 if dealer_up_card.rank == Rank.ACE else dealer_up_card.rank.rank_value
        )

        if player.current_hand.value() < 12:
            return Action.HIT
        elif player.current_hand.value() == 12:
            if dealer_up_card_value >= 4 and dealer_up_card_value <= 6:
                return Action.STAND
            else:
                return Action.HIT
        elif player.current_hand.value() >= 13 and player.current_hand.value() <= 16:
            if dealer_up_card_value <= 6:
                return Action.STAND
            else:
                return Action.HIT
        else:  # player hand value is 17-20
            return Action.STAND


class CountingStrategy(Strategy):
    def decide_action(self, player, dealer_up_card):
        # Fill in with Counting Strategy logic
        pass
