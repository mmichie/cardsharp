from cardsharp.common.card import Card, Suit, Rank
from cardsharp.common.hand import Hand


def test_hand_initialization():
    hand = Hand()
    assert hand.cards == []


def test_add_card():
    hand = Hand()
    card = Card(Suit.HEARTS, Rank.EIGHT)
    hand.add_card(card)
    assert card in hand.cards


def test_remove_card():
    hand = Hand()
    card = Card(Suit.HEARTS, Rank.EIGHT)
    hand.add_card(card)
    hand.remove_card(card)
    assert card not in hand.cards


def test_hand_repr():
    hand = Hand()
    card = Card(Suit.HEARTS, Rank.EIGHT)
    hand.add_card(card)
    assert repr(hand) == f"Hand([{card!r}])"


def test_hand_str():
    hand = Hand()
    card = Card(Suit.HEARTS, Rank.EIGHT)
    hand.add_card(card)
    assert str(hand) == "8 of ♥"
