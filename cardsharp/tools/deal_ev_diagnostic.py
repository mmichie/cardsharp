#!/usr/bin/env python
"""Per-deal EV diagnostic: localize simulator-vs-solver gaps by deal state.

For each simulated round, X = net/initial_bet and Y = the solver's exact
E[X | deal] for the round's (card1, card2, upcard) deal (with the
dealer-blackjack branch folded in, via build_deal_ev_table). Any deal
category whose mean(X - Y) moves from its expected baseline localizes a
simulator/solver mismatch: pairs implicate the split model, A/10-up
columns implicate peek conditioning, naturals implicate payout handling,
and so on.

Runs fresh-shoe rounds (penetration=0.01: the shoe reshuffles before
every round), matching the solver's per-round composition model.

Two engine legs with different expected baselines:

- --engine python (default): the reference engine plays the
  composition-dependent solver strategy (SolverStrategy
  use_ev_table=True) -- exactly the strategy whose per-deal EVs Y
  models for first decisions. E[X - Y | deal] is then ~0 except for
  the post-first-decision continuation effect (accuracy chain item 4),
  so significant per-deal residuals point at real mismatches.
- --engine fast: the Rust core plays the PURE solver table at every
  decision (composition-dependent play is not table-encodable), with
  per-deal bucketing done in the core (simulate_batch per_deal=True).
  Y stays the solver's CD optimum, so the TOTAL row reproduces the
  documented achievability gap (accuracy chain item 7b) and the table
  shows WHERE table play gives up EV against the CD optimum --
  concentrated where post-hit re-optimization matters. Future drift
  shows up as a CHANGE from that recorded baseline, decomposed by deal.

Examples:
    # 1-deck H17 (combinatorial solver), 4M rounds, reference engine
    python -m cardsharp.tools.deal_ev_diagnostic --num_decks 1 --num_rounds 4000000

    # Same config on the fast core: ~1000x faster per round
    python -m cardsharp.tools.deal_ev_diagnostic --num_decks 1 \\
        --num_rounds 100000000 --engine fast

    # Quick 6-deck sanity pass
    python -m cardsharp.tools.deal_ev_diagnostic --num_decks 6 --num_rounds 500000
"""

import argparse
import logging
import math
import random
from collections import defaultdict

from cardsharp.blackjack.actor import Player
from cardsharp.blackjack.blackjack import (
    BlackjackGame,
    build_deal_ev_table,
    _solver_card_value,
)
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.solver import solve, strategy_house_edge
from cardsharp.blackjack.state import (
    _state_placing_bets,
    STATE_DEALING,
    STATE_END_ROUND,
)
from cardsharp.blackjack.strategy import SolverStrategy
from cardsharp.common.io_interface import DummyIOInterface


def simulate(rules, num_rounds, seed):
    """Run num_rounds fresh-shoe rounds; return {deal_key: [n, sum_d, sum_d2]}."""
    print("solving...", flush=True)
    sol = solve(rules, mode="auto")
    print(f"solver HE = {sol.house_edge * 100:.4f}%", flush=True)
    deal_ev = build_deal_ev_table(sol.ev_table, rules)

    random.seed(seed)
    io = DummyIOInterface()
    strategy = SolverStrategy(sol, use_ev_table=True)
    game = BlackjackGame(rules, io)
    player = Player("P", io, strategy, initial_money=2_000_000_000)
    game.add_player(player)
    game.set_state(_state_placing_bets)

    per_key = defaultdict(lambda: [0, 0.0, 0.0])
    for r in range(num_rounds):
        money_before = player.money
        key = None
        while game.current_state.STATE_ID != STATE_END_ROUND:
            prev = game.current_state.STATE_ID
            game.current_state.handle(game)
            if prev == STATE_DEALING and key is None:
                up = _solver_card_value(game.dealer.current_hand.cards[0])
                c1 = _solver_card_value(player.hands[0].cards[0])
                c2 = _solver_card_value(player.hands[0].cards[1])
                key = (min(c1, c2), max(c1, c2), up)
        game.current_state.handle(game)  # END_ROUND
        x = (player.money - money_before) / player.initial_bets
        d = x - deal_ev[key]
        s = per_key[key]
        s[0] += 1
        s[1] += d
        s[2] += d * d
        game.reset()
        if (r + 1) % 1_000_000 == 0:
            print(f"...{r + 1:,} rounds", flush=True)
    return per_key


def simulate_fast(rules, num_rounds, seed, threads=0):
    """Fast-core leg: pure solver-table play, per-deal bucketing in the core.

    The core returns raw X moments per (c1, c2, upcard) cell; Y is
    constant within a cell, so the d = X - Y moments are derived here
    exactly: sum_d = sum_x - n*y, sum_d2 = sum_x2 - 2y*sum_x + n*y^2.
    """
    print("solving...", flush=True)
    sol = solve(rules, mode="auto")
    table_he = strategy_house_edge(sol, rules)
    print(
        f"solver HE = {sol.house_edge * 100:.4f}%  "
        f"table HE = {table_he * 100:.4f}%  "
        f"(expected TOTAL baseline: the achievability gap between table "
        f"play and the CD optimum)",
        flush=True,
    )
    deal_ev = build_deal_ev_table(sol.ev_table, rules)

    from cardsharp.fastsim import run_fast_per_deal

    strategy = SolverStrategy(sol)  # table-only: encodable for the core
    stats, cells = run_fast_per_deal(rules, strategy, num_rounds, seed, threads=threads)
    he = stats.house_edge_with_ci()
    if he is not None:
        print(
            f"simulated HE = {he[0] * 100:.4f}% +/- {he[3] * 100:.4f}% "
            f"({stats.n_rounds:,} rounds)",
            flush=True,
        )

    per_key = defaultdict(lambda: [0, 0.0, 0.0])
    for idx, (n, sx, sx2) in enumerate(cells):
        if n == 0:
            continue
        lo = idx // 100 + 1
        hi = (idx // 10) % 10 + 1
        up = idx % 10 + 1
        y = deal_ev.get((lo, hi, up))
        if y is None:
            raise RuntimeError(
                f"deal ({lo},{hi},{up}) was simulated but is absent from "
                f"the solver's deal-EV table"
            )
        per_key[(lo, hi, up)] = [n, sx - n * y, sx2 - 2.0 * y * sx + n * y * y]
    return per_key


def _category(key):
    c1, c2, _ = key
    if c1 == 1 and c2 == 10:
        return "natural"
    if c1 == c2:
        return "pair"
    if c1 == 1:
        return "soft"
    return "hard"


def report(per_key, groups):
    print(f"\n{'group':<22}{'n':>10}  {'mean(X-Y) bp':>12}  {'SE bp':>8}  {'z':>6}")
    total_n = 0
    total_d = total_d2 = 0.0
    for name, keys in groups.items():
        n = sum(per_key[k][0] for k in keys)
        if n == 0:
            continue
        sd = sum(per_key[k][1] for k in keys)
        sd2 = sum(per_key[k][2] for k in keys)
        mean = sd / n
        var = max(sd2 / n - mean * mean, 0.0)
        se = math.sqrt(var / n)
        z = mean / se if se > 0 else 0.0
        print(f"{name:<22}{n:>10,}  {mean * 1e4:>12.2f}  {se * 1e4:>8.2f}  {z:>6.1f}")
        total_n += n
        total_d += sd
        total_d2 += sd2
    mean = total_d / total_n
    var = max(total_d2 / total_n - mean * mean, 0.0)
    se = math.sqrt(var / total_n)
    z = mean / se if se > 0 else 0.0
    print(
        f"{'TOTAL':<22}{total_n:>10,}  {mean * 1e4:>12.2f}  {se * 1e4:>8.2f}  {z:>6.1f}"
    )


def main():
    # Per-decision debug logging would dominate the runtime at millions of
    # rounds; silence it the same way --simulate mode does.
    logging.disable(logging.CRITICAL)

    parser = argparse.ArgumentParser(
        description="Localize simulator-vs-solver EV gaps by deal category."
    )
    parser.add_argument("--num_decks", type=int, default=1)
    parser.add_argument("--num_rounds", type=int, default=4_000_000)
    parser.add_argument("--seed", type=int, default=99)
    parser.add_argument("--s17", action="store_true", help="dealer stands on soft 17")
    parser.add_argument(
        "--no_das", action="store_true", help="disable double after split"
    )
    parser.add_argument(
        "--engine",
        choices=["python", "fast"],
        default="python",
        help="python: reference engine with the CD solver strategy "
        "(residuals ~0 by construction). fast: Rust core with the pure "
        "solver table (TOTAL reproduces the achievability gap; see module "
        "docstring), orders of magnitude more rounds per second.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=0,
        help="fast engine only: 0 = all cores (bit-identical results "
        "regardless of thread count)",
    )
    args = parser.parse_args()

    rules = Rules(
        num_decks=args.num_decks,
        dealer_hit_soft_17=not args.s17,
        allow_double_down=True,
        allow_split=True,
        allow_surrender=True,
        allow_late_surrender=True,
        allow_double_after_split=not args.no_das,
        allow_resplitting=False,
        dealer_peek=True,
        blackjack_payout=1.5,
        penetration=0.01,  # fresh shoe every round: matches the solver model
        min_bet=10,
        max_bet=1000,
    )

    if args.engine == "fast":
        per_key = simulate_fast(rules, args.num_rounds, args.seed, args.threads)
    else:
        per_key = simulate(rules, args.num_rounds, args.seed)

    all_keys = list(per_key.keys())
    by_cat = defaultdict(list)
    for k in all_keys:
        by_cat[_category(k)].append(k)
    report(per_key, by_cat)

    by_up = defaultdict(list)
    for k in all_keys:
        name = {1: "up=A", 10: "up=10"}.get(k[2], "up=2-9")
        by_up[name].append(k)
    report(per_key, by_up)

    rows = []
    for k, (n, sd, sd2) in per_key.items():
        if n < 1000:
            continue
        mean = sd / n
        var = max(sd2 / n - mean * mean, 0.0)
        se = math.sqrt(var / n) if n else 0.0
        if se > 0:
            rows.append((abs(mean / se), k, n, mean, se))
    rows.sort(reverse=True)
    print("\nworst keys (c1,c2,up) by |z| (multiple-comparison caveat applies):")
    print(f"{'key':<14}{'n':>9}  {'mean(X-Y) bp':>12}  {'SE bp':>8}  {'z':>6}")
    for _, k, n, mean, se in rows[:15]:
        print(
            f"{str(k):<14}{n:>9,}  {mean * 1e4:>12.2f}  {se * 1e4:>8.2f}  {mean / se:>6.1f}"
        )


if __name__ == "__main__":
    main()
