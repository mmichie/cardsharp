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
    def __init__(self):
        pass

    def decide_action(self, player, dealer_up_card) -> Action:
        current_hand = player.current_hand
        if current_hand.is_blackjack():
            return Action.STAND

        # Split
        if current_hand.can_split():
            player_rank = current_hand.cards[0].rank
            dealer_rank = dealer_up_card.rank
            if player_rank in [Rank.ACE, Rank.EIGHT]:
                return Action.SPLIT
            elif (
                player_rank in [Rank.TWO, Rank.THREE, Rank.SEVEN]
                and dealer_rank.rank_value <= 7
            ):
                return Action.SPLIT
            elif player_rank == Rank.SIX and dealer_rank.rank_value <= 6:
                return Action.SPLIT
            elif player_rank in [Rank.FOUR] and dealer_rank.rank_value == 5:
                return Action.SPLIT
            elif player_rank in [Rank.NINE] and dealer_rank.rank_value not in [
                7,
                10,
                11,
            ]:
                return Action.SPLIT

        if current_hand.can_double():
            # Double
            if (
                current_hand.value() in [10, 11] and dealer_up_card.rank.rank_value < 10
            ) or (
                current_hand.is_soft()
                and current_hand.value() in [13, 14, 15, 16, 17]
                and dealer_up_card.rank.rank_value < 7
            ):
                return Action.DOUBLE

        if current_hand.value() <= 11:
            return Action.HIT
        elif current_hand.value() == 12:
            if dealer_up_card.rank.rank_value < 4 or dealer_up_card.rank.rank_value > 6:
                return Action.HIT
            else:
                return Action.STAND
        elif current_hand.value() in range(13, 17):
            if dealer_up_card.rank.rank_value > 6:
                return Action.HIT
            else:
                return Action.STAND
        else:
            return Action.STAND


class CountingStrategy(Strategy):
    def decide_action(self, player, dealer_up_card):
        # Fill in with Counting Strategy logic
        pass
