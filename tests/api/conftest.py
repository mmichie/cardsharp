"""
Pytest configuration for API tests.

This module contains pytest fixtures and configuration for testing API components.
"""

import asyncio
import pytest
from cardsharp.events import EventBus


# Reset event bus before each test module
@pytest.fixture(scope="module", autouse=True)
def reset_event_bus():
    """Reset the event bus singleton before each test module."""
    EventBus._instance = None
    yield
    # Clean up after all tests in the module
    EventBus._instance = None


# Use a fresh event loop for each test
@pytest.fixture(scope="function")
def event_loop():
    """Create and yield a new event loop for each test."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    # Clean up pending tasks
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()
    # Run loop until all tasks are complete
    if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()
