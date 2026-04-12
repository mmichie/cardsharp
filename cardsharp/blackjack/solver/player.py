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
    """EV of splitting a pair, with optional resplit support.

    max_hands: maximum total hands from splitting (default 4).
    For infinite deck with resplitting, uses algebraic solution:
      E = (S - p_same) / (1 - 2*p_same)
    For finite deck, uses recursive approach with depth tracking.
    """
    return _ev_split_inner(
        pair_value, dealer_probs, allow_das, deck,
        allow_resplit, max_hands, resplit_aces, current_hands=2,
    )


def _ev_one_split_hand(pair_value, card_val, card_idx, deck_after, dealer_probs,
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


def _ev_split_inner(pair_value, dealer_probs, allow_das, deck,
                    allow_resplit, max_hands, resplit_aces, current_hands):
    """Compute EV of splitting, handling resplits."""
    pair_idx = CARD_VALUES.index(pair_value)

    can_resplit = (
        allow_resplit
        and current_hands < max_hands
        and (pair_value != 1 or resplit_aces)
    )

    # Accumulate EV over non-resplit draws
    ev_normal = 0.0
    p_same = 0.0

    for card_idx, card_val in enumerate(CARD_VALUES):
        p, deck_after = deck.draw(card_idx)
        if p == 0:
            continue

        if card_val == pair_value and can_resplit:
            p_same = p
            continue  # handled below

        ev_normal += p * _ev_one_split_hand(
            pair_value, card_val, card_idx, deck_after, dealer_probs, allow_das
        )

    if p_same > 0:
        # Always compute EV of playing the pair as a normal hand
        _, deck_after_same = deck.draw(pair_idx)
        ev_play_pair = _ev_one_split_hand(
            pair_value, pair_value, pair_idx, deck_after_same,
            dealer_probs, allow_das
        )

        if can_resplit:
            if deck._is_infinite:
                # Algebraic: assuming resplit, E = (S - p) / (1 - 2p)
                denom = 1.0 - 2.0 * p_same
                if abs(denom) > 1e-15:
                    ev_one_if_resplit = (ev_normal - p_same) / denom
                    ev_resplit_action = 2.0 * ev_one_if_resplit - 1.0
                else:
                    ev_resplit_action = ev_play_pair

                # Only resplit if it's actually better than playing
                if ev_resplit_action > ev_play_pair:
                    ev_one = ev_one_if_resplit
                else:
                    ev_one = ev_normal + p_same * ev_play_pair
            else:
                # Finite deck: compute resplit EV recursively
                ev_resplit_pair = _ev_split_inner(
                    pair_value, dealer_probs, allow_das, deck_after_same,
                    allow_resplit, max_hands, resplit_aces, current_hands + 1,
                )
                ev_resplit_action = ev_resplit_pair - 1.0

                if ev_resplit_action > ev_play_pair:
                    ev_one = ev_normal + p_same * ev_resplit_action
                else:
                    ev_one = ev_normal + p_same * ev_play_pair
        else:
            ev_one = ev_normal + p_same * ev_play_pair
    else:
        ev_one = ev_normal

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
    allow_resplit: bool = False,
    max_hands: int = 4,
    resplit_aces: bool = False,
) -> StateEV:
    """Compute EV for all actions at a given state, pick best."""
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
