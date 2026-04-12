"""Solver orchestrator: Rules -> house edge + optimal strategy table.

This is the main entry point. It consumes a Rules object and produces
exact house edge, per-state EVs, and an optimal strategy table.
"""

import csv
import io
from typing import NamedTuple

from cardsharp.blackjack.action import Action
from cardsharp.blackjack.rules import Rules

from .types import (
    CARD_VALUES,
    INF_DECK_PROBS,
    StateEV,
    hand_state_from_cards,
)
from .dealer import (
    compute_dealer_table,
    compute_conditional_dealer_table,
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

        for section, prefix, start, end in [
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
            header = next(reader)
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


def solve(rules: Rules) -> SolverResult:
    """Compute exact house edge and optimal strategy for a rule set.

    Currently supports infinite-deck (CSM) mode only.
    """
    probs = INF_DECK_PROBS
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

    # Step 1: Dealer probability tables
    if peek:
        dealer_table = compute_conditional_dealer_table(hit_soft_17, probs)
    else:
        dealer_table = compute_dealer_table(hit_soft_17, probs)

    # Step 2: Compute EV for every initial player state vs every upcard
    ev_table = {}
    for upcard in CARD_VALUES:
        dp = dealer_table[upcard]
        for i, cv1 in enumerate(CARD_VALUES):
            for cv2 in CARD_VALUES[i:]:
                hard, usable, disp, is_pair = hand_state_from_cards(cv1, cv2)
                pair_value = cv1 if is_pair else 0

                sev = compute_state_ev(
                    hard_total=hard,
                    usable_ace=usable,
                    is_pair=is_pair,
                    pair_value=pair_value,
                    dealer_probs=dp,
                    allow_double=allow_double,
                    allow_split=allow_split,
                    allow_das=allow_das,
                    allow_surrender=allow_surrender,
                    probs=probs,
                )
                ev_table[(cv1, cv2, upcard)] = sev

    # Step 3: Compute house edge
    house_edge = _compute_house_edge(
        ev_table, probs, bj_payout, peek, dealer_table
    )

    # Step 4: Generate strategy table
    strategy = _generate_strategy(ev_table, probs, allow_double)

    return SolverResult(
        house_edge=house_edge,
        ev_table=ev_table,
        strategy=strategy,
    )


def _compute_house_edge(ev_table, probs, bj_payout, peek, dealer_table):
    """Compute exact house edge by summing over all initial deals."""
    total_ev = 0.0

    for i, (cv1, p1) in enumerate(zip(CARD_VALUES, probs)):
        for j, (cv2, p2) in enumerate(zip(CARD_VALUES, probs)):
            if j < i:
                continue
            # Probability of this player hand
            p_pair = p1 * p2 if i == j else 2 * p1 * p2

            _, _, disp, _ = hand_state_from_cards(cv1, cv2)
            is_player_bj = disp == 21 and (cv1 == 1 or cv2 == 1) and len({cv1, cv2}) == 2

            for k, (upcard, p_up) in enumerate(zip(CARD_VALUES, probs)):
                p_deal = p_pair * p_up
                p_dbj = dealer_blackjack_prob(upcard, probs)

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
    """EV of a deal with peek (US rules)."""
    if is_player_bj:
        # Player BJ vs dealer BJ = push; vs no BJ = win bj_payout
        return p_dbj * 0.0 + (1 - p_dbj) * bj_payout

    # Player no BJ vs dealer BJ = lose; vs no BJ = play optimally
    key = (min(cv1, cv2), max(cv1, cv2), upcard)
    optimal_ev = ev_table[key].best_ev
    return p_dbj * (-1.0) + (1 - p_dbj) * optimal_ev


def _ev_no_peek(cv1, cv2, upcard, is_player_bj, p_dbj, bj_payout, ev_table):
    """EV of a deal without peek (European rules).

    Player plays first without knowing if dealer has BJ.
    OBO not modeled in MVP -- player loses full bet to dealer BJ.
    """
    if is_player_bj:
        # Player BJ: if dealer also BJ = push, else win
        return p_dbj * 0.0 + (1 - p_dbj) * bj_payout

    # Player plays optimally, then dealer reveals
    key = (min(cv1, cv2), max(cv1, cv2), upcard)
    optimal_ev = ev_table[key].best_ev

    # If dealer has BJ, player loses regardless of their play
    # (simplified: no OBO in MVP)
    return p_dbj * (-1.0) + (1 - p_dbj) * optimal_ev


def _generate_strategy(ev_table, probs, allow_double):
    """Generate strategy table from EV data.

    Returns dict mapping hand labels to lists of action codes.
    """
    strategy = {}
    dealer_order = [2, 3, 4, 5, 6, 7, 8, 9, 10, 1]  # columns: 2-10, A

    # Hard totals: 4-21
    for total in range(4, 22):
        label = f"Hard{total}"
        actions = []
        for upcard in dealer_order:
            action = _best_action_for_hard(total, upcard, ev_table, probs, allow_double)
            actions.append(action)
        strategy[label] = actions

    # Soft totals: 13-21
    for total in range(13, 22):
        label = f"Soft{total}"
        actions = []
        for upcard in dealer_order:
            action = _best_action_for_soft(total, upcard, ev_table, probs, allow_double)
            actions.append(action)
        strategy[label] = actions

    # Pairs: 2-10, A
    for pair_val in range(2, 11):
        label = f"Pair{pair_val}" if pair_val <= 10 else "PairA"
        actions = []
        for upcard in dealer_order:
            cv = pair_val
            key = (min(cv, cv), max(cv, cv), upcard)
            sev = ev_table[key]
            actions.append(_action_code(sev, allow_double))
        strategy[label] = actions

    # Pair A
    label = "PairA"
    actions = []
    for upcard in dealer_order:
        key = (1, 1, upcard)
        sev = ev_table[key]
        actions.append(_action_code(sev, allow_double))
    strategy[label] = actions

    return strategy


def _best_action_for_hard(total, upcard, ev_table, probs, allow_double):
    """Find the best action code for a hard total.

    A hard total can come from multiple card combinations. We use the
    canonical pair that produces this hard total (doesn't matter for
    infinite deck since EV only depends on total, not specific cards).
    """
    # Trivial: always stand on 17+ (hitting can only hurt or bust)
    if total >= 17:
        return "S"

    # Pick a canonical non-pair, non-Ace card pair for this hard total
    for cv1 in CARD_VALUES:
        cv2 = total - cv1
        if cv2 < 1 or cv2 > 10:
            continue
        if cv1 == 1 or cv2 == 1:
            continue  # Ace makes it soft, not hard
        if cv1 == cv2:
            continue  # Pairs have their own row
        key = (min(cv1, cv2), max(cv1, cv2), upcard)
        if key in ev_table:
            return _action_code(ev_table[key], allow_double)

    # Fallback for hard totals only reachable as pairs (e.g., hard 4 = 2+2)
    for cv1 in CARD_VALUES:
        cv2 = total - cv1
        if 1 <= cv2 <= 10:
            key = (min(cv1, cv2), max(cv1, cv2), upcard)
            if key in ev_table:
                return _action_code(ev_table[key], allow_double)

    return "H"


def _best_action_for_soft(total, upcard, ev_table, probs, allow_double):
    """Find the best action code for a soft total.

    Soft totals have an Ace counting as 11. E.g., soft 18 = A+7.
    """
    # Soft total = Ace(1) + other card. Display = total, hard = total - 10.
    other = total - 11  # e.g., soft 18 = A + 7, other = 7
    if other < 1 or other > 10:
        return "S"
    cv1, cv2 = min(1, other), max(1, other)
    key = (cv1, cv2, upcard)
    if key in ev_table:
        return _action_code(ev_table[key], allow_double)
    return "H"


def _action_code(sev: StateEV, allow_double: bool) -> str:
    """Convert a StateEV to a CSV action code (H/S/D/DS/P/R)."""
    action = sev.best_action

    if action == Action.HIT:
        return "H"
    elif action == Action.STAND:
        return "S"
    elif action == Action.DOUBLE:
        # Determine fallback: is stand or hit better without double?
        if sev.stand >= sev.hit:
            return "DS"  # double, else stand
        return "D"  # double, else hit
    elif action == Action.SPLIT:
        return "P"
    elif action == Action.SURRENDER:
        return "R"
    return "H"
