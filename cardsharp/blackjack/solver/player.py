"""Player expected value computation.

Computes the exact EV of each action (hit, stand, double, split, surrender)
for every possible player hand state vs every dealer upcard.
"""

import math

from cardsharp.blackjack.action import Action

from .types import (
    CARD_VALUES,
    INF_DECK_PROBS,
    StateEV,
    add_card,
    display_value,
)


def ev_stand(player_display: int, dealer_probs: dict) -> float:
    """EV of standing with a given display total against dealer distribution.

    Returns EV in units of 1 bet. Win=+1, Lose=-1, Push=0.
    """
    ev = 0.0
    for total, p in dealer_probs.items():
        if total == 22:  # dealer bust
            ev += p
        elif player_display > total:
            ev += p
        elif player_display < total:
            ev -= p
        # push: +0
    return ev


def ev_hit(
    hard_total: int,
    usable_ace: bool,
    dealer_probs: dict,
    probs=INF_DECK_PROBS,
    memo: dict = None,
) -> float:
    """EV of hitting (and playing optimally afterward).

    Recursive: after drawing, the player chooses max(hit, stand) for each
    resulting state.
    """
    if memo is None:
        memo = {}
    return _ev_hit(hard_total, usable_ace, dealer_probs, probs, memo)


def _ev_hit(hard_total, usable_ace, dealer_probs, probs, memo):
    key = (hard_total, usable_ace)
    if key in memo:
        return memo[key]

    ev = 0.0
    for card_val, p in zip(CARD_VALUES, probs):
        new_hard, new_usable, disp = add_card(hard_total, usable_ace, card_val)

        if disp > 21:
            ev += p * (-1.0)  # bust
        else:
            s = ev_stand(disp, dealer_probs)
            h = _ev_hit(new_hard, new_usable, dealer_probs, probs, memo)
            ev += p * max(s, h)

    memo[key] = ev
    return ev


def ev_double(
    hard_total: int,
    usable_ace: bool,
    dealer_probs: dict,
    probs=INF_DECK_PROBS,
) -> float:
    """EV of doubling: one more card, forced stand, doubled bet.

    Returns EV in units of initial bet (i.e., win/loss is +/-2).
    """
    ev = 0.0
    for card_val, p in zip(CARD_VALUES, probs):
        new_hard, new_usable, disp = add_card(hard_total, usable_ace, card_val)

        if disp > 21:
            ev += p * (-2.0)
        else:
            ev += p * 2.0 * ev_stand(disp, dealer_probs)

    return ev


def ev_surrender() -> float:
    """EV of surrendering. Always -0.5."""
    return -0.5


def ev_split(
    pair_value: int,
    dealer_probs: dict,
    allow_das: bool,
    probs=INF_DECK_PROBS,
) -> float:
    """EV of splitting a pair (infinite deck, no resplit).

    With infinite deck, the two split hands are independent.
    EV = 2 * EV(one split hand).

    Each split hand starts with one card of pair_value, receives one
    more card, then plays with restricted actions (no surrender, no BJ
    payout, DAS controlled by allow_das).
    """
    hit_memo = {}
    ev_one = 0.0

    for card_val, p in zip(CARD_VALUES, probs):
        # Build the split hand: pair_value + drawn card
        hard = pair_value + card_val
        usable = False
        if pair_value == 1 and hard + 10 <= 21:
            usable = True
        elif card_val == 1 and hard + 10 <= 21:
            usable = True

        disp = hard + 10 if usable else hard
        if disp > 21 and usable:
            usable = False
            disp = hard

        # Split aces: forced to stand after one card
        if pair_value == 1:
            ev_one += p * ev_stand(disp, dealer_probs)
            continue

        if disp > 21:
            ev_one += p * (-1.0)
            continue

        # Non-ace split: choose best of stand, hit, (double if DAS)
        s = ev_stand(disp, dealer_probs)
        h = _ev_hit(hard, usable, dealer_probs, probs, hit_memo)
        candidates = [s, h]

        if allow_das:
            d = ev_double(hard, usable, dealer_probs, probs)
            candidates.append(d)

        ev_one += p * max(candidates)

    return 2.0 * ev_one


def compute_state_ev(
    hard_total: int,
    usable_ace: bool,
    is_pair: bool,
    pair_value: int,
    dealer_probs: dict,
    allow_double: bool,
    allow_split: bool,
    allow_das: bool,
    allow_surrender: bool,
    probs=INF_DECK_PROBS,
) -> StateEV:
    """Compute EV for all actions at a given state, pick best."""
    disp = display_value(hard_total, usable_ace)

    hit_memo = {}
    ev_s = ev_stand(disp, dealer_probs)
    ev_h = _ev_hit(hard_total, usable_ace, dealer_probs, probs, hit_memo)
    ev_d = ev_double(hard_total, usable_ace, dealer_probs, probs) if allow_double else math.nan
    ev_sp = (
        ev_split(pair_value, dealer_probs, allow_das, probs)
        if (is_pair and allow_split)
        else math.nan
    )
    ev_sr = ev_surrender() if allow_surrender else math.nan

    # Find best action
    candidates = [(ev_h, Action.HIT), (ev_s, Action.STAND)]
    if allow_double:
        candidates.append((ev_d, Action.DOUBLE))
    if is_pair and allow_split:
        candidates.append((ev_sp, Action.SPLIT))
    if allow_surrender:
        candidates.append((ev_sr, Action.SURRENDER))

    best_ev, best_action = max(candidates, key=lambda x: x[0])

    return StateEV(
        hit=ev_h,
        stand=ev_s,
        double=ev_d,
        split=ev_sp,
        surrender=ev_sr,
        best_action=best_action,
        best_ev=best_ev,
    )
