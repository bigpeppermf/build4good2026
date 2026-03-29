from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "WhiteboardAgent",
    "ValidationAgent",
    "ValidationResult",
    "AnalysisAgent",
    "ChatAgent",
]


def __getattr__(name: str) -> Any:
    if name == "WhiteboardAgent":
        return import_module(".agent", __name__).WhiteboardAgent
    if name in {"ValidationAgent", "ValidationResult"}:
        module = import_module(".validation_agent", __name__)
        return getattr(module, name)
    if name == "AnalysisAgent":
        return import_module(".analysis_agent", __name__).AnalysisAgent
    if name == "ChatAgent":
        return import_module(".chat_agent", __name__).ChatAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
