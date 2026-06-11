"""Interactive session facade for the fast core (beads-i2s.1).

`open_session` builds a `cardsharp_core.Session` from cardsharp `Rules`:
a resumable interactive round driver running the exact batch round
implementation (one rules engine, no drift), with the shoe and per-seat
bankrolls persisting across rounds.

    session = open_session(rules, bankroll=500)
    step = session.begin_round([10])
    while step.phase != "round_over":
        print(step.players[step.seat].hands, step.valid_actions)
        step = session.apply(choose(step))
    print(step.result.players[0].winners, session.money)

Step phases and their answers:

- "insurance": "insure" or "decline" (asked per seat on a dealer ace).
- "early_surrender": any of the step's valid_actions; the engine acts
  on "surrender" and treats anything else as declining (the reference
  engine's semantics).
- "decision": one of the step's valid_actions.
- "round_over": no answer; `step.result` carries the full RoundRecord.

The dealer's hole card never appears in a step until round_over.

The adapter/event layer (beads-i2s.2) builds on these steps; custom
Python strategies drive `apply()` directly at Python speeds.
"""

import random

from cardsharp.fastsim.encoding import (
    CORE_AVAILABLE,
    cardsharp_core,
    make_core_rules,
)


def open_session(
    rules,
    n_players: int = 1,
    bankroll: float = 1000.0,
    seed=None,
    cards=None,
    shuffle_type: str = "perfect",
    shuffle_count=None,
):
    """Open an interactive fast-core session for cardsharp ``rules``.

    With ``cards`` (an iterable of rank codes, Ace=1..King=13), rounds
    replay that exact sequence with no shuffling -- for tests, replays,
    and forensics. Otherwise a real shoe is built from the rules
    (num_decks, penetration, burn_cards, CSM) and seeded; ``seed=None``
    draws a fresh system-random seed.
    """
    if not CORE_AVAILABLE:
        raise RuntimeError(
            "cardsharp_core extension is not installed (uv sync --extra fast)"
        )
    if seed is None:
        seed = random.SystemRandom().randint(0, 2**63 - 1)
    return cardsharp_core.Session(
        make_core_rules(rules),
        n_players=n_players,
        bankroll=bankroll,
        seed=seed % (2**64),
        cards=bytes(cards) if cards is not None else None,
        shuffle_type=shuffle_type,
        shuffle_count=shuffle_count,
    )
