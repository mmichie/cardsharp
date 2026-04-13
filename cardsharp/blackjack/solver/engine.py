"""Solver orchestrator: Rules -> house edge + optimal strategy table.

Supports both infinite-deck (fast, constant probabilities) and
finite-deck (exact, composition-dependent probabilities).
"""

import csv
from typing import NamedTuple

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.rules import Rules

from .types import CARD_VALUES, CARD_IDX, StateEV, Deck, hand_state_from_cards
from .dealer import (
    compute_dealer_table,
    compute_conditional_dealer_table,
    compute_dealer_probs_for_deal,
    compute_conditional_dealer_probs_for_deal,
    dealer_blackjack_prob,
)
from .player import compute_state_ev


class SolverResult(NamedTuple):
    """Result of solving a rule set."""

    house_edge: float
    ev_table: dict  # {(card1, card2, upcard): StateEV}
    strategy: dict  # {"Hard16": ["S","S",...], "Soft18": [...], ...}

    def print_strategy(self):
        """Print the optimal strategy in a readable table."""
        print(f"\nHouse edge: {self.house_edge:.4%}\n")
        header = "Hand     " + "  ".join(
            f"{d:>3}" for d in ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
        )
        print(header)
        print("-" * len(header))

        for _, prefix, start, end in [
            ("Hard", "Hard", 4, 22),
            ("Soft", "Soft", 13, 22),
            ("Pair", "Pair", 0, 10),
        ]:
            for i in range(start, end):
                if prefix == "Pair":
                    label = "PairA" if i == 9 else f"Pair{i + 2}"
                else:
                    label = f"{prefix}{i}"
                if label in self.strategy:
                    actions = self.strategy[label]
                    row = f"{label:<9}" + "  ".join(f"{a:>3}" for a in actions)
                    print(row)
            print()

    def to_csv(self, filepath: str):
        """Export strategy in the same format as basic_strategy.csv."""
        rows = []
        header = ["Hand", "2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
        rows.append(header)

        for prefix, start, end in [
            ("Hard", 4, 22),
            ("Soft", 13, 22),
            ("Pair", 0, 10),
        ]:
            for i in range(start, end):
                if prefix == "Pair":
                    label = "PairA" if i == 9 else f"Pair{i + 2}"
                else:
                    label = f"{prefix}{i}"
                if label in self.strategy:
                    rows.append([label] + self.strategy[label])

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(row)

    def diff_strategy(self, csv_path: str) -> list:
        """Compare solver strategy against a CSV file. Returns list of diffs."""
        diffs = []
        with open(csv_path, "r") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                label = row[0].strip()
                if label not in self.strategy:
                    continue
                csv_actions = [a.strip() for a in row[1:]]
                solver_actions = self.strategy[label]
                dealer_labels = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
                for j, (csv_a, solver_a) in enumerate(
                    zip(csv_actions, solver_actions)
                ):
                    if csv_a != solver_a:
                        diffs.append(
                            f"{label} vs {dealer_labels[j]}: "
                            f"CSV={csv_a}, solver={solver_a}"
                        )
        return diffs


def solve(rules: Rules, mode: str = "fast") -> SolverResult:
    """Compute exact house edge and optimal strategy for a rule set.

    mode:
        "fast"  - Static dealer probs, ~1-2s for finite deck. (default)
        "exact" - Dynamic dealer probs recomputed after player draws.
                  Captures player-dealer shoe correlation. ~5-10min.
                  ~0.02% more accurate for finite deck.

    Infinite-deck is always fast (no card depletion effect).
    """
    # Choose deck mode
    use_finite = hasattr(rules, "num_decks") and rules.num_decks <= 8
    if use_finite:
        deck = Deck.finite(rules.num_decks)
    else:
        deck = Deck.infinite()

    hit_soft_17 = rules.dealer_hit_soft_17
    bj_payout = rules.blackjack_payout
    allow_double = rules.allow_double_down
    allow_split = rules.allow_split
    allow_das = rules.allow_double_after_split
    allow_surrender = rules.allow_surrender and (
        rules.allow_late_surrender
        or rules.allow_early_surrender
        or rules.allow_surrender
    )
    peek = rules.dealer_peek
    allow_resplit = rules.allow_resplitting
    max_hands = rules.max_splits + 1
    resplit_aces = rules.resplit_aces

    exact = mode == "exact"
    split_kw = dict(allow_resplit=allow_resplit, max_hands=max_hands,
                    resplit_aces=resplit_aces, exact=exact)

    if use_finite:
        return _solve_finite(
            deck, hit_soft_17, bj_payout, allow_double, allow_split,
            allow_das, allow_surrender, peek, split_kw,
        )
    else:
        return _solve_infinite(
            deck, hit_soft_17, bj_payout, allow_double, allow_split,
            allow_das, allow_surrender, peek, split_kw,
        )


def _solve_infinite(deck, hit_soft_17, bj_payout, allow_double,
                    allow_split, allow_das, allow_surrender, peek, split_kw):
    """Solve with infinite-deck probabilities (fast path)."""
    if peek:
        dealer_table = compute_conditional_dealer_table(hit_soft_17, deck)
    else:
        dealer_table = compute_dealer_table(hit_soft_17, deck)

    ev_table = {}
    for upcard in CARD_VALUES:
        dp = dealer_table[upcard]
        for i, cv1 in enumerate(CARD_VALUES):
            for cv2 in CARD_VALUES[i:]:
                hard, usable, _, is_pair = hand_state_from_cards(cv1, cv2)
                pair_value = cv1 if is_pair else 0
                sev = compute_state_ev(
                    hard, usable, is_pair, pair_value, dp,
                    allow_double, allow_split, allow_das, allow_surrender,
                    deck, **split_kw,
                )
                ev_table[(cv1, cv2, upcard)] = sev

    house_edge = _compute_house_edge(ev_table, deck, bj_payout, peek)
    strategy = _generate_strategy(ev_table, allow_double)

    return SolverResult(house_edge=house_edge, ev_table=ev_table, strategy=strategy)


def _solve_finite(deck, hit_soft_17, bj_payout, allow_double,
                  allow_split, allow_das, allow_surrender, peek, split_kw):
    """Solve with finite-deck composition-dependent probabilities."""
    ev_table = {}

    for upcard in CARD_VALUES:
        for i, cv1 in enumerate(CARD_VALUES):
            for cv2 in CARD_VALUES[i:]:
                hard, usable, _, is_pair = hand_state_from_cards(cv1, cv2)
                pair_value = cv1 if is_pair else 0

                remaining = deck.remove_card(cv1).remove_card(cv2).remove_card(upcard)

                if peek:
                    if upcard == 1:
                        dp = _cond_dealer_for_deal(upcard, remaining, hit_soft_17, 10)
                    elif upcard == 10:
                        dp = _cond_dealer_for_deal(upcard, remaining, hit_soft_17, 1)
                    else:
                        d_hard = upcard
                        d_usable = False
                        memo = {}
                        from .dealer import _recurse
                        dp = _recurse(d_hard, d_usable, hit_soft_17, remaining, memo)
                else:
                    d_hard = upcard
                    d_usable = upcard == 1 and d_hard + 10 <= 21
                    memo = {}
                    from .dealer import _recurse
                    dp = _recurse(d_hard, d_usable, hit_soft_17, remaining, memo)

                sev = compute_state_ev(
                    hard, usable, is_pair, pair_value, dp,
                    allow_double, allow_split, allow_das, allow_surrender,
                    remaining, **split_kw,
                    upcard=upcard, hit_soft_17=hit_soft_17, peek=peek,
                )
                ev_table[(cv1, cv2, upcard)] = sev

    house_edge = _compute_house_edge(ev_table, deck, bj_payout, peek)
    strategy = _generate_strategy(ev_table, allow_double)

    return SolverResult(house_edge=house_edge, ev_table=ev_table, strategy=strategy)


def _cond_dealer_for_deal(upcard, remaining, hit_soft_17, exclude_hole):
    """Compute conditional dealer probs for a specific deal."""
    from .dealer import _conditional_probs
    return _conditional_probs(upcard, hit_soft_17, remaining, exclude_hole)


def _compute_house_edge(ev_table, deck, bj_payout, peek):
    """Compute exact house edge by summing over all initial deals.

    For finite deck, accounts for card removal: P(card2|card1) and
    P(upcard|card1,card2) use conditional probabilities.
    """
    total_ev = 0.0

    for i, cv1 in enumerate(CARD_VALUES):
        p1, _ = deck.draw(i)
        if p1 == 0:
            continue
        deck1 = deck.remove_card(cv1)

        for j, cv2 in enumerate(CARD_VALUES):
            if j < i:
                continue
            p2_cond, _ = deck1.draw(j)
            if p2_cond == 0:
                continue
            p_pair = p1 * p2_cond if i == j else 2 * p1 * p2_cond
            deck12 = deck1.remove_card(cv2)

            _, _, disp, _ = hand_state_from_cards(cv1, cv2)
            is_player_bj = disp == 21 and (cv1 == 1 or cv2 == 1) and cv1 != cv2

            for k, upcard in enumerate(CARD_VALUES):
                p_up_cond, _ = deck12.draw(k)
                if p_up_cond == 0:
                    continue
                p_deal = p_pair * p_up_cond

                # Dealer BJ prob from remaining deck (after 3 cards dealt)
                deck123 = deck12.remove_card(upcard)
                p_dbj = dealer_blackjack_prob(upcard, deck123)

                if peek:
                    ev = _ev_with_peek(
                        cv1, cv2, upcard, is_player_bj, p_dbj,
                        bj_payout, ev_table,
                    )
                else:
                    ev = _ev_no_peek(
                        cv1, cv2, upcard, is_player_bj, p_dbj,
                        bj_payout, ev_table,
                    )

                total_ev += p_deal * ev

    return -total_ev


def _ev_with_peek(cv1, cv2, upcard, is_player_bj, p_dbj, bj_payout, ev_table):
    if is_player_bj:
        return p_dbj * 0.0 + (1 - p_dbj) * bj_payout
    key = (min(cv1, cv2), max(cv1, cv2), upcard)
    optimal_ev = ev_table[key].best_ev
    return p_dbj * (-1.0) + (1 - p_dbj) * optimal_ev


def _ev_no_peek(cv1, cv2, upcard, is_player_bj, p_dbj, bj_payout, ev_table):
    if is_player_bj:
        return p_dbj * 0.0 + (1 - p_dbj) * bj_payout
    key = (min(cv1, cv2), max(cv1, cv2), upcard)
    optimal_ev = ev_table[key].best_ev
    return p_dbj * (-1.0) + (1 - p_dbj) * optimal_ev


def _generate_strategy(ev_table, allow_double):
    """Generate strategy table from EV data."""
    strategy = {}
    dealer_order = [2, 3, 4, 5, 6, 7, 8, 9, 10, 1]

    for total in range(4, 22):
        label = f"Hard{total}"
        actions = []
        for upcard in dealer_order:
            actions.append(_best_action_for_hard(total, upcard, ev_table, allow_double))
        strategy[label] = actions

    for total in range(13, 22):
        label = f"Soft{total}"
        actions = []
        for upcard in dealer_order:
            actions.append(_best_action_for_soft(total, upcard, ev_table, allow_double))
        strategy[label] = actions

    for pair_val in range(2, 11):
        label = f"Pair{pair_val}"
        actions = []
        for upcard in dealer_order:
            key = (pair_val, pair_val, upcard)
            sev = ev_table[key]
            actions.append(_action_code(sev, allow_double))
        strategy[label] = actions

    label = "PairA"
    actions = []
    for upcard in dealer_order:
        key = (1, 1, upcard)
        sev = ev_table[key]
        actions.append(_action_code(sev, allow_double))
    strategy[label] = actions

    return strategy


def _best_action_for_hard(total, upcard, ev_table, allow_double):
    if total >= 17:
        return "S"
    for cv1 in CARD_VALUES:
        cv2 = total - cv1
        if cv2 < 1 or cv2 > 10:
            continue
        if cv1 == 1 or cv2 == 1:
            continue
        if cv1 == cv2:
            continue
        key = (min(cv1, cv2), max(cv1, cv2), upcard)
        if key in ev_table:
            return _action_code(ev_table[key], allow_double)
    for cv1 in CARD_VALUES:
        cv2 = total - cv1
        if 1 <= cv2 <= 10:
            key = (min(cv1, cv2), max(cv1, cv2), upcard)
            if key in ev_table:
                return _action_code(ev_table[key], allow_double)
    return "H"


def _best_action_for_soft(total, upcard, ev_table, allow_double):
    other = total - 11
    if other < 1 or other > 10:
        return "S"
    cv1, cv2 = min(1, other), max(1, other)
    key = (cv1, cv2, upcard)
    if key in ev_table:
        return _action_code(ev_table[key], allow_double)
    return "H"


def _action_code(sev: StateEV, allow_double: bool) -> str:
    action = sev.best_action
    if action == Action.HIT:
        return "H"
    elif action == Action.STAND:
        return "S"
    elif action == Action.DOUBLE:
        if sev.stand >= sev.hit:
            return "DS"
        return "D"
    elif action == Action.SPLIT:
        return "P"
    elif action == Action.SURRENDER:
        return "R"
    return "H"
