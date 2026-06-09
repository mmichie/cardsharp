"""Physical-card integrity of simulated rounds.

Regression tests for the mid-round reshuffle bug: Shoe.deal() used to
reshuffle the entire card list (in-play cards included) the moment the
cut-card index was crossed, so a round straddling the cut card could deal
the same physical card twice -- a single-deck round could contain two
copies of the ace of spades. With round-aware dealing this is impossible:
the cut card defers the shuffle to the next begin_round, and emergency
mid-round reshuffles exclude in-play cards.
"""

import random

from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.blackjack import BlackjackGame
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.state import _state_placing_bets
from cardsharp.blackjack.strategy import BasicStrategy
from cardsharp.common.io_interface import DummyIOInterface


def _play_rounds_and_check(num_decks, penetration, num_rounds, seed):
    rules = Rules(
        num_decks=num_decks,
        dealer_hit_soft_17=True,
        allow_double_down=True,
        allow_split=True,
        allow_surrender=True,
        allow_late_surrender=True,
        allow_double_after_split=True,
        dealer_peek=True,
        blackjack_payout=1.5,
        penetration=penetration,
        min_bet=10,
        max_bet=1000,
    )
    io = DummyIOInterface()
    game = BlackjackGame(rules, io)
    player = Player("P", io, BasicStrategy(), initial_money=10_000_000)
    game.add_player(player)
    game.set_state(_state_placing_bets)

    random.seed(seed)
    for round_no in range(num_rounds):
        game.play_round()

        cards_this_round = list(game.dealer.current_hand.cards)
        for hand in player.hands:
            cards_this_round.extend(hand.cards)

        labels = [(c.rank, c.suit) for c in cards_this_round]
        from collections import Counter

        counts = Counter(labels)
        worst = counts.most_common(1)[0]
        assert worst[1] <= num_decks, (
            f"round {round_no}: physical card {worst[0]} appeared "
            f"{worst[1]} times with only {num_decks} deck(s) in the shoe"
        )
        game.reset()


def test_single_deck_round_never_contains_duplicate_cards():
    """1 deck, 75% penetration: ~1 round in 7 straddles the cut card.

    Under the old mid-round reshuffle behavior this fails within a few
    hundred rounds (an in-play card gets shuffled back and re-dealt).
    """
    _play_rounds_and_check(num_decks=1, penetration=0.75, num_rounds=600, seed=123)


def test_double_deck_round_never_exceeds_physical_copies():
    _play_rounds_and_check(num_decks=2, penetration=0.75, num_rounds=400, seed=321)
