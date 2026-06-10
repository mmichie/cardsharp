"""Exact probabilistic blackjack solver.

Computes house edge and optimal strategy by recursive expansion of all
possible card draws weighted by exact probabilities. No simulation --
pure math.

    from cardsharp.blackjack.solver import solve
    from cardsharp.blackjack.rules import Rules

    result = solve(Rules(num_decks=6, dealer_hit_soft_17=True))
    print(f"House edge: {result.house_edge:.4%}")
    result.print_strategy()

Modes (see ``solve`` docstring for full table):

* ``fast`` (library default): ~1-2s. Static dealer probabilities.
  Pessimistic by ~0.01-0.03% at 1-2 decks, shrinking to <0.005% at 5+.
* ``auto`` (CLI default, recommended for accuracy): routes by deck size
  to the most accurate practical path. ≤2 decks → combinatorial (matches
  WoO Appendix 9 within rounding). 3-4 decks → exact (closes ~88% of the
  static-dealer-prob gap). 5+ decks → fast (no penalty over plain fast).
"""

from .engine import solve, strategy_house_edge, SolverResult
from .types import StateEV

__all__ = ["solve", "strategy_house_edge", "SolverResult", "StateEV"]
