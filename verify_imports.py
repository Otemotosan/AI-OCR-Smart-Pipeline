
import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

print(f"Testing import from {PROJECT_ROOT}")

try:
    print("Attempting to import handle_dead_letter from main...")
    from main import handle_dead_letter
    print("SUCCESS: handle_dead_letter imported.")
except Exception as e:
    print(f"FAILURE: {e}")
    import traceback
    traceback.print_exc()
