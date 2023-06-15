from cardsharp.common.hand import Hand
from cardsharp.common.card import Rank


class BlackjackHand(Hand):
    def value(self) -> int:
        values = []
        for card in self.cards:
            if card.rank in [Rank.JACK, Rank.QUEEN, Rank.KING]:
                values.append(10)
            elif card.rank == Rank.ACE:
                values.append(11)
            else:
                values.append(
                    card.rank.rank_value
                )  # use the numeric value defined in the enum

        # Adjust for Aces
        while sum(values) > 21 and 11 in values:
            values.remove(11)
            values.append(1)
        return sum(values)

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
