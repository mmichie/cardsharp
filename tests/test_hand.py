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


def test_add_multiple_cards():
    hand = Hand()
    cards = [Card(Suit.HEARTS, Rank.EIGHT), Card(Suit.CLUBS, Rank.ACE)]
    for card in cards:
        hand.add_card(card)
    assert all(card in hand.cards for card in cards)


def test_remove_card_not_in_hand():
    hand = Hand()
    card = Card(Suit.HEARTS, Rank.EIGHT)
    try:
        hand.remove_card(card)
    except ValueError:
        pass  # Expected behavior
    else:
        assert False, "Expected ValueError when removing card not in hand"


def test_order_of_cards():
    hand = Hand()
    cards = [Card(Suit.HEARTS, Rank.EIGHT), Card(Suit.CLUBS, Rank.ACE)]
    for card in cards:
        hand.add_card(card)
    assert hand.cards == cards


def test_empty_hand_repr():
    hand = Hand()
    assert repr(hand) == "Hand([])"


def test_empty_hand_str():
    hand = Hand()
    assert str(hand) == ""
