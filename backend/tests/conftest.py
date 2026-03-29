"""
Pytest configuration for the backend test suite.

Adds the backend root to sys.path so imports like ``from core.graph import ...``
work regardless of where pytest is invoked from.
"""

import os
import sys
from pathlib import Path

# Ultralytics/YOLO writes config under XDG; keep it inside the repo for CI/sandbox.
_xdg = Path(__file__).resolve().parent / ".pytest_xdg_config"
_xdg.mkdir(exist_ok=True)
os.environ.setdefault("XDG_CONFIG_HOME", str(_xdg))

# Ensure backend/ is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))
