"""
API module for Cardsharp.

This module provides high-level, platform-agnostic APIs for working with the
Cardsharp engine, supporting both synchronous and asynchronous operation.
"""

from cardsharp.api.base import CardsharpGame
from cardsharp.api.blackjack import BlackjackGame
from cardsharp.api.high_card import HighCardGame
from cardsharp.api.war import WarGame
from cardsharp.api.durak import DurakGame
from cardsharp.api.flow import (
    EventWaiter,
    EventSequence,
    EventFilter,
    event_driven,
    EventDrivenContext,
)

__all__ = [
    # Core API
    "CardsharpGame",
    "BlackjackGame",
    "HighCardGame",
    "WarGame",
    "DurakGame",
    # Flow control utilities
    "EventWaiter",
    "EventSequence",
    "EventFilter",
    "event_driven",
    "EventDrivenContext",
]
