"""
Verification package for the CardSharp blackjack simulation.

This package provides tools for verifying the correctness of blackjack simulations,
tracking game events, and analyzing statistical outcomes.
"""

from cardsharp.verification.schema import initialize_database, DatabaseInitializer
from cardsharp.verification.events import (
    EventType,
    GameEvent,
    EventEmitter,
    EventRecorder,
)
from cardsharp.verification.storage import SQLiteEventStore
from cardsharp.verification.verifier import (
    VerificationType,
    VerificationResult,
    BlackjackVerifier,
)
from cardsharp.verification.statistics import (
    AnalysisType,
    ConfidenceInterval,
    StatisticalValidator,
)
from cardsharp.verification.playback import (
    PlaybackSpeed,
    PlaybackController,
    GameVisualizer,
)
from cardsharp.verification.main import (
    VerificationSystem,
    init_verification,
    get_verification_system,
    verify_session,
)

__all__ = [
    "initialize_database",
    "DatabaseInitializer",
    "EventType",
    "GameEvent",
    "EventEmitter",
    "EventRecorder",
    "SQLiteEventStore",
    "VerificationType",
    "VerificationResult",
    "BlackjackVerifier",
    "AnalysisType",
    "ConfidenceInterval",
    "StatisticalValidator",
    "PlaybackSpeed",
    "PlaybackController",
    "GameVisualizer",
    "VerificationSystem",
    "init_verification",
    "get_verification_system",
    "verify_session",
]
