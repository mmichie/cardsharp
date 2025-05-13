"""
Pytest configuration for verification tests.

This module contains pytest fixtures and configuration for testing verification components.
"""

import asyncio
import pytest
import time
from cardsharp.events import EventBus


# Reset event bus before each test function
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
