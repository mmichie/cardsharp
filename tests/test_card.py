import pytest
from cardsharp.common.card import Card, Suit, Rank

def test_card_initialization():
    card = Card(Suit.HEARTS, Rank.EIGHT)
    assert card.suit == Suit.HEARTS
    assert card.rank == Rank.EIGHT

def test_card_repr():
    card = Card(Suit.HEARTS, Rank.EIGHT)
    assert repr(card) == "Card(Suit.HEARTS, Rank.EIGHT)"

def test_card_str():
    card = Card(Suit.HEARTS, Rank.EIGHT)
    assert str(card) == "8 of ♥"

def test_card_joker_initialization():
    card = Card(None, Rank.JOKER)
    assert card.suit is None
    assert card.rank == Rank.JOKER

def test_card_joker_repr():
    card = Card(None, Rank.JOKER)
    assert repr(card) == "Card(None, Rank.JOKER)"

def test_card_joker_str():
    card = Card(None, Rank.JOKER)
    assert str(card) == "Joker"

def test_invalid_suit():
    with pytest.raises(ValueError):
        card = Card("Z", Rank.EIGHT)

def test_invalid_rank():
    with pytest.raises(ValueError):
        card = Card(Suit.HEARTS, "invalid")

def test_empty_suit():
    with pytest.raises(ValueError):
        card = Card("", Rank.EIGHT)

def test_empty_rank():
    with pytest.raises(ValueError):
        card = Card(Suit.HEARTS, "")

def test_non_string_rank():
    with pytest.raises(ValueError):
        card = Card(Suit.HEARTS, 123)

def test_all_suits():
    for suit in Suit:
        card = Card(suit, Rank.ACE)
        assert card.suit == suit
        assert card.rank == Rank.ACE

def test_all_ranks():
    for rank in Rank:
        if rank == Rank.JOKER:
            card = Card(None, rank)
            assert card.suit is None
        else:
            card = Card(Suit.HEARTS, rank)
            assert card.suit == Suit.HEARTS
        assert card.rank == rank

