from collections import Counter

from cardsharp.common.card import Card, Rank, Suit
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


def test_deck_deal_until_empty():
    deck = Deck()
    for _ in range(deck.size):
        card = deck.deal()
        assert isinstance(card, Card)
    assert deck.is_empty()


def test_deck_draw_empty_deck():
    deck = Deck()
    # Draw all cards from the deck
    for _ in range(deck.size):
        deck.deal()
    # Check that trying to draw from an empty deck raises an exception
    try:
        deck.deal()
    except IndexError:
        assert True
    else:
        assert False, "Should not be able to draw from an empty deck"


def test_deck_reset():
    deck = Deck()
    original_cards = Counter(deck.cards)
    deck.shuffle()
    assert Counter(deck.cards) == original_cards
    deck.reset()
    # After resetting, the deck should be shuffled but contain the same cards.
    assert Counter(deck.cards) == original_cards
    assert deck.size == 52


def test_deck_reset_after_draw():
    deck = Deck()
    size = deck.size
    deck.deal()
    assert len(deck.cards) == size - 1
    deck.reset()
    assert len(deck.cards) == size
    assert (
        deck.cards != deck.initialize_default_deck()
    )  # The deck should be shuffled after resetting


def test_deck_reset_empty_deck():
    deck = Deck()
    # Draw all cards from the deck
    for _ in range(deck.size):
        deck.deal()
    assert deck.is_empty()
    deck.reset()
    assert len(deck.cards) == deck.size
    assert (
        deck.cards != deck.initialize_default_deck()
    )  # The deck should be shuffled after resetting
