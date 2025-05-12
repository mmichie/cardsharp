"""
Event system for the Cardsharp engine.

This package provides a robust event system that serves as the foundation for the
event-driven architecture.
"""

from cardsharp.events.emitter import (
    EventEmitter,
    EventBus,
    EventPriority,
    EngineEventType,
)

# Import websocket support if available
try:
    from cardsharp.events.websocket import (
        WebSocketEventHandler,
        WebSocketClient,
        ClientMessage,
        ServerMessage,
        get_websocket_handler,
    )

    __all__ = [
        "EventEmitter",
        "EventBus",
        "EventPriority",
        "EngineEventType",
        "WebSocketEventHandler",
        "WebSocketClient",
        "ClientMessage",
        "ServerMessage",
        "get_websocket_handler",
    ]
except ImportError:
    __all__ = ["EventEmitter", "EventBus", "EventPriority", "EngineEventType"]
