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
        Card("Z", Rank.EIGHT)


def test_invalid_rank():
    with pytest.raises(ValueError):
        Card(Suit.HEARTS, "invalid")


def test_empty_suit():
    with pytest.raises(ValueError):
        Card("", Rank.EIGHT)


def test_empty_rank():
    with pytest.raises(ValueError):
        Card(Suit.HEARTS, "")


def test_non_string_rank():
    with pytest.raises(ValueError):
        Card(Suit.HEARTS, 123)


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


def test_card_equality():
    card1 = Card(Suit.HEARTS, Rank.EIGHT)
    card2 = Card(Suit.HEARTS, Rank.EIGHT)
    card3 = Card(Suit.CLUBS, Rank.EIGHT)
    card4 = Card(Suit.HEARTS, Rank.NINE)

    assert card1 == card2  # Two cards with same suit and rank should be equal
    assert (
        card1 != card3
    )  # Two cards with different suits but same rank should not be equal
    assert (
        card1 != card4
    )  # Two cards with same suit but different ranks should not be equal
