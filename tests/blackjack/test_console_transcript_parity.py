"""Console transcript parity: session-backed console vs the old state
machine (beads-i2s.2).

Both drivers play identical injected card streams with identical scripted
actions; their narration must match line for line after two documented
normalizations:

- Suits are stripped from the old output ("T of Spades" -> "T"): the
  core deals ranks, and suits were cosmetic randomness.
- "{name} got a blackjack!" lines are dropped from both sides before
  comparison: the old state machine printed that line for EVERY player
  whenever the dealer peeked (an indentation bug at state.py's peek
  branch). A separate assertion checks the new console emits it exactly
  when a natural actually happened.

The old console also CRASHES when the dealer shows an ace (insurance
needs a strategy object; console players have none). That bug is pinned
here as documentation, and the new console's real insurance prompt gets
its own coverage.
"""

import logging
import os
import re

import pytest

pytest.importorskip(
    "cardsharp_core",
    reason="cardsharp-core extension not built (uv sync --extra fast)",
)

os.environ["BLACKJACK_DISABLE_LOGGING"] = "1"

from cardsharp.blackjack.action import Action  # noqa: E402
from cardsharp.blackjack.actor import Player  # noqa: E402
from cardsharp.blackjack.blackjack import BlackjackGame  # noqa: E402
from cardsharp.blackjack.console import ConsoleSession  # noqa: E402
from cardsharp.blackjack.decision_logger import decision_logger  # noqa: E402
from cardsharp.blackjack.rules import Rules  # noqa: E402
from cardsharp.common.card import Card, Rank, Suit  # noqa: E402
from cardsharp.common.io_interface import TestIOInterface  # noqa: E402
from cardsharp.common.shoe import Shoe  # noqa: E402

decision_logger.set_level(logging.ERROR)

_SUIT_RE = re.compile(r" of (?:Spades|Hearts|Diamonds|Clubs|♠|♥|♦|♣)")
_BLACKJACK_LINE = "got a blackjack!"


def make_rules(**overrides):
    kwargs = dict(
        num_decks=6,
        dealer_peek=True,
        allow_double_after_split=True,
        allow_split=True,
        allow_insurance=True,
        allow_surrender=True,
        min_bet=10,
        max_bet=1000,
        penetration=0.75,
        dealer_hit_soft_17=True,
        max_splits=3,
    )
    kwargs.update(overrides)
    return Rules(**kwargs)


def old_transcript(codes, actions, num_rounds=1, bankroll=1000, **overrides):
    """The retired state-machine console on an injected shoe."""
    rules = make_rules(**overrides)
    io = TestIOInterface()
    for name in actions:
        io.add_player_action(Action(name))
    shoe = Shoe(num_decks=rules.num_decks, penetration=1.0)
    shoe.cards = [Card(Suit.SPADES, Rank(c)) for c in codes]
    shoe.next_card_index = 0
    shoe.total_cards = len(shoe.cards)
    shoe.reshuffle_point = len(shoe.cards) + 10_000
    for _ in range(num_rounds):
        game = BlackjackGame(rules, io, shoe)
        player = Player("Player1", io, None, initial_money=bankroll)
        game.add_player(player)
        game.play_round()
        shoe = game.shoe
    return io.sent_messages


def new_transcript(
    codes,
    actions,
    num_rounds=1,
    bankroll=1000,
    insurance_answers=(),
    **overrides,
):
    """The session-backed console on the same injected stream."""
    rules = make_rules(**overrides)
    io = TestIOInterface()
    for name in actions:
        io.add_player_action(Action(name))
    io.input_responses = list(insurance_answers)
    table = ConsoleSession(rules, io, bankroll=bankroll, cards=codes)
    try:
        for _ in range(num_rounds):
            assert table.play_round()
    finally:
        table.close()
    return io.sent_messages, table


def normalize(lines):
    return [_SUIT_RE.sub("", line) for line in lines if _BLACKJACK_LINE not in line]


def assert_transcripts_match(codes, actions, num_rounds=1, **overrides):
    old = old_transcript(codes, actions, num_rounds, **overrides)
    new, _ = new_transcript(codes, actions, num_rounds, **overrides)
    assert normalize(new) == normalize(old), (
        "transcripts diverged\n--- old ---\n"
        + "\n".join(normalize(old))
        + "\n--- new ---\n"
        + "\n".join(normalize(new))
    )
    return new


SCENARIOS = [
    pytest.param([10, 8, 9, 7, 10], ["stand"], 1, {}, id="stand-dealer-busts"),
    pytest.param([10, 7, 6, 9, 10, 5, 5], ["hit"], 1, {}, id="hit-bust"),
    pytest.param([10, 10, 9, 9, 5], ["stand"], 1, {}, id="stand-push"),
    pytest.param([6, 6, 5, 10, 9, 4, 8], ["double"], 1, {}, id="double-push"),
    pytest.param([10, 10, 6, 9, 5, 5], ["surrender"], 1, {}, id="surrender"),
    pytest.param([1, 9, 13, 5, 10, 10], [], 1, {}, id="player-natural"),
    pytest.param([10, 10, 9, 1, 5], [], 1, {}, id="dealer-blackjack-ten-up"),
    pytest.param(
        [8, 6, 8, 10, 10, 5, 9, 8, 8],
        ["split", "stand", "stand"],
        1,
        {},
        id="split-two-hands",
    ),
    pytest.param(
        [8, 6, 8, 10, 8, 10, 9, 3, 10, 10],
        ["split", "split", "stand", "stand", "stand"],
        1,
        {"allow_resplitting": True},
        id="resplit-three-hands",
    ),
    pytest.param(
        [10, 8, 9, 7, 10, 9, 10, 10, 6, 2],
        ["stand", "stand"],
        2,
        {},
        id="two-rounds-shoe-continuity",
    ),
    pytest.param(
        [2, 10, 3, 9, 10, 6, 13, 5, 5],
        ["hit", "hit", "stand"],
        1,
        {},
        id="multi-hit-stand",
    ),
]


@pytest.mark.parametrize("codes,actions,num_rounds,overrides", SCENARIOS)
def test_transcript_parity(codes, actions, num_rounds, overrides):
    assert_transcripts_match(codes, actions, num_rounds, **overrides)


def test_natural_line_emitted_only_for_actual_naturals():
    new, _ = new_transcript([1, 9, 13, 5, 10, 10], [])
    assert sum(_BLACKJACK_LINE in line for line in new) == 1
    new, _ = new_transcript([10, 8, 9, 7, 10], ["stand"])
    assert sum(_BLACKJACK_LINE in line for line in new) == 0


def test_old_console_crashes_on_dealer_ace_insurance():
    """The bug the migration fixes: the old console requires a strategy
    object to answer insurance and dies on any dealer ace. Pinned so its
    eventual disappearance (engine retirement) is a conscious event."""
    with pytest.raises(AttributeError):
        old_transcript([10, 1, 9, 10, 5], ["stand"])


def test_new_console_offers_insurance_and_settles_it():
    # Dealer A,T blackjack. Insured: hand loses 10, insurance pays 10.
    codes = [10, 1, 9, 10]
    new, table = new_transcript(codes, [], insurance_answers=["yes"])
    assert "Player1 has bought insurance." in new
    assert "Dealer has blackjack!" in new
    assert "Player1 wins insurance bet of $15.00." in new
    assert "Player1 loses to dealer's blackjack." in new
    assert table.money == 1000.0  # -10 hand, +10 insurance profit

    # Declined: lose the hand outright.
    new, table = new_transcript(codes, [], insurance_answers=["no"])
    assert "Player1 declines insurance." in new
    assert "Player1 did not take insurance." in new
    assert table.money == 990.0


def test_new_console_insurance_with_no_dealer_blackjack():
    # Dealer A,6: insurance loses quietly; play continues. P 10,9 stands.
    codes = [10, 1, 9, 6, 10]
    new, table = new_transcript(codes, ["stand"], insurance_answers=["yes"])
    assert "Player1 has bought insurance." in new
    assert "Player1's turn." in new
    # Dealer A,6 = soft 17, hits (H17) and gets T: 17 -> busts? A,6,T = 17.
    # A=11 -> 17 soft; hit T -> 17 hard. Stands at 17 hard.
    assert "Dealer's final hand value: 17" in new
    # Hand: 19 beats 17 (+10); insurance bet 5 lost.
    assert table.money == 1005.0


def test_bankroll_persists_across_console_rounds():
    # Two stand rounds, player wins both: money should accumulate (the
    # old console reset the bankroll every round by recreating Player).
    codes = [10, 8, 9, 7, 10, 9, 10, 10, 6, 2]
    _, table = new_transcript(codes, ["stand", "stand"], num_rounds=2)
    assert table.money == 1020.0
