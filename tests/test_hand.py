import pytest
from cardsharp.common.card import Card, Suit, Rank
from cardsharp.common.hand import CardGameHand


def test_hand_initialization():
    hand = CardGameHand()
    assert hand.cards == []

def test_add_card():
    hand = CardGameHand()
    card = Card(Suit.HEARTS, Rank.EIGHT)
    hand.add_card(card)
    assert card in hand.cards

def test_remove_card():
    hand = CardGameHand()
    card = Card(Suit.HEARTS, Rank.EIGHT)
    hand.add_card(card)
    hand.remove_card(card)
    assert card not in hand.cards

def test_hand_repr():
    hand = CardGameHand()
    card = Card(Suit.HEARTS, Rank.EIGHT)
    hand.add_card(card)
    assert repr(hand) == f"CardGameHand([{card!r}])"

def test_hand_str():
    hand = CardGameHand()
    card = Card(Suit.HEARTS, Rank.EIGHT)
    hand.add_card(card)
    assert str(hand) == "8 of ♥"

