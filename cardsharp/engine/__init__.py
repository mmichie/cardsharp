"""
Core engine for the Cardsharp framework.

This package provides the game engine that powers the Cardsharp framework,
implementing the game logic in a platform-agnostic way.
"""

from cardsharp.engine.base import CardsharpEngine
from cardsharp.engine.blackjack import BlackjackEngine
from cardsharp.engine.high_card import HighCardEngine
from cardsharp.engine.war import WarEngine
from cardsharp.engine.durak import DurakEngine

__all__ = [
    "CardsharpEngine",
    "BlackjackEngine",
    "HighCardEngine",
    "WarEngine",
    "DurakEngine",
]
