"""Exact probabilistic blackjack solver.

Computes house edge and optimal strategy by recursive expansion of all
possible card draws weighted by exact probabilities. No simulation --
pure math.

    from cardsharp.blackjack.solver import solve
    from cardsharp.blackjack.rules import Rules

    result = solve(Rules(num_decks=6, dealer_hit_soft_17=True))
    print(f"House edge: {result.house_edge:.4%}")
    result.print_strategy()
"""

from .engine import solve, SolverResult
from .types import StateEV

__all__ = ["solve", "SolverResult", "StateEV"]
