from abc import ABC, abstractmethod
from cardsharp.common.card import Card


class AbstractHand(ABC):
    def __init__(self):
        self.cards = []

    def add_card(self, card: Card):
        self.cards.append(card)

    def remove_card(self, card: Card):
        self.cards.remove(card)

    @abstractmethod
    def __repr__(self):
        pass

    @abstractmethod
    def __str__(self):
        pass


class Hand(AbstractHand):
    def __init__(self):
        super().__init__()

    def __repr__(self) -> str:
        return f"Hand({self.cards!r})"

    def __str__(self) -> str:
        return ", ".join(str(card) for card in self.cards)
