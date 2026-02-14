#!/usr/bin/env python3
"""
Example script demonstrating the immutable state verification system.

This script shows how to use the enhanced verification system that leverages
the immutable state pattern to verify game integrity and rule adherence.
"""

import asyncio
import logging

from cardsharp.api import BlackjackGame
from cardsharp.adapters import DummyAdapter
from cardsharp.events import EventBus
from cardsharp.blackjack.rules import Rules
from cardsharp.verification.immutable_verifier import (
    StateTransitionRecorder,
    ImmutableStateVerifier,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_verification_demo():
    """Run the verification demo."""
    logger.info("Starting verification demo")

    # Create a rules object
    rules = Rules(
        blackjack_payout=1.5,
        num_decks=6,
        dealer_hit_soft_17=False,
        allow_insurance=True,
        allow_surrender=True,
        allow_double_after_split=True,
        allow_split=True,
        allow_double_down=True,
        min_bet=5.0,
        max_bet=1000.0,
    )

    # Create a state transition recorder
    recorder = StateTransitionRecorder()

    # Create a dummy adapter
    adapter = DummyAdapter()

    # Create a game with the adapter
    config = {
        "dealer_rules": {"stand_on_soft_17": True, "peek_for_blackjack": True},
        "deck_count": 6,
        "rules": rules.__dict__,
    }

    game = BlackjackGame(adapter=adapter, config=config, auto_play=True)

    try:
        # Initialize the game
        logger.info("Initializing game")
        await game.initialize()

        # Start the game
        logger.info("Starting game")
        await game.start_game()

        # Add players
        logger.info("Adding players")
        player1 = await game.add_player("Alice", 1000.0)
        player2 = await game.add_player("Bob", 1000.0)

        # Play a few rounds
        logger.info("Playing rounds")
        for i in range(3):
            logger.info(f"Playing round {i+1}")
            result = await game.auto_play_round(default_bet=10.0)
            logger.info(f"Round {i+1} result: {result}")

            # Wait a bit between rounds
            await asyncio.sleep(0.5)

        # Get the event bus
        event_bus = EventBus.get_instance()

        # Create a verifier with the recorder and rules
        logger.info("Creating verifier")
        verifier = ImmutableStateVerifier(recorder, rules)

        # Run verification
        logger.info("Running verification")
        results = verifier.verify_all()

        # Display results
        logger.info("Verification results:")
        for result in results:
            status = "PASSED" if result.passed else "FAILED"
            logger.info(f"{result.verification_type.name}: {status}")
            if not result.passed and result.error_detail:
                logger.info(f"  Error: {result.error_detail}")

    finally:
        # Shutdown the game
        logger.info("Shutting down game")
        await game.shutdown()

        # Shutdown the recorder
        logger.info("Shutting down recorder")
        recorder.shutdown()


if __name__ == "__main__":
    # Run the demo
    asyncio.run(run_verification_demo())
