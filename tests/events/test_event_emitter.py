"""
Tests for the enhanced event system.

This module contains tests for the EventEmitter and EventBus classes
to ensure they provide the expected behavior for event handling.
"""

import pytest
import threading
import time
from unittest.mock import MagicMock

from cardsharp.events import EventEmitter, EventBus, EngineEventType, EventPriority


def test_event_emitter_initialization():
    """Test that the EventEmitter initializes correctly."""
    emitter = EventEmitter()
    assert emitter is not None
    assert emitter._listeners is not None
    assert emitter._global_listeners is not None
    assert emitter._game_id is None
    assert emitter._round_id is None
    assert emitter._recorder is None


def test_set_context():
    """Test setting event context."""
    emitter = EventEmitter()
    emitter.set_context("game-123", "round-456")
    assert emitter._game_id == "game-123"
    assert emitter._round_id == "round-456"


def test_set_recorder():
    """Test setting an event recorder."""
    emitter = EventEmitter()
    mock_recorder = MagicMock()
    emitter.set_recorder(mock_recorder)
    assert emitter._recorder == mock_recorder


def test_on_with_string_event_type():
    """Test subscribing to an event with a string event type."""
    emitter = EventEmitter()
    callback = MagicMock()

    # Subscribe to the event
    unsubscribe = emitter.on("test_event", callback)

    # Emit the event
    test_data = {"value": "test"}
    emitter.emit("test_event", test_data)

    # Verify callback was called with the right data
    callback.assert_called_once_with(test_data)

    # Unsubscribe and emit again
    unsubscribe()
    emitter.emit("test_event", {"value": "test2"})

    # Verify callback was not called again (still has only one call)
    assert callback.call_count == 1


def test_on_with_enum_event_type():
    """Test subscribing to an event with an enum event type."""
    emitter = EventEmitter()
    callback = MagicMock()

    # Subscribe to the event using enum
    emitter.on(EngineEventType.CARD_DEALT, callback)

    # Emit the event with the enum
    test_data = {"card": "A♠"}
    emitter.emit(EngineEventType.CARD_DEALT, test_data)

    # Verify callback was called with the right data
    callback.assert_called_once_with(test_data)


def test_once_subscription():
    """Test subscribing to an event for a single occurrence."""
    emitter = EventEmitter()
    callback = MagicMock()

    # Subscribe to the event once
    emitter.once("test_event", callback)

    # Emit the event twice
    emitter.emit("test_event", {"id": 1})
    emitter.emit("test_event", {"id": 2})

    # Verify callback was called only once with the first event
    callback.assert_called_once()
    assert callback.call_args[0][0]["id"] == 1


def test_on_any_subscription():
    """Test subscribing to all events."""
    emitter = EventEmitter()
    callback = MagicMock()

    # Subscribe to all events
    unsubscribe = emitter.on_any(callback)

    # Emit different events
    emitter.emit("event1", {"id": 1})
    emitter.emit("event2", {"id": 2})

    # Verify callback was called for each event
    assert callback.call_count == 2
    # First call should have event type and data
    event_type, event_data = callback.call_args_list[0][0][0]
    assert event_type == "event1"
    assert event_data["id"] == 1

    # Unsubscribe and emit again
    unsubscribe()
    emitter.emit("event3", {"id": 3})

    # Verify callback was not called again
    assert callback.call_count == 2


def test_emitter_priority():
    """Test that handlers are called in priority order."""
    emitter = EventEmitter()
    call_order = []

    # Create callbacks that record the order they're called in
    def low_priority(data):
        call_order.append("low")

    def normal_priority(data):
        call_order.append("normal")

    def high_priority(data):
        call_order.append("high")

    def critical_priority(data):
        call_order.append("critical")

    # Subscribe in a mixed order but with different priorities
    emitter.on("test_event", normal_priority, EventPriority.NORMAL)
    emitter.on("test_event", low_priority, EventPriority.LOW)
    emitter.on("test_event", critical_priority, EventPriority.CRITICAL)
    emitter.on("test_event", high_priority, EventPriority.HIGH)

    # Emit the event
    emitter.emit("test_event", {})

    # Check the order: should be critical, high, normal, low
    assert call_order == ["critical", "high", "normal", "low"]


def test_remove_all_listeners():
    """Test removing all listeners."""
    emitter = EventEmitter()
    callback1 = MagicMock()
    callback2 = MagicMock()

    # Subscribe to different events
    emitter.on("event1", callback1)
    emitter.on("event2", callback2)

    # Remove all listeners for event1
    emitter.remove_all_listeners("event1")

    # Emit both events
    emitter.emit("event1", {"id": 1})
    emitter.emit("event2", {"id": 2})

    # Verify callback1 was not called, but callback2 was
    callback1.assert_not_called()
    callback2.assert_called_once()

    # Remove all listeners for all events
    emitter.remove_all_listeners()

    # Reset the mock and emit event2 again
    callback2.reset_mock()
    emitter.emit("event2", {"id": 3})

    # Verify callback2 was not called
    callback2.assert_not_called()


def test_emit_exceptions_are_caught():
    """Test that exceptions in event handlers are caught and don't stop execution."""
    emitter = EventEmitter()

    def callback_raises_exception(data):
        raise ValueError("Test exception")

    callback_after = MagicMock()

    # Subscribe both callbacks
    emitter.on("test_event", callback_raises_exception)
    emitter.on("test_event", callback_after)

    # Emit event (should not raise exception)
    emitter.emit("test_event", {})

    # Verify the second callback was still called
    callback_after.assert_called_once()


def test_emit_deferred():
    """Test deferred event emission."""
    emitter = EventEmitter()
    callback = MagicMock()

    # Subscribe to the event
    emitter.on("test_event", callback)

    # Emit with a short delay
    emitter.emit_deferred("test_event", {"id": 1}, 100)  # 100ms

    # Verify callback not called immediately
    callback.assert_not_called()

    # Wait for the event to be emitted
    time.sleep(0.2)  # 200ms

    # Verify callback was called after the delay
    callback.assert_called_once()


def test_event_bus_singleton():
    """Test that EventBus is a singleton."""
    bus1 = EventBus.get_instance()
    bus2 = EventBus.get_instance()

    # Verify both references point to the same object
    assert bus1 is bus2

    # Verify it's an EventEmitter
    assert isinstance(bus1, EventEmitter)


def test_thread_safety():
    """Test thread safety of event emission."""
    emitter = EventEmitter()
    count = {"value": 0}
    lock = threading.Lock()

    def increment_counter(data):
        with lock:
            count["value"] += 1

    # Subscribe to the event
    emitter.on("test_event", increment_counter)

    # Create threads that emit events simultaneously
    threads = []
    for _ in range(10):
        t = threading.Thread(target=lambda: emitter.emit("test_event", {}))
        threads.append(t)

    # Start all threads
    for t in threads:
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # Verify all events were processed
    assert count["value"] == 10


@pytest.mark.asyncio
async def test_emit_async():
    """Test asynchronous event emission."""
    emitter = EventEmitter()
    callback = MagicMock()

    # Subscribe to the event
    emitter.on("test_event", callback)

    # Emit asynchronously
    await emitter.emit_async("test_event", {"id": 1})

    # Verify callback was called
    callback.assert_called_once()


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
