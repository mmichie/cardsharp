"""Test shoe penetration and burn cards functionality."""

import pytest
from cardsharp.common.shoe import Shoe
from cardsharp.common.card import Card, Rank, Suit


class TestShoePenetration:
    """Test penetration and cut card functionality."""
    
    def test_penetration_basic(self):
        """Test basic penetration functionality."""
        shoe = Shoe(num_decks=1, penetration=0.5)
        
        # Initially cut card should not be reached
        assert not shoe.is_cut_card_reached()
        
        # Deal cards just to the penetration point (26 cards = 50%)
        cards_to_deal = int(52 * 0.5)
        for _ in range(cards_to_deal):
            shoe.deal()
        
        # Now cut card should be reached
        assert shoe.is_cut_card_reached()
        
    def test_penetration_percentage(self):
        """Test penetration percentage calculation."""
        shoe = Shoe(num_decks=2, penetration=0.75)
        
        # Initially at 0%
        assert shoe.get_penetration_percentage() == 0.0
        
        # Deal 26 cards (25% of 104 cards)
        for _ in range(26):
            shoe.deal()
        
        assert abs(shoe.get_penetration_percentage() - 0.25) < 0.01
        
    def test_burn_cards(self):
        """Test burn cards functionality."""
        shoe = Shoe(num_decks=1, penetration=0.75, burn_cards=3)
        
        # Check that cards were burned
        burned = shoe.get_burned_cards()
        assert len(burned) == 3
        assert all(isinstance(card, Card) for card in burned)
        
        # Cards remaining should be 52 - 3 = 49
        assert shoe.cards_remaining == 49
        
    def test_burn_cards_after_reshuffle(self):
        """Test that cards are burned after reshuffle."""
        shoe = Shoe(num_decks=1, penetration=0.5, burn_cards=2)
        
        # Get initial burned cards
        initial_burned = shoe.get_burned_cards()
        assert len(initial_burned) == 2
        
        # Deal past penetration to trigger reshuffle
        cards_to_deal = int(52 * 0.5) + 1
        for _ in range(cards_to_deal):
            shoe.deal()
        
        # After reshuffle, new cards should be burned
        new_burned = shoe.get_burned_cards()
        assert len(new_burned) == 2
        # They should be different cards (very high probability)
        
    def test_no_burn_with_csm(self):
        """Test that CSM doesn't burn cards."""
        shoe = Shoe(num_decks=6, use_csm=True, burn_cards=5)
        
        # CSM should not burn cards
        burned = shoe.get_burned_cards()
        assert len(burned) == 0
        
    def test_cut_card_resets_after_shuffle(self):
        """Test that cut card status resets after shuffle."""
        shoe = Shoe(num_decks=1, penetration=0.5)
        
        # Deal to penetration point
        cards_to_deal = int(52 * 0.5)
        for _ in range(cards_to_deal):
            shoe.deal()
        
        assert shoe.is_cut_card_reached()
        
        # Deal one more card (which triggers reshuffle), cut card should reset
        shoe.deal()
        assert not shoe.is_cut_card_reached()
        
    def test_penetration_with_multiple_decks(self):
        """Test penetration with multiple decks."""
        shoe = Shoe(num_decks=6, penetration=0.80)
        total_cards = 52 * 6
        
        # Deal to just before 80% penetration  
        cards_to_deal = int(total_cards * 0.80) - 1
        for _ in range(cards_to_deal):
            shoe.deal()
        
        assert not shoe.is_cut_card_reached()
        
        # Deal one more to reach exactly 80%
        shoe.deal()
            
        assert shoe.is_cut_card_reached()
        
    def test_extreme_burn_cards(self):
        """Test burning many cards doesn't break the shoe."""
        # Try to burn more cards than reasonable
        shoe = Shoe(num_decks=1, burn_cards=10)
        
        # Should only burn 10 cards even though it's a lot for 1 deck
        burned = shoe.get_burned_cards()
        assert len(burned) == 10
        assert shoe.cards_remaining == 42