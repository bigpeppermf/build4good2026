"""
Unit tests for agent/analysis_agent.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage

from agent.analysis_agent import AnalysisAgent
from core.graph import SystemDesignGraph


def _build_graph() -> SystemDesignGraph:
    graph = SystemDesignGraph()
    graph.create_node("browser", "Browser", "client")
    graph.create_node("api", "API Service", "service")
    graph.create_node("db", "PostgreSQL", "database")
    graph.add_edge("browser", "api", "requests")
    graph.add_edge("api", "db", "writes")
    graph.set_entry_point("browser")
    return graph


def test_analyze_without_llm_returns_valid_schema():
    graph = _build_graph()
    agent = AnalysisAgent(llm=None)

    output = asyncio.run(agent.analyze(
        graph=graph,
        transcript="Browser sends requests to API, API writes to PostgreSQL.",
        session_metadata={"duration_ms": 120000, "frames_processed": 8, "agent_responses": 8},
    ))

    assert set(output.keys()) == {"analysis", "feedback", "score"}

    analysis = output["analysis"]
    assert isinstance(analysis["architecture_pattern"], str)
    assert isinstance(analysis["component_count"], int)
    assert isinstance(analysis["identified_components"], list)
    assert analysis["connection_density"] in {"sparse", "moderate", "dense"}
    assert analysis["entry_point"] == "Browser"

    feedback = output["feedback"]
    assert isinstance(feedback["strengths"], list)
    assert isinstance(feedback["improvements"], list)
    assert isinstance(feedback["critical_gaps"], list)
    assert isinstance(feedback["narrative"], str)

    score = output["score"]
    assert 0 <= score["total"] <= 100
    assert score["grade"] in {"A", "B", "C", "D", "F"}
    assert set(score["breakdown"].keys()) == {"completeness", "scalability", "reliability", "clarity"}
    assert all(0 <= score["breakdown"][k] <= 25 for k in score["breakdown"])


def test_analyze_uses_llm_json_when_parseable():
    graph = _build_graph()
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(
        content=(
            '{"analysis":{"architecture_pattern":"3-tier web architecture",'
            '"component_count":3,"identified_components":["Browser","API Service","PostgreSQL"],'
            '"connection_density":"moderate","entry_point":"Browser",'
            '"disconnected_components":[],"bottlenecks":["PostgreSQL"],'
            '"missing_standard_components":["Cache layer"],'
            '"summary":"Solid baseline with clear layering."},'
            '"feedback":{"strengths":["Layered architecture is clear."],'
            '"improvements":["Add Redis cache for read-heavy paths."],'
            '"critical_gaps":[],"narrative":"Nice foundation; add caching next."},'
            '"score":{"total":82,"breakdown":{"completeness":21,"scalability":20,'
            '"reliability":20,"clarity":21},"grade":"B"}}'
        )
    ))
    agent = AnalysisAgent(llm=mock_llm)

    output = asyncio.run(agent.analyze(
        graph=graph,
        transcript="Candidate discussed adding Redis later.",
        session_metadata={"duration_ms": 60000},
    ))

    assert output["analysis"]["architecture_pattern"] == "3-tier web architecture"
    assert output["analysis"]["component_count"] == 3
    assert output["score"]["total"] == 82
    assert output["score"]["grade"] == "B"
    assert mock_llm.ainvoke.call_count == 1


def test_analyze_invalid_llm_payload_falls_back_to_heuristics():
    graph = _build_graph()
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="not json at all"))
    agent = AnalysisAgent(llm=mock_llm)

    output = asyncio.run(agent.analyze(
        graph=graph,
        transcript="We have browser -> api -> database.",
        session_metadata=None,
    ))

    assert set(output.keys()) == {"analysis", "feedback", "score"}
    assert output["analysis"]["component_count"] == 3
    assert output["score"]["total"] >= 0
    assert output["score"]["grade"] in {"A", "B", "C", "D", "F"}
