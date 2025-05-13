"""
Pytest configuration for integration tests.

This module contains pytest fixtures and configuration for integration testing components,
ensuring proper event bus initialization and event loop cleanup between tests.
"""

import asyncio
import pytest
import time
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


# Use a fresh event loop for each test
@pytest.fixture(scope="function")
def event_loop():
    """Create and yield a new event loop for each test."""
    # Get the current policy
    policy = asyncio.get_event_loop_policy()

    # Create and set a new loop
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)

    yield loop

    try:
        # Clean up pending tasks
        pending = asyncio.all_tasks(loop)
        if pending:
            # Give tasks a chance to complete
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        # Close the loop
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
    except Exception as e:
        print(f"Error during event_loop cleanup: {e}")

    # Reset the event loop
    asyncio.set_event_loop(None)
