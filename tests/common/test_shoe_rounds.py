"""Round-aware shoe behavior: cut-card timing and mid-round integrity.

A real blackjack game shuffles between rounds: the cut card coming out
mid-round never interrupts the round in progress, and a card on the table
can never simultaneously be in the shoe. The legacy Shoe behavior (kept
for callers that never call begin_round/end_round) shuffles the moment the
cut-card index is crossed -- including the whole card list, so in-play
cards could be dealt twice in the same round. These tests pin the
round-aware contract.
"""

import random

import pytest

from cardsharp.common.card import Card
from cardsharp.common.shoe import Shoe


def deal_n(shoe: Shoe, n: int) -> list[Card]:
    out = []
    for _ in range(n):
        card = shoe.deal()
        assert isinstance(card, Card)
        out.append(card)
    return out


class TestRoundAwareDealing:
    def test_cut_card_does_not_interrupt_round(self):
        """Crossing the cut card mid-round must not reshuffle."""
        random.seed(1)
        shoe = Shoe(num_decks=1, penetration=0.5)  # cut card at 26
        shoe.begin_round()
        dealt = deal_n(shoe, 40)  # crosses the cut card at card 26

        assert shoe.is_cut_card_reached()
        # No shuffle happened: 40 distinct physical cards from one deck.
        seen = {(c.rank, c.suit) for c in dealt}
        assert len(seen) == 40
        assert shoe.next_card_index == 40

    def test_begin_round_shuffles_after_cut_card(self):
        """The shuffle deferred by the round happens at the next begin_round."""
        random.seed(2)
        shoe = Shoe(num_decks=1, penetration=0.5)
        shoe.begin_round()
        deal_n(shoe, 30)
        shoe.end_round()
        assert shoe.is_cut_card_reached()

        shoe.begin_round()
        assert not shoe.is_cut_card_reached()
        assert shoe.next_card_index == 0
        assert shoe.cards_remaining == 52

    def test_no_shuffle_between_rounds_before_cut_card(self):
        """begin_round must NOT shuffle while the cut card is still in."""
        random.seed(3)
        shoe = Shoe(num_decks=1, penetration=0.75)  # cut card at 39
        shoe.begin_round()
        first = deal_n(shoe, 10)
        shoe.end_round()

        shoe.begin_round()
        second = deal_n(shoe, 10)
        shoe.end_round()

        assert not shoe.is_cut_card_reached()
        # Two rounds consumed 20 distinct cards of the same shoe.
        seen = {(c.rank, c.suit) for c in first + second}
        assert len(seen) == 20
        assert shoe.next_card_index == 20

    def test_mid_round_exhaustion_excludes_in_play_cards(self):
        """If the shoe empties mid-round, only discards are reshuffled in.

        Cards dealt earlier in the SAME round stay on the table -- they
        must not reappear from the reshuffled pile.
        """
        random.seed(4)
        shoe = Shoe(num_decks=1, penetration=1.0)
        # Prior rounds consume 45 cards (discards).
        shoe.begin_round()
        deal_n(shoe, 45)
        shoe.end_round()

        # This round needs 12 cards but only 7 remain: the deal must
        # reshuffle the 45 discards mid-round, not the 7 in play.
        shoe.begin_round()
        round_cards = deal_n(shoe, 12)
        seen = {(c.rank, c.suit) for c in round_cards}
        assert len(seen) == 12, "in-play card was dealt twice in one round"

    def test_exhaustion_with_everything_in_play_raises(self):
        """Degenerate case: a single round consuming the whole shoe."""
        random.seed(5)
        shoe = Shoe(num_decks=1, penetration=1.0)
        shoe.begin_round()
        deal_n(shoe, 52)
        with pytest.raises(RuntimeError, match="every card in play"):
            shoe.deal()

    def test_tiny_penetration_gives_fresh_shoe_every_round(self):
        """penetration ~0 -> begin_round reshuffles before every round.

        This is the configuration that makes the simulator directly
        comparable to the solver, which models a fresh shoe per round.
        """
        random.seed(6)
        shoe = Shoe(num_decks=1, penetration=0.01)
        for _ in range(5):
            shoe.begin_round()
            assert shoe.next_card_index == 0
            cards = deal_n(shoe, 20)
            assert len({(c.rank, c.suit) for c in cards}) == 20
            shoe.end_round()

    def test_burn_cards_respected_on_round_shuffle(self):
        """Burned cards are consumed by the begin_round shuffle as usual."""
        random.seed(7)
        shoe = Shoe(num_decks=1, penetration=0.5, burn_cards=2)
        assert shoe.cards_remaining == 50
        shoe.begin_round()
        deal_n(shoe, 30)  # past the cut card
        shoe.end_round()

        shoe.begin_round()
        assert len(shoe.get_burned_cards()) == 2
        assert shoe.cards_remaining == 50

    def test_csm_round_hooks_are_safe(self):
        """CSM mode has no cut card; the hooks must be harmless no-ops."""
        random.seed(8)
        shoe = Shoe(num_decks=6, use_csm=True)
        shoe.begin_round()
        cards = deal_n(shoe, 10)
        assert len(cards) == 10
        shoe.end_round()


class TestLegacyDealing:
    """Callers that never bracket rounds keep the historical behavior."""

    def test_legacy_shuffles_at_cut_card(self):
        random.seed(9)
        shoe = Shoe(num_decks=1, penetration=0.5)
        deal_n(shoe, 26)
        assert shoe.is_cut_card_reached()
        shoe.deal()  # triggers the legacy auto-reshuffle
        assert not shoe.is_cut_card_reached()
        assert shoe.next_card_index == 1
