"""
Baccarat game implementation.

This module provides a complete implementation of the casino game Baccarat,
including game rules, hand evaluation, and simulation capabilities.
"""

from cardsharp.baccarat.game import BaccaratGame, BetType, Outcome, BaccaratResult
from cardsharp.baccarat.hand import BaccaratHand
from cardsharp.baccarat.rules import BaccaratRules

__all__ = [
    "BaccaratGame",
    "BaccaratHand",
    "BaccaratRules",
    "BetType",
    "Outcome",
    "BaccaratResult",
]
