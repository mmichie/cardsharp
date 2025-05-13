"""
Pytest configuration for tests at the root level.

This module contains pytest fixtures and configuration for testing components.
"""

import asyncio
import time
import pytest
from cardsharp.events import EventBus


# Reset event bus before each test
@pytest.fixture(scope="function", autouse=True)
def reset_event_bus():
    """Reset the event bus singleton before each test."""
    # Reset before test
    EventBus._instance = None
    yield
    # Clean up after test
    EventBus._instance = None
    # Add a small delay to ensure events are fully processed
    time.sleep(0.1)
