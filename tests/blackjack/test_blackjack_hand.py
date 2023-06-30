from cardsharp.common.card import Card, Suit, Rank
from cardsharp.blackjack.hand import BlackjackHand


def test_value():
    hand = BlackjackHand()
    cards = [Card(Suit.HEARTS, Rank.TEN), Card(Suit.CLUBS, Rank.ACE)]
    for card in cards:
        hand.add_card(card)
    assert hand.value() == 21


def test_value_with_multiple_aces():
    hand = BlackjackHand()
    cards = [Card(Suit.HEARTS, Rank.ACE), Card(Suit.CLUBS, Rank.ACE)]
    for card in cards:
        hand.add_card(card)
    assert hand.value() == 12


def test_is_soft_true():
    hand = BlackjackHand()
    cards = [Card(Suit.HEARTS, Rank.ACE), Card(Suit.CLUBS, Rank.TWO)]
    for card in cards:
        hand.add_card(card)
    assert hand.is_soft()


def test_hand_with_ace_and_ten_is_soft():
    hand = BlackjackHand()
    cards = [Card(Suit.HEARTS, Rank.ACE), Card(Suit.CLUBS, Rank.TEN)]
    for card in cards:
        hand.add_card(card)
    assert hand.is_soft()


def test_empty_hand_value():
    hand = BlackjackHand()
    assert hand.value() == 0


def test_hand_without_ace_is_not_soft():
    hand = BlackjackHand()
    cards = [Card(Suit.HEARTS, Rank.TEN), Card(Suit.CLUBS, Rank.TWO)]
    for card in cards:
        hand.add_card(card)
    assert not hand.is_soft()


def test_hand_bust():
    hand = BlackjackHand()
    cards = [
        Card(Suit.HEARTS, Rank.TEN),
        Card(Suit.CLUBS, Rank.TEN),
        Card(Suit.DIAMONDS, Rank.TWO),
    ]
    for card in cards:
        hand.add_card(card)
    assert hand.value() > 21


def test_hand_value_exact_21_with_different_combinations():
    hand = BlackjackHand()
    cards = [
        Card(Suit.HEARTS, Rank.NINE),
        Card(Suit.CLUBS, Rank.EIGHT),
        Card(Suit.DIAMONDS, Rank.FOUR),
    ]
    for card in cards:
        hand.add_card(card)
    assert hand.value() == 21


def test_value_with_face_cards():
    hand = BlackjackHand()
    cards = [
        Card(Suit.HEARTS, Rank.KING),
        Card(Suit.CLUBS, Rank.QUEEN),
        Card(Suit.DIAMONDS, Rank.JACK),
    ]
    for card in cards:
        hand.add_card(card)
    assert hand.value() == 30


def test_is_soft_with_multiple_aces():
    hand = BlackjackHand()
    cards = [
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.CLUBS, Rank.ACE),
        Card(Suit.DIAMONDS, Rank.THREE),
    ]
    for card in cards:
        hand.add_card(card)
    assert hand.is_soft()


def test_changing_from_soft_to_hard():
    hand = BlackjackHand()
    hand.add_card(Card(Suit.HEARTS, Rank.ACE))
    hand.add_card(Card(Suit.CLUBS, Rank.TWO))
    assert hand.is_soft()
    hand.add_card(Card(Suit.DIAMONDS, Rank.NINE))
    assert not hand.is_soft()
