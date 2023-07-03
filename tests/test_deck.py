from cardsharp.common.card import Card, Suit, Rank
from cardsharp.common.deck import Deck


def test_deck_initialization():
    deck = Deck()
    assert isinstance(deck.cards, list)
    assert len(deck.cards) == 52


def test_deck_initialization_with_custom_cards():
    cards = [
        Card(Suit.HEARTS, Rank.TWO),
        Card(Suit.DIAMONDS, Rank.ACE),
        Card(Suit.CLUBS, Rank.JACK),
    ]
    deck = Deck(cards)
    assert deck.cards == cards


def test_deck_shuffle():
    deck = Deck()
    original_order = deck.cards.copy()
    deck.shuffle()
    assert deck.cards != original_order
    assert set(deck.cards) == set(original_order)


def test_deck_deal():
    deck = Deck()
    size = deck.size
    card = deck.deal()
    assert isinstance(card, Card)
    assert len(deck.cards) == size - 1


def test_deck_size():
    deck = Deck()
    assert deck.size == 52


def test_deck_repr():
    deck = Deck()
    assert repr(deck) == f"Deck({[repr(card) for card in deck.cards]})"


def test_deck_str():
    deck = Deck()
    assert str(deck) == f"Deck of {len(deck.cards)} cards"
