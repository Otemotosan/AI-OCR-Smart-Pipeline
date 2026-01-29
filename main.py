"""Cloud Functions entry point wrapper.

This file serves as the entry point for Cloud Functions deployment,
properly setting up the Python path to allow imports from src/.
"""

import sys
from pathlib import Path

# Add project root to Python path for proper imports
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Re-export the Cloud Function entry points
from src.functions.alert.main import handle_dead_letter  # noqa: E402
from src.functions.processor.main import (  # noqa: E402
    health_check,
    process_document,
)

__all__ = ["handle_dead_letter", "health_check", "process_document"]
