"""Dealer outcome probability computation.

Computes the exact probability distribution over dealer final totals
(17-21 + bust) for each upcard, by recursive expansion of all possible
draws weighted by card probabilities.
"""

from collections import defaultdict

from .types import CARD_VALUES, INF_DECK_PROBS, add_card, display_value


def compute_dealer_table(hit_soft_17: bool, probs=INF_DECK_PROBS):
    """Compute dealer outcome probabilities for all 10 upcards.

    Returns dict mapping upcard (1-10) to {final_total: probability}.
    Final totals: 17, 18, 19, 20, 21, 22 (22 = bust).
    """
    table = {}
    for upcard in CARD_VALUES:
        # Dealer starts with upcard only (hole card drawn via recursion)
        hard = upcard
        usable = upcard == 1 and hard + 10 <= 21
        memo = {}
        table[upcard] = _recurse(hard, usable, hit_soft_17, probs, memo)
    return table


def compute_conditional_dealer_table(hit_soft_17: bool, probs=INF_DECK_PROBS):
    """Dealer outcome probabilities conditioned on no blackjack.

    For upcards where blackjack is possible (Ace, 10), removes the
    blackjack outcome and renormalizes. For other upcards, identical
    to the unconditional table.
    """
    table = {}
    for upcard in CARD_VALUES:
        if upcard == 1:
            # Ace up: condition on hole card != 10-value
            table[upcard] = _conditional_probs(
                upcard, hit_soft_17, probs, exclude_hole=10
            )
        elif upcard == 10:
            # 10 up: condition on hole card != Ace
            table[upcard] = _conditional_probs(
                upcard, hit_soft_17, probs, exclude_hole=1
            )
        else:
            # No blackjack possible -- use unconditional
            hard = upcard
            usable = False
            memo = {}
            table[upcard] = _recurse(hard, usable, hit_soft_17, probs, memo)
    return table


def dealer_blackjack_prob(upcard: int, probs=INF_DECK_PROBS) -> float:
    """Probability that dealer has blackjack given upcard."""
    if upcard == 1:
        return probs[9]  # P(hole = 10)
    if upcard == 10:
        return probs[0]  # P(hole = Ace)
    return 0.0


def _conditional_probs(upcard, hit_soft_17, probs, exclude_hole):
    """Compute dealer probs conditioned on hole card != exclude_hole.

    Rather than modifying the recursion, enumerate each valid hole card,
    compute the resulting distribution, and weight by conditional probability.
    """
    # Probability of the excluded hole card value
    exclude_idx = CARD_VALUES.index(exclude_hole)
    p_exclude = probs[exclude_idx]
    cond_factor = 1.0 / (1.0 - p_exclude)

    result = defaultdict(float)
    for i, (hole_val, p) in enumerate(zip(CARD_VALUES, probs)):
        if hole_val == exclude_hole:
            continue
        adj_p = p * cond_factor

        # Starting state: upcard + this hole card
        hard = upcard + hole_val
        usable = False
        if upcard == 1 and hard + 10 <= 21:
            usable = True
        elif hole_val == 1 and hard + 10 <= 21:
            usable = True

        disp = hard + 10 if usable else hard

        # If display > 21 with usable ace, demote
        if disp > 21 and usable:
            usable = False
            disp = hard

        memo = {}
        sub = _recurse(hard, usable, hit_soft_17, probs, memo)
        for total, sp in sub.items():
            result[total] += adj_p * sp

    return dict(result)


def _recurse(hard_total, usable_ace, hit_soft_17, probs, memo):
    """Recursive dealer play with memoization.

    Returns {final_total: probability} where 22 means bust.
    """
    key = (hard_total, usable_ace)
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
        # Soft 17 with H17: fall through to draw

    # Must hit: below 17, or soft 17 with H17
    result = defaultdict(float)
    for card_val, p in zip(CARD_VALUES, probs):
        new_hard, new_usable, _ = add_card(hard_total, usable_ace, card_val)
        sub = _recurse(new_hard, new_usable, hit_soft_17, probs, memo)
        for total, sp in sub.items():
            result[total] += p * sp

    result = dict(result)
    memo[key] = result
    return result
