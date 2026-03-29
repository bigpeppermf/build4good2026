"""
Unit tests for agent/validation_agent.py.

The LLM and transcription layers are mocked so tests run offline.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from agent.validation_agent import ValidationAgent, transcribe_audio
from core.graph import SystemDesignGraph


def tool_response(tool_name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"id": call_id, "name": tool_name, "args": args}],
    )


def text_response(text: str) -> AIMessage:
    return AIMessage(content=text)


def make_agent(
    graph: SystemDesignGraph | None = None,
    transcript_text: str = "Candidate mentioned Redis cache and API.",
) -> tuple[ValidationAgent, SystemDesignGraph, AsyncMock]:
    graph = graph or SystemDesignGraph()

    llm = MagicMock()
    llm_with_tools = AsyncMock()
    llm.bind_tools.return_value = llm_with_tools

    async def fake_transcribe(_audio_bytes: bytes, _mime_type: str) -> str:
        return transcript_text

    agent = ValidationAgent(
        graph=graph,
        llm=llm,
        transcribe_fn=fake_transcribe,
    )
    return agent, graph, llm_with_tools


class TestValidationAgent:
    def test_validate_transcript_applies_mutations_and_counts_corrections(self):
        graph = SystemDesignGraph()
        graph.create_node("client", "Client", "client")
        graph.create_node("api", "API", "service")
        graph.add_edge("client", "api", "requests")

        agent, _, llm_with_tools = make_agent(graph=graph)
        llm_with_tools.ainvoke.side_effect = [
            tool_response(
                "create_node",
                {"id": "redis", "label": "Redis Cache", "type": "cache"},
                call_id="mut_1",
            ),
            tool_response("get_graph_state", {}, call_id="read_1"),
            text_response("Added Redis cache mentioned in transcript."),
        ]

        result = asyncio.run(agent.validate_transcript("I added Redis cache behind API."))

        node_ids = [node["id"] for node in graph.get_state()["nodes"]]
        assert "redis" in node_ids
        assert result.corrections_made == 1
        assert result.validation_summary == "Added Redis cache mentioned in transcript."
        assert result.graph_confidence == pytest.approx(2 / 3)

    def test_validate_transcript_empty_input_skips_llm(self):
        agent, _, llm_with_tools = make_agent(transcript_text="")

        result = asyncio.run(agent.validate_transcript("   "))

        assert result.transcript == ""
        assert result.corrections_made == 0
        assert result.validation_summary == "Graph matches transcript"
        assert result.graph_confidence == 1.0
        assert llm_with_tools.ainvoke.call_count == 0

    def test_validate_audio_uses_transcriber_output(self):
        agent, _, llm_with_tools = make_agent(transcript_text="Transcript text")
        llm_with_tools.ainvoke.side_effect = [
            text_response("Graph matches transcript"),
        ]

        result = asyncio.run(agent.validate_audio(b"audio-bytes", "audio/webm"))

        assert result.transcript == "Transcript text"
        assert result.validation_summary == "Graph matches transcript"
        assert llm_with_tools.ainvoke.call_count == 1

    def test_non_empty_transcript_without_llm_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key-stub")
        agent = ValidationAgent(graph=SystemDesignGraph())

        with pytest.raises(RuntimeError, match="Validation LLM is not configured"):
            asyncio.run(agent.validate_transcript("non-empty transcript"))


class TestTranscribeAudio:
    def test_stub_key_returns_empty_without_network(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key-stub")

        transcript = asyncio.run(transcribe_audio(b"fake-audio", "audio/webm"))

        assert transcript == ""
