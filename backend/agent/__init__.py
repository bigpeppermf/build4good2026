from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["WhiteboardAgent"]


def __getattr__(name: str) -> Any:
    if name == "WhiteboardAgent":
        return import_module(".agent", __name__).WhiteboardAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
