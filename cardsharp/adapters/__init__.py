"""
Platform adapters for the Cardsharp engine.

This package provides adapters that translate between the core game engine
and various platforms (CLI, web, Discord, etc.).
"""

from cardsharp.adapters.base import PlatformAdapter
from cardsharp.adapters.cli import CLIAdapter
from cardsharp.adapters.dummy import DummyAdapter

__all__ = ["PlatformAdapter", "CLIAdapter", "DummyAdapter"]
