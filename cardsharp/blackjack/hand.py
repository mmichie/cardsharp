from cardsharp.common.hand import Hand
from cardsharp.common.card import Rank


class BlackjackHand(Hand):
    def value(self) -> int:
        total_value = sum(
            card.rank.rank_value for card in self.cards if card.rank != Rank.ACE
        )
        num_aces = sum(card.rank == Rank.ACE for card in self.cards)

        for _ in range(num_aces):
            if total_value + Rank.ACE.rank_value <= 21:
                total_value += Rank.ACE.rank_value
            else:
                total_value += Rank.ACE.rank_value - 10

        return total_value

    def is_soft(self) -> bool:
        """
        Returns True if the hand is soft, which means it contains an Ace
        that can be counted as 11 without busting.
        """
        values_without_ace = [
            10
            if card.rank in [Rank.JACK, Rank.QUEEN, Rank.KING]
            else card.rank.rank_value
            for card in self.cards
            if card.rank != Rank.ACE
        ]
        return (
            Rank.ACE in (card.rank for card in self.cards)
            and sum(values_without_ace) <= 10
        )
