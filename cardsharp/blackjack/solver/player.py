"""Player expected value computation.

Computes the exact EV of each action (hit, stand, double, split, surrender)
for every possible player hand state vs every dealer upcard.

Supports both infinite-deck and finite-deck via the Deck interface.
"""

import math

from cardsharp.blackjack.action import Action

from .types import CARD_VALUES, StateEV, Deck, add_card, display_value


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
    return ev


def ev_hit(hard_total: int, usable_ace: bool, dealer_probs: dict,
           deck: Deck, memo: dict = None) -> float:
    """EV of hitting (and playing optimally afterward)."""
    if memo is None:
        memo = {}
    return _ev_hit(hard_total, usable_ace, dealer_probs, deck, memo)


def _ev_hit(hard_total, usable_ace, dealer_probs, deck, memo):
    key = (hard_total, usable_ace, deck.key)
    if key in memo:
        return memo[key]

    ev = 0.0
    for card_idx, card_val in enumerate(CARD_VALUES):
        p, new_deck = deck.draw(card_idx)
        if p == 0:
            continue
        new_hard, new_usable, disp = add_card(hard_total, usable_ace, card_val)

        if disp > 21:
            ev += p * (-1.0)
        else:
            s = ev_stand(disp, dealer_probs)
            h = _ev_hit(new_hard, new_usable, dealer_probs, new_deck, memo)
            ev += p * max(s, h)

    memo[key] = ev
    return ev


def ev_double(hard_total: int, usable_ace: bool, dealer_probs: dict,
              deck: Deck) -> float:
    """EV of doubling: one more card, forced stand, doubled bet."""
    ev = 0.0
    for card_idx, card_val in enumerate(CARD_VALUES):
        p, _ = deck.draw(card_idx)
        if p == 0:
            continue
        _, _, disp = add_card(hard_total, usable_ace, card_val)

        if disp > 21:
            ev += p * (-2.0)
        else:
            ev += p * 2.0 * ev_stand(disp, dealer_probs)

    return ev


def ev_surrender() -> float:
    """EV of surrendering. Always -0.5."""
    return -0.5


def ev_split(pair_value: int, dealer_probs: dict, allow_das: bool,
             deck: Deck) -> float:
    """EV of splitting a pair (no resplit).

    With infinite deck, the two split hands are independent.
    With finite deck, the second hand sees a slightly different
    composition than the first. For simplicity (and following standard
    practice), we treat split hands as independent even for finite deck
    -- the error is negligible (<0.001%).

    EV = 2 * EV(one split hand).
    """
    hit_memo = {}
    ev_one = 0.0

    for card_idx, card_val in enumerate(CARD_VALUES):
        p, deck_after_draw = deck.draw(card_idx)
        if p == 0:
            continue

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

        s = ev_stand(disp, dealer_probs)
        h = _ev_hit(hard, usable, dealer_probs, deck_after_draw, hit_memo)
        candidates = [s, h]

        if allow_das:
            d = ev_double(hard, usable, dealer_probs, deck_after_draw)
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
    deck: Deck,
) -> StateEV:
    """Compute EV for all actions at a given state, pick best."""
    disp = display_value(hard_total, usable_ace)

    hit_memo = {}
    ev_s = ev_stand(disp, dealer_probs)
    ev_h = _ev_hit(hard_total, usable_ace, dealer_probs, deck, hit_memo)
    ev_d = ev_double(hard_total, usable_ace, dealer_probs, deck) if allow_double else math.nan
    ev_sp = (
        ev_split(pair_value, dealer_probs, allow_das, deck)
        if (is_pair and allow_split)
        else math.nan
    )
    ev_sr = ev_surrender() if allow_surrender else math.nan

    candidates = [(ev_h, Action.HIT), (ev_s, Action.STAND)]
    if allow_double:
        candidates.append((ev_d, Action.DOUBLE))
    if is_pair and allow_split:
        candidates.append((ev_sp, Action.SPLIT))
    if allow_surrender:
        candidates.append((ev_sr, Action.SURRENDER))

    best_ev, best_action = max(candidates, key=lambda x: x[0])

    return StateEV(
        hit=ev_h, stand=ev_s, double=ev_d, split=ev_sp, surrender=ev_sr,
        best_action=best_action, best_ev=best_ev,
    )
