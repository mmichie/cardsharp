from abc import ABC, abstractmethod
from cardsharp.blackjack.action import Action


class Strategy(ABC):
    @abstractmethod
    def decide_action(self, player) -> Action:
        pass


class DealerStrategy(Strategy):
    def decide_action(self, player) -> Action:
        if player.is_busted():
            return Action.STAND
        if player.current_hand.value() < 17 or (
            player.current_hand.value() == 17 and player.current_hand.is_soft()
        ):
            return Action.HIT
        else:
            return Action.STAND


class BasicStrategy(Strategy):
    def decide_action(self, player):
        # Fill in with Basic Strategy logic
        pass


class CountingStrategy(Strategy):
    def decide_action(self, player):
        # Fill in with Counting Strategy logic
        pass
