"""Dealer outcome probability computation.

Computes the exact probability distribution over dealer final totals
(17-21 + bust) for each upcard, by recursive expansion of all possible
draws weighted by card probabilities.

Supports both infinite-deck (constant probs) and finite-deck
(composition-dependent probs that change as cards are drawn).
"""

from collections import defaultdict

from .types import CARD_VALUES, CARD_IDX, Deck, add_card, display_value


def compute_dealer_table(hit_soft_17: bool, deck: Deck):
    """Compute dealer outcome probabilities for all 10 upcards.

    Returns dict mapping upcard (1-10) to {final_total: probability}.
    Final totals: 17, 18, 19, 20, 21, 22 (22 = bust).
    """
    table = {}
    for upcard in CARD_VALUES:
        # Remove upcard from deck (no-op for infinite)
        remaining = deck.remove_card(upcard)
        hard = upcard
        usable = upcard == 1 and hard + 10 <= 21
        memo = {}
        table[upcard] = _recurse(hard, usable, hit_soft_17, remaining, memo)
    return table


def compute_conditional_dealer_table(hit_soft_17: bool, deck: Deck):
    """Dealer outcome probabilities conditioned on no blackjack.

    For upcards where blackjack is possible (Ace, 10), removes the
    blackjack outcome and renormalizes. For other upcards, identical
    to the unconditional table.
    """
    table = {}
    for upcard in CARD_VALUES:
        remaining = deck.remove_card(upcard)
        if upcard == 1:
            table[upcard] = _conditional_probs(
                upcard, hit_soft_17, remaining, exclude_hole=10
            )
        elif upcard == 10:
            table[upcard] = _conditional_probs(
                upcard, hit_soft_17, remaining, exclude_hole=1
            )
        else:
            hard = upcard
            usable = False
            memo = {}
            table[upcard] = _recurse(hard, usable, hit_soft_17, remaining, memo)
    return table


def compute_dealer_probs_for_deal(
    upcard: int, player_cards: tuple, hit_soft_17: bool, deck: Deck
):
    """Dealer probs for a specific initial deal (finite-deck).

    Removes the player's cards AND the upcard from the shoe before
    computing dealer probabilities. Used for per-deal house edge.
    """
    remaining = deck.remove_card(upcard)
    for cv in player_cards:
        remaining = remaining.remove_card(cv)
    hard = upcard
    usable = upcard == 1 and hard + 10 <= 21
    memo = {}
    return _recurse(hard, usable, hit_soft_17, remaining, memo)


def compute_conditional_dealer_probs_for_deal(
    upcard: int, player_cards: tuple, hit_soft_17: bool, deck: Deck
):
    """Conditional dealer probs for a specific deal (no blackjack)."""
    remaining = deck.remove_card(upcard)
    for cv in player_cards:
        remaining = remaining.remove_card(cv)
    if upcard == 1:
        return _conditional_probs(upcard, hit_soft_17, remaining, exclude_hole=10)
    elif upcard == 10:
        return _conditional_probs(upcard, hit_soft_17, remaining, exclude_hole=1)
    else:
        hard = upcard
        usable = False
        memo = {}
        return _recurse(hard, usable, hit_soft_17, remaining, memo)


def dealer_blackjack_prob(upcard: int, deck: Deck) -> float:
    """Probability that dealer has blackjack given upcard."""
    if upcard == 1:
        _, p_ten = deck.remove_card(upcard).draw(CARD_IDX[10])
        # Wait, draw returns (prob, new_deck). We just need the prob.
        return deck.remove_card(upcard).draw(CARD_IDX[10])[0]
    if upcard == 10:
        return deck.remove_card(upcard).draw(CARD_IDX[1])[0]
    return 0.0


def _conditional_probs(upcard, hit_soft_17, deck, exclude_hole):
    """Compute dealer probs conditioned on hole card != exclude_hole."""
    exclude_idx = CARD_IDX[exclude_hole]
    p_exclude = deck.draw(exclude_idx)[0]

    if p_exclude >= 1.0:
        # All remaining cards are the excluded value (degenerate)
        return {22: 1.0}

    cond_factor = 1.0 / (1.0 - p_exclude)

    result = defaultdict(float)
    for card_idx, hole_val in enumerate(CARD_VALUES):
        if hole_val == exclude_hole:
            continue
        p_hole, deck_after_hole = deck.draw(card_idx)
        if p_hole == 0:
            continue
        adj_p = p_hole * cond_factor

        # Starting state: upcard + this hole card
        hard = upcard + hole_val
        usable = False
        if upcard == 1 and hard + 10 <= 21:
            usable = True
        elif hole_val == 1 and hard + 10 <= 21:
            usable = True

        disp = hard + 10 if usable else hard
        if disp > 21 and usable:
            usable = False

        memo = {}
        sub = _recurse(hard, usable, hit_soft_17, deck_after_hole, memo)
        for total, sp in sub.items():
            result[total] += adj_p * sp

    return dict(result)


def _recurse(hard_total, usable_ace, hit_soft_17, deck, memo):
    """Recursive dealer play with memoization.

    Returns {final_total: probability} where 22 means bust.
    Memo key includes deck state for finite-deck correctness.
    """
    key = (hard_total, usable_ace, deck.key)
    if key in memo:
        return memo[key]

    disp = display_value(hard_total, usable_ace)

    # Bust
    if disp > 21:
        result = {22: 1.0}
        memo[key] = result
        return result

    # Stand conditions
    if disp >= 18:
        result = {disp: 1.0}
        memo[key] = result
        return result

    if disp == 17:
        if not (usable_ace and hit_soft_17):
            result = {17: 1.0}
            memo[key] = result
            return result

    # Must hit
    result = defaultdict(float)
    for card_idx, card_val in enumerate(CARD_VALUES):
        p, new_deck = deck.draw(card_idx)
        if p == 0:
            continue
        new_hard, new_usable, _ = add_card(hard_total, usable_ace, card_val)
        sub = _recurse(new_hard, new_usable, hit_soft_17, new_deck, memo)
        for total, sp in sub.items():
            result[total] += p * sp

    result = dict(result)
    memo[key] = result
    return result
