#!/usr/bin/env python3
"""
Card Handling Test Script

This script tests the card handling in the HandState class with different card representations.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
import sys

try:
    from cardsharp.state.models import HandState
except ImportError:
    print("ERROR: CardSharp package not found or incompletely installed.")
    print("Please ensure CardSharp is installed properly with: poetry install")
    sys.exit(1)


class TestRank(Enum):
    """Enum for card ranks (for testing)."""

    TWO = auto()
    THREE = auto()
    FOUR = auto()
    FIVE = auto()
    SIX = auto()
    SEVEN = auto()
    EIGHT = auto()
    NINE = auto()
    TEN = auto()
    JACK = auto()
    QUEEN = auto()
    KING = auto()
    ACE = auto()

    @property
    def rank_value(self):
        """Get the numerical value of the rank."""
        if self == TestRank.ACE:
            return 11
        elif self in (TestRank.JACK, TestRank.QUEEN, TestRank.KING):
            return 10
        else:
            return list(TestRank).index(self) + 2


@dataclass
class TestCard:
    """Card class for testing."""

    rank: TestRank
    suit: str

    def __str__(self):
        """String representation of the card."""
        return f"{self.rank.name[0]}{self.suit}"


def test_string_cards():
    """Test handling of string cards."""
    print("\n=== Testing String Cards ===")

    # Test regular hand
    hand = HandState(cards=["2♠", "3♥"])
    print(f"Hand: {hand.cards}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Blackjack: {hand.is_blackjack}")
    print(f"Is Bust: {hand.is_bust}")

    # Test blackjack
    hand = HandState(cards=["A♠", "K♥"])
    print(f"\nHand: {hand.cards}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Blackjack: {hand.is_blackjack}")
    print(f"Is Bust: {hand.is_bust}")

    # Test soft hand
    hand = HandState(cards=["A♠", "6♥"])
    print(f"\nHand: {hand.cards}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Bust: {hand.is_bust}")

    # Test bust
    hand = HandState(cards=["K♠", "Q♥", "2♣"])
    print(f"\nHand: {hand.cards}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Blackjack: {hand.is_blackjack}")
    print(f"Is Bust: {hand.is_bust}")


def test_object_cards():
    """Test handling of card objects."""
    print("\n=== Testing Card Objects ===")

    # Test regular hand
    hand = HandState(cards=[TestCard(TestRank.TWO, "♠"), TestCard(TestRank.THREE, "♥")])
    print(f"Hand: {[str(c) for c in hand.cards]}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Blackjack: {hand.is_blackjack}")
    print(f"Is Bust: {hand.is_bust}")

    # Test blackjack
    hand = HandState(cards=[TestCard(TestRank.ACE, "♠"), TestCard(TestRank.KING, "♥")])
    print(f"\nHand: {[str(c) for c in hand.cards]}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Blackjack: {hand.is_blackjack}")
    print(f"Is Bust: {hand.is_bust}")

    # Test soft hand
    hand = HandState(cards=[TestCard(TestRank.ACE, "♠"), TestCard(TestRank.SIX, "♥")])
    print(f"\nHand: {[str(c) for c in hand.cards]}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Bust: {hand.is_bust}")

    # Test bust
    hand = HandState(
        cards=[
            TestCard(TestRank.KING, "♠"),
            TestCard(TestRank.QUEEN, "♥"),
            TestCard(TestRank.TWO, "♣"),
        ]
    )
    print(f"\nHand: {[str(c) for c in hand.cards]}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Blackjack: {hand.is_blackjack}")
    print(f"Is Bust: {hand.is_bust}")


def test_mixed_cards():
    """Test handling of mixed card types."""
    print("\n=== Testing Mixed Card Types ===")

    # Test mixed types
    hand = HandState(
        cards=["A♠", TestCard(TestRank.KING, "♥")]  # String card  # Object card
    )
    print(f"Hand: {[str(c) if hasattr(c, '__str__') else c for c in hand.cards]}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Blackjack: {hand.is_blackjack}")
    print(f"Is Bust: {hand.is_bust}")

    # Test another mixed hand
    hand = HandState(
        cards=[
            "10♠",  # String card
            "J♦",  # String card
            TestCard(TestRank.TWO, "♥"),  # Object card
        ]
    )
    print(f"\nHand: {[str(c) if hasattr(c, '__str__') else c for c in hand.cards]}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Blackjack: {hand.is_blackjack}")
    print(f"Is Bust: {hand.is_bust}")


def test_simple_string_cards():
    """Test handling of simple string cards (e.g., 'A', 'K')."""
    print("\n=== Testing Simple String Cards ===")

    # Test regular hand
    hand = HandState(cards=["2", "3"])
    print(f"Hand: {hand.cards}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Blackjack: {hand.is_blackjack}")
    print(f"Is Bust: {hand.is_bust}")

    # Test blackjack
    hand = HandState(cards=["A", "K"])
    print(f"\nHand: {hand.cards}")
    print(f"Value: {hand.value}")
    print(f"Is Soft: {hand.is_soft}")
    print(f"Is Blackjack: {hand.is_blackjack}")
    print(f"Is Bust: {hand.is_bust}")


def main():
    """Main function to run all tests."""
    print("Testing HandState with different card representations")

    test_string_cards()
    test_object_cards()
    test_mixed_cards()
    test_simple_string_cards()

    print("\nAll tests completed!")


if __name__ == "__main__":
    main()
