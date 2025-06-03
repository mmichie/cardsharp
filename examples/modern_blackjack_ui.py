#!/usr/bin/env python3
"""
Example script for running the modern Blackjack UI.

This script demonstrates how to run the modern Blackjack UI using
the new engine pattern.
"""

import os
import subprocess
import sys
from pathlib import Path


def run_streamlit_app():
    """
    Run the Streamlit app for the modern Blackjack UI.

    This function runs the Streamlit app for the modern Blackjack UI
    as a subprocess.
    """
    # Get the path to the UI module
    # We need to use absolute paths for the module path
    ui_module_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "cardsharp",
        "ui",
        "blackjack_ui.py",
    )

    # Ensure the module exists
    if not os.path.exists(ui_module_path):
        print(f"Error: UI module not found at {ui_module_path}")
        sys.exit(1)

    # Run the Streamlit app
    print(f"Running Streamlit app from {ui_module_path}")

    # We need to provide the full path to avoid module import issues
    command = [
        "streamlit",
        "run",
        ui_module_path,
        "--server.port",
        "8501",  # Default port
        "--browser.serverAddress",
        "localhost",
        "--server.headless",
        "false",
        "--browser.gatherUsageStats",
        "false",
    ]

    try:
        process = subprocess.Popen(command)

        # Wait for the process to complete
        process.wait()
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print("\nStopping Streamlit app...")
        process.terminate()
        process.wait()
    except Exception as e:
        print(f"Error running Streamlit app: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_streamlit_app()
