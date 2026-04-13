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
             deck: Deck, allow_resplit: bool = False,
             max_hands: int = 4, resplit_aces: bool = False) -> float:
    """EV of splitting a pair with correlated hand evaluation.

    For finite deck, enumerates cards dealt to BOTH split hands,
    tracking deck depletion between them. This captures the correlation
    that the first hand's draws reduce the deck for the second hand.

    For infinite deck, hands are independent (probabilities don't change),
    so the simpler 2*ev_one formula is used.
    """
    if deck._is_infinite:
        return _ev_split_independent(
            pair_value, dealer_probs, allow_das, deck,
            allow_resplit, max_hands, resplit_aces,
        )
    else:
        return _ev_split_correlated(
            pair_value, dealer_probs, allow_das, deck,
            allow_resplit, max_hands, resplit_aces,
        )


def _ev_one_split_hand(pair_value, card_val, deck_after, dealer_probs,
                       allow_das):
    """EV of playing one split hand after receiving a card."""
    hit_memo = {}
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

    if pair_value == 1:
        return ev_stand(disp, dealer_probs)
    if disp > 21:
        return -1.0

    s = ev_stand(disp, dealer_probs)
    h = _ev_hit(hard, usable, dealer_probs, deck_after, hit_memo)
    candidates = [s, h]
    if allow_das:
        d = ev_double(hard, usable, dealer_probs, deck_after)
        candidates.append(d)
    return max(candidates)


def _ev_split_independent(pair_value, dealer_probs, allow_das, deck,
                          allow_resplit, max_hands, resplit_aces):
    """Split EV for infinite deck (hands independent). 2 * ev_one."""
    ev_one = 0.0
    for card_idx, card_val in enumerate(CARD_VALUES):
        p, deck_after = deck.draw(card_idx)
        if p == 0:
            continue
        ev_one += p * _ev_one_split_hand(
            pair_value, card_val, deck_after, dealer_probs, allow_das
        )
    return 2.0 * ev_one


def _ev_split_correlated(pair_value, dealer_probs, allow_das, deck,
                         allow_resplit, max_hands, resplit_aces):
    """Split EV for finite deck with correlated hand evaluation.

    Enumerates the card dealt to hand 1, then for each, enumerates
    the card dealt to hand 2 from the REDUCED deck. This captures
    the correlation between split hands sharing a finite shoe.
    """
    pair_idx = CARD_VALUES.index(pair_value)
    can_resplit = (
        allow_resplit
        and max_hands > 2
        and (pair_value != 1 or resplit_aces)
    )

    total_ev = 0.0

    for ci1, cv1 in enumerate(CARD_VALUES):
        p1, deck1 = deck.draw(ci1)
        if p1 == 0:
            continue

        # Hand 1 draws cv1. Compute hand 1's best play.
        if cv1 == pair_value and can_resplit:
            # Hand 1 drew same value → option to resplit
            ev_play_h1 = _ev_one_split_hand(
                pair_value, cv1, deck1, dealer_probs, allow_das
            )
            ev_resplit_h1 = _ev_split_correlated(
                pair_value, dealer_probs, allow_das, deck1,
                allow_resplit, max_hands - 1, resplit_aces,
            ) - 1.0  # extra bet
            ev_h1 = max(ev_play_h1, ev_resplit_h1)
        else:
            ev_h1 = _ev_one_split_hand(
                pair_value, cv1, deck1, dealer_probs, allow_das
            )

        # Now enumerate hand 2's draw from the REDUCED deck (deck1)
        for ci2, cv2 in enumerate(CARD_VALUES):
            p2, deck2 = deck1.draw(ci2)
            if p2 == 0:
                continue

            if cv2 == pair_value and can_resplit:
                ev_play_h2 = _ev_one_split_hand(
                    pair_value, cv2, deck2, dealer_probs, allow_das
                )
                ev_resplit_h2 = _ev_split_correlated(
                    pair_value, dealer_probs, allow_das, deck2,
                    allow_resplit, max_hands - 1, resplit_aces,
                ) - 1.0
                ev_h2 = max(ev_play_h2, ev_resplit_h2)
            else:
                ev_h2 = _ev_one_split_hand(
                    pair_value, cv2, deck2, dealer_probs, allow_das
                )

            total_ev += p1 * p2 * (ev_h1 + ev_h2)

    return total_ev


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
    allow_resplit: bool = False,
    max_hands: int = 4,
    resplit_aces: bool = False,
    **_kwargs,
) -> StateEV:
    """Compute EV for all actions at a given state, pick best.

    For finite deck, uses dynamic dealer probs (computed at each
    terminal player state from the exact remaining deck). For infinite
    deck, uses pre-computed dealer probs (no card depletion effect).
    """
    disp = display_value(hard_total, usable_ace)
    hit_memo = {}
    ev_s = ev_stand(disp, dealer_probs)
    ev_h = _ev_hit(hard_total, usable_ace, dealer_probs, deck, hit_memo)
    ev_d = ev_double(hard_total, usable_ace, dealer_probs, deck) if allow_double else math.nan

    ev_sp = (
        ev_split(pair_value, dealer_probs, allow_das, deck,
                 allow_resplit, max_hands, resplit_aces)
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
