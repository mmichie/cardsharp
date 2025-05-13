# 0.5.0

* Fix event handler cleanup in WarGame and HighCardGame to match BlackjackGame implementation
* Add standalone test script for API tests that doesn't rely on pytest
* Add proper pytest tests for event handler cleanup and BlackjackGame functionality
* Reorganize test files to follow proper structure
* Rename example scripts to clarify they are demos, not tests
* Add new BlackjackGame API demo
* Update architecture documentation to highlight resource management benefits
* Migrate UI implementation to use modern architecture (renamed blackjack_ui_new.py to blackjack_ui.py)

# 0.4.0

* Complete Phase 4 of architecture modernization
* Add WebSocket support for real-time updates
* Add immutable state verification system
* Implement high-level game APIs for all game types
* Add new example scripts for demonstration

# 0.3.0

* Vastly increased performance, removed async from main path
* Add async io compatibility layer

# 0.2.0

* Multiprocessing Capability
* Basic profiling support

# 0.1.0

* Initial Release
