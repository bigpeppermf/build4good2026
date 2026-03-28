"""
Pytest configuration for the backend test suite.

Adds the backend root to sys.path so imports like ``from core.graph import ...``
work regardless of where pytest is invoked from.
"""

import sys
from pathlib import Path

# Ensure backend/ is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))
