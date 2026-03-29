"""
Post-session graph validation agent.

This agent compares an audio transcript against the current graph snapshot and
uses graph tools to apply high-confidence corrections.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from core.graph import SystemDesignGraph

from .agent import _build_tools

TRANSCRIPTION_PROMPT = (
    "Transcribe this audio recording of a system design whiteboard session. "
    "Preserve technical terms, component names, and architecture details verbatim."
)

VALIDATION_SYSTEM_PROMPT = """\
You are a system design auditor. You are given:
1) A TRANSCRIPT of what a developer said while designing on a whiteboard.
2) A GRAPH SNAPSHOT captured from the visual/OCR pipeline.

Your job is to identify discrepancies: components/connections mentioned in the
transcript that are missing from the graph, or labels that are clearly misread.

Use available tools to correct the graph. Only make high-confidence changes
grounded in explicit transcript statements. Do not add vague implications.

After corrections, call get_graph_state() and output one sentence summarizing
what was corrected, or exactly "Graph matches transcript" if no corrections were needed.
"""


@dataclass
class ValidationResult:
    transcript: str
    corrections_made: int
    validation_summary: str
    graph_confidence: float


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
    """
    Transcribe session audio with Gemini multimodal API.

    Returns an empty string when no real API key is configured so local tests
    can run without network access.
    """
    if not audio_bytes:
        return ""

    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key or api_key == "test-key-stub":
        return ""

    try:
        import google.generativeai as genai  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"google-generativeai is required for audio transcription: {exc}") from exc

    genai.configure(api_key=api_key)
    models = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]
    last_error: Exception | None = None

    for model_name in models:
        try:
            model = genai.GenerativeModel(model_name)
            audio_part = {"mime_type": mime_type or "audio/webm", "data": audio_bytes}
            response = await model.generate_content_async([TRANSCRIPTION_PROMPT, audio_part])
            text = (getattr(response, "text", "") or "").strip()
            if text:
                return text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    if last_error is not None:
        raise RuntimeError(f"Gemini transcription failed: {last_error}") from last_error
    return ""


class ValidationAgent:
    """
    Validates graph structure against audio transcript and applies corrections.
    """

    def __init__(
        self,
        graph: SystemDesignGraph,
        llm: Any | None = None,
        transcribe_fn: Callable[[bytes, str], Awaitable[str]] | None = None,
    ) -> None:
        self.graph = graph
        api_key = os.environ.get("GOOGLE_API_KEY", "").strip()

        if llm is not None:
            self.llm = llm
        elif api_key and api_key != "test-key-stub":
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash-lite",
                temperature=0,
                google_api_key=api_key,
            )
        else:
            # In local tests or environments without a real key we still allow
            # transcript-less validation paths to run without an LLM.
            self.llm = None

        self.tools = _build_tools(graph)
        self.llm_with_tools = self.llm.bind_tools(self.tools) if self.llm is not None else None
        self.tool_map: dict[str, Any] = {t.name: t for t in self.tools}
        self._transcribe_fn = transcribe_fn or transcribe_audio

    async def validate_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> ValidationResult:
        transcript = await self._transcribe_fn(audio_bytes, mime_type)
        return self.validate_transcript(transcript)

    def validate_transcript(self, transcript: str) -> ValidationResult:
        normalized_transcript = (transcript or "").strip()
        if not normalized_transcript:
            return ValidationResult(
                transcript="",
                corrections_made=0,
                validation_summary="Graph matches transcript",
                graph_confidence=1.0,
            )

        if self.llm_with_tools is None:
            raise RuntimeError("Validation LLM is not configured for non-empty transcript validation.")

        graph_snapshot = self.graph.bfs_serialize()
        user_prompt = (
            f"TRANSCRIPT:\n{normalized_transcript}\n\n"
            f"GRAPH SNAPSHOT:\n{graph_snapshot}\n\n"
            "Apply corrections only when explicit in the transcript."
        )
        messages: list[Any] = [
            SystemMessage(content=VALIDATION_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        corrections_made = 0
        validation_summary = "Graph matches transcript"

        while True:
            response = self.llm_with_tools.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                text = (response.content or "").strip()
                if text:
                    validation_summary = text
                break

            tool_messages: list[ToolMessage] = []
            for call in response.tool_calls:
                fn = self.tool_map.get(call["name"])
                if fn is None:
                    continue
                before_state = self.graph.get_state()
                result = fn.invoke(call["args"])
                after_state = self.graph.get_state()
                if before_state != after_state:
                    corrections_made += 1
                tool_messages.append(
                    ToolMessage(
                        name=call["name"],
                        content=str(result),
                        tool_call_id=call["id"],
                    )
                )
            messages.extend(tool_messages)

        node_count = max(1, len(self.graph.get_state()["nodes"]))
        graph_confidence = 1.0 - min(1.0, corrections_made / node_count)

        return ValidationResult(
            transcript=normalized_transcript,
            corrections_made=corrections_made,
            validation_summary=validation_summary,
            graph_confidence=graph_confidence,
        )
