#!/usr/bin/env python
"""Benchmark the simulator against the Wizard of Odds calculator.

For each rule set pinned against the WoO blackjack calculator
(tests/blackjack/solver/test_engine.py::TestWoOReference), runs a large
multiprocess simulation under matched assumptions -- fresh shoe every
round (penetration=0.01), composition-dependent first decisions
(SolverStrategy use_ev_table=True), solver-EV control variate -- and
reports the simulated house edge against both the WoO Optimal value and
this package's solver.

Interpretation guide (see beads-8o8/beads-caz and the RESOLVED note in
TestWoOReference): our solver and WoO Optimal agree within ~1 bp at
every config -- both compute the full composition-dependent optimum,
including re-optimized stand-vs-hit at every post-hit card. The
simulator plays table-achievable strategy, so it lands slightly above
both: ~+6 bp at 1-2 decks, ~+1.5 bp at 6 decks (the achievability gap
dilutes with deck count).

Example:
    python -m cardsharp.tools.woo_benchmark --num_games 40000000
    python -m cardsharp.tools.woo_benchmark --num_games 1000000 --configs 1dH17
"""

import argparse
import multiprocessing
import os
import random
import time

from cardsharp.blackjack.blackjack import build_deal_ev_table, play_game_batch
from cardsharp.blackjack.rules import Rules
from cardsharp.blackjack.solver import solve
from cardsharp.blackjack.stats import SimulationStats
from cardsharp.blackjack.strategy import SolverStrategy
from cardsharp.common.io_interface import DummyIOInterface

# WoO calculator "Optimal results" (perfect composition-dependent
# strategy + reshuffle every hand), pulled via Playwright on 2026-05-12.
# Rule set: no-DAS, double-any, resplit-to-2-hands, no resplit-aces,
# no hit-split-aces, OBO/peek, late surrender, blackjack 3:2.
# Keep in sync with tests/blackjack/solver/test_engine.py.
WOO_OPTIMAL = {
    "1dH17": (1, True, 0.0013076),
    "1dS17": (1, False, -0.0004632),
    "2dH17": (2, True, 0.0048575),
    "6dH17": (6, True, 0.0070486),
    "6dS17": (6, False, 0.0050619),
}


def woo_rules(num_decks, h17):
    return Rules(
        num_decks=num_decks,
        dealer_hit_soft_17=h17,
        allow_double_down=True,
        allow_split=True,
        allow_double_after_split=False,
        allow_resplitting=False,
        allow_surrender=True,
        allow_late_surrender=True,
        dealer_peek=True,
        blackjack_payout=1.5,
        penetration=0.01,  # fresh shoe every round: WoO's reshuffle model
        min_bet=10,
        max_bet=1000,
    )


def run_config(label, num_decks, h17, woo_he, num_games, master_seed):
    rules = woo_rules(num_decks, h17)

    t0 = time.time()
    print(f"\n[{label}] solving (mode=auto)...", flush=True)
    sol = solve(rules, mode="auto")
    print(
        f"[{label}] solver HE = {sol.house_edge * 100:+.4f}%  "
        f"(WoO Optimal {woo_he * 100:+.4f}%)  solve took {time.time() - t0:.0f}s",
        flush=True,
    )

    strategy = SolverStrategy(sol, use_ev_table=True)
    deal_ev_table = build_deal_ev_table(sol.ev_table, rules)

    random.seed(master_seed)
    cpu_count = multiprocessing.cpu_count()
    games_per_cpu, remainder = divmod(num_games, cpu_count)
    batches = [games_per_cpu + (1 if i < remainder else 0) for i in range(cpu_count)]
    worker_seeds = [random.randint(0, 2**63 - 1) for _ in range(cpu_count)]

    t0 = time.time()
    with multiprocessing.Pool() as pool:
        batch_args = [
            (
                rules,
                DummyIOInterface(),
                ["Player"],
                batch,
                strategy,
                1000,
                "perfect",
                None,
                worker_seeds[i],
                deal_ev_table,
            )
            for i, batch in enumerate(batches)
        ]
        results = pool.starmap(play_game_batch, batch_args)

    agg = SimulationStats()
    agg.cv_mu_y = -sol.house_edge
    for batch_dict, _, _ in results:
        agg.merge(SimulationStats.from_dict(batch_dict))
    elapsed = time.time() - t0
    print(
        f"[{label}] {num_games:,} games in {elapsed:.0f}s "
        f"({num_games / elapsed:,.0f} games/s)",
        flush=True,
    )

    he_raw = agg.house_edge_with_ci(0.95)
    if he_raw is None:
        raise RuntimeError(f"[{label}] no rounds recorded")
    cv = agg.control_variate_he_with_ci(0.95)
    row = {
        "label": label,
        "woo": woo_he,
        "solver": sol.house_edge,
        "raw": he_raw,  # (he, lo, hi, half)
        "cv": cv,  # dict or None
    }
    he, _, _, half = he_raw
    print(f"[{label}] sim HE = {he * 100:+.4f}% +/- {half * 100:.4f}% (raw)", flush=True)
    if cv:
        print(
            f"[{label}] sim HE = {cv['he'] * 100:+.4f}% +/- {cv['half'] * 100:.4f}% (CV)",
            flush=True,
        )
    return row


def print_report(rows, num_games):
    bp = 1e4
    print("\n" + "=" * 96)
    print(
        f"Simulator vs Wizard of Odds Optimal -- fresh shoe per round, "
        f"CD strategy, {num_games:,} games per config"
    )
    print(
        "Rules: no-DAS, double any 2, split to 2 hands, no RSA/HSA, peek, "
        "late surrender, 3:2"
    )
    print("=" * 96)
    header = (
        f"{'config':<7} {'WoO':>8} {'solver':>8} {'sim (CV)':>9} "
        f"{'+/-':>6} {'sim-WoO':>8} {'sim-solver':>10}"
    )
    print(header + "   (all in bp of initial bet)")
    print("-" * 96)
    for r in rows:
        est = r["cv"] if r["cv"] else None
        if est:
            he, half = est["he"], est["half"]
        else:
            he, _, _, half = r["raw"]
        print(
            f"{r['label']:<7} {r['woo'] * bp:>8.2f} {r['solver'] * bp:>8.2f} "
            f"{he * bp:>9.2f} {half * bp:>6.2f} "
            f"{(he - r['woo']) * bp:>+8.2f} {(he - r['solver']) * bp:>+10.2f}"
        )
    print("-" * 96)
    print(
        "Expected: solver-WoO within ~1 bp at every config (both are full-CD "
        "optima). sim-solver is\npositive and shrinks with deck count -- the "
        "achievability gap between table play and\ncomposition-dependent "
        "continuations: ~+6 bp at 1-2 decks, ~+1.5 bp at 6 decks "
        "(2026-06-09\nbaselines: 40M games/config + 160M-game 6d precision "
        "run)."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Large-sample simulator benchmark vs WoO calculator values."
    )
    parser.add_argument(
        "--num_games", type=int, default=40_000_000,
        help="games per configuration (default 40M: CV CI ~ +/-3bp)",
    )
    parser.add_argument(
        "--configs", nargs="*", default=list(WOO_OPTIMAL),
        choices=list(WOO_OPTIMAL), help="subset of configs to run",
    )
    parser.add_argument("--seed", type=int, default=20260609)
    args = parser.parse_args()

    os.environ["BLACKJACK_DISABLE_LOGGING"] = "1"

    rows = []
    for i, label in enumerate(args.configs):
        num_decks, h17, woo_he = WOO_OPTIMAL[label]
        rows.append(
            run_config(label, num_decks, h17, woo_he, args.num_games, args.seed + i)
        )
    print_report(rows, args.num_games)


if __name__ == "__main__":
    main()
