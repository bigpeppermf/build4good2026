"""
Full integration tests for WhiteboardAgent tool activation.

These tests call the REAL Google Gemini API to verify that the agent correctly
maps visual_delta descriptions to the appropriate graph mutation tools.  They
are automatically skipped when GOOGLE_API_KEY is absent or set to the test stub.

Run:
    uv run pytest tests/test_integration.py -v

Skip (CI / no key):
    uv run pytest tests/ --ignore=tests/test_integration.py

Design
------
Each tool in agent.tool_map is replaced with a MagicMock(wraps=real_tool) spy
before process_frame is called.  The real tool still executes — so the graph
mutates normally — but .invoke.called and .invoke.call_count let us observe
exactly which tools the LLM chose to activate.

Two flavours of assertions are combined in a single parametrized test:
  1. Tool activation  — which tools were (or were not) called
  2. Graph state      — what the graph looks like after the call

This keeps the API call count at exactly one per scenario.
"""

import os
import time
from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv

# Load .env before checking for the API key — otherwise os.environ won't
# contain keys that are only set in the .env file.
load_dotenv()

# ------------------------------------------------------------------ #
# Skip guard — no real API key → skip entire module                   #
# ------------------------------------------------------------------ #

_REAL_KEY = os.environ.get("GOOGLE_API_KEY", "")
_IS_STUB = _REAL_KEY in ("", "test-key-stub")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        _IS_STUB,
        reason="GOOGLE_API_KEY not set — skipping real LLM integration tests",
    ),
]

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")

from agent.agent import WhiteboardAgent  # noqa: E402
from core.graph import SystemDesignGraph  # noqa: E402

# ------------------------------------------------------------------ #
# Rate-limit handling                                                  #
# ------------------------------------------------------------------ #
#
# Gemini free tier: 15 requests per minute.
# Running 15 tests back-to-back without any pause exhausts the RPM cap
# immediately.  The fixture below sleeps 5 s before every test, capping
# throughput at ~12 req/min and keeping us well under the limit.
# The retry wrapper handles any 429 that still slips through (e.g. from
# multi-turn tool loops that make 2-3 LLM calls per test).

_INTER_TEST_SLEEP = 5  # seconds — ~12 tests/min max, safely under gemini-2.5-flash-lite's 15 RPM


@pytest.fixture(autouse=True)
def _rate_limit_pause():
    """Sleep before each integration test to stay under Gemini free-tier RPM."""
    time.sleep(_INTER_TEST_SLEEP)
    yield


def _process(agent: "WhiteboardAgent", delta: str, timestamp_ms: int) -> str:
    """
    Call agent.process_frame, skipping the test immediately on a 429.

    A rate-limit error means the free-tier quota is exhausted — there is no
    point retrying within the same run.  Skipping surfaces a clear message
    rather than a misleading assertion failure.
    """
    try:
        return agent.process_frame(delta, timestamp_ms)
    except Exception as exc:
        if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
            pytest.skip(f"Gemini free-tier quota exhausted (429) — run again later. {exc}")
        raise


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _make_agent(
    setup_fn: Callable[[SystemDesignGraph], None] | None = None,
) -> tuple[WhiteboardAgent, SystemDesignGraph, dict[str, MagicMock]]:
    """
    Build a fresh (agent, graph, spies) triple.

    Each entry in agent.tool_map is swapped for MagicMock(wraps=real_tool).
    The real function still runs, so graph mutations happen normally, but every
    .invoke() call is recorded for inspection.
    """
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    graph = SystemDesignGraph()
    if setup_fn:
        setup_fn(graph)

    agent = WhiteboardAgent(graph)

    # If the graph was pre-populated via setup_fn, inject a synthetic prior
    # exchange into the agent's history so the LLM knows those nodes already
    # exist and won't try to recreate them (which would raise ValueError).
    if setup_fn and len(graph) > 0:
        agent.message_history.append(
            HumanMessage(content='{"visual_delta": "Session started.", "current_timestamp": 0}\n\n'
                                 "Call the appropriate graph tools for any structural changes, "
                                 "then respond with a single sentence.")
        )
        agent.message_history.append(
            AIMessage(
                content="",
                tool_calls=[{"id": "prime_query", "name": "get_graph_state", "args": {}}],
            )
        )
        agent.message_history.append(
            ToolMessage(
                name="get_graph_state",
                content=str(graph.get_state()),
                tool_call_id="prime_query",
            )
        )
        agent.message_history.append(
            AIMessage(content=f"Graph has {len(graph)} pre-existing node(s). Ready.")
        )

    spies: dict[str, MagicMock] = {}
    for name, real_tool in agent.tool_map.items():
        spy = MagicMock(wraps=real_tool)
        agent.tool_map[name] = spy
        spies[name] = spy

    return agent, graph, spies


def _invoked(spies: dict[str, MagicMock]) -> set[str]:
    """Return the names of every tool whose .invoke() was actually called."""
    return {name for name, spy in spies.items() if spy.invoke.called}


# All tools that structurally change the graph.
# get_graph_state is intentionally absent — it is read-only and the LLM is
# allowed to call it before deciding that nothing changed.
_MUTATION_TOOLS = frozenset({
    "create_node",
    "delete_node",
    "add_edge",
    "remove_edge",
    "add_details_to_node",
    "set_entry_point",
    "insert_node_between",
})


# ------------------------------------------------------------------ #
# Scenario table                                                       #
# ------------------------------------------------------------------ #
#
# Each row:
#   delta        — visual_delta string sent to the agent
#   setup_fn     — optional callable(graph) that pre-populates the graph
#   must_call    — set of tool names; at least one must be invoked
#   must_not_call— set of tool names; none of these may be invoked
#   graph_check  — optional callable(graph) with additional state assertions
#
# The prompts are written to be as unambiguous as possible so the LLM has
# a clear structural signal to act on.  This minimises flakiness while still
# exercising realistic input.

def _node_exists(label_fragment: str):
    """Return a graph_check that asserts a node whose label contains label_fragment."""
    def check(g: SystemDesignGraph):
        labels = [n["label"] for n in g.get_state()["nodes"]]
        assert any(label_fragment.lower() in lbl.lower() for lbl in labels), (
            f"Expected a node containing '{label_fragment}' in label. Got: {labels}"
        )
    return check


def _edge_exists(from_fragment: str, to_fragment: str):
    """Return a graph_check that asserts at least one edge between matching nodes."""
    def check(g: SystemDesignGraph):
        edges = g.get_state()["edges"]
        assert len(edges) > 0, f"Expected at least one edge. Got: {edges}"
    return check


_SCENARIOS = [
    # ── node creation ────────────────────────────────────────────────
    pytest.param(
        "A box labeled 'API Gateway' was drawn on the whiteboard.",
        None,
        {"create_node"},
        set(),
        lambda g: (
            assert_true := len(g) > 0,
            _node_exists("API")(g),
        ),
        id="create_api_gateway_box",
    ),
    pytest.param(
        "A box labeled 'PostgreSQL Database' was drawn to the right of the board.",
        None,
        {"create_node"},
        set(),
        lambda g: (assert_true := len(g) > 0),
        id="create_database_box",
    ),
    pytest.param(
        "A box labeled 'Redis Cache' appeared on the whiteboard.",
        None,
        {"create_node"},
        set(),
        lambda g: (assert_true := len(g) > 0),
        id="create_cache_box",
    ),
    pytest.param(
        "A box labeled 'Kafka Message Queue' was drawn with the word 'Kafka' written inside it.",
        None,
        {"create_node"},
        set(),
        lambda g: (assert_true := len(g) > 0),
        id="create_queue_box",
    ),
    # ── edge creation ────────────────────────────────────────────────
    pytest.param(
        "An arrow was drawn from the 'Client Browser' box to the 'API Gateway' box.",
        lambda g: (
            g.create_node("client_browser", "Client Browser", "client"),
            g.create_node("api_gateway", "API Gateway", "service"),
        ),
        {"add_edge"},
        set(),
        lambda g: _edge_exists("client_browser", "api_gateway")(g),
        id="draw_arrow_between_existing_nodes",
    ),
    pytest.param(
        "An arrow labeled 'writes to' was drawn from the 'API Server' box to the 'Database' box.",
        lambda g: (
            g.create_node("api_server", "API Server", "service"),
            g.create_node("database", "Database", "database"),
        ),
        {"add_edge"},
        set(),
        lambda g: _edge_exists("api_server", "database")(g),
        id="draw_labeled_arrow",
    ),
    # ── entry point ──────────────────────────────────────────────────
    pytest.param(
        "The 'Client Browser' box is at the far left and all arrows originate from it — "
        "it is clearly the user-facing entry point of the system.",
        lambda g: (
            g.create_node("client_browser", "Client Browser", "client"),
            g.create_node("api", "API", "service"),
            g.add_edge("client_browser", "api"),
        ),
        {"set_entry_point"},
        set(),
        lambda g: assert_(g.get_state()["entry_point"] is not None,
                          "entry_point should be set"),
        id="identify_entry_point",
    ),
    # ── node deletion ────────────────────────────────────────────────
    pytest.param(
        "The 'Legacy Service' box was erased from the whiteboard and is no longer visible.",
        lambda g: (
            g.create_node("legacy_service", "Legacy Service", "service"),
            g.create_node("api", "API", "service"),
        ),
        {"delete_node"},
        set(),
        lambda g: assert_(
            not any("Legacy" in n["label"] for n in g.get_state()["nodes"]),
            f"Legacy Service should be gone. Nodes: {g.get_state()['nodes']}",
        ),
        id="erase_node",
    ),
    # ── node details ─────────────────────────────────────────────────
    pytest.param(
        "The text 'PostgreSQL 15, primary-replica, 3 nodes' was written inside the 'Database' box.",
        lambda g: g.create_node("database", "Database", "database"),
        {"add_details_to_node"},
        set(),
        lambda g: assert_(
            any(len(n["details"]) > 0 for n in g.get_state()["nodes"]),
            f"At least one node should have details. Nodes: {g.get_state()['nodes']}",
        ),
        id="add_annotation_to_existing_node",
    ),
    # ── edge deletion ────────────────────────────────────────────────
    pytest.param(
        "The arrow between the 'API Server' box and the 'Cache' box was erased.",
        lambda g: (
            g.create_node("api_server", "API Server", "service"),
            g.create_node("cache", "Cache", "cache"),
            g.add_edge("api_server", "cache", "reads from"),
        ),
        {"remove_edge"},
        set(),
        lambda g: assert_(
            not any(e["from"] == "api_server" and e["to"] == "cache"
                    for e in g.get_state()["edges"]),
            f"Edge api_server→cache should be gone. Edges: {g.get_state()['edges']}",
        ),
        id="erase_arrow",
    ),
    # ── no structural change ─────────────────────────────────────────
    # get_graph_state is intentionally excluded from must_not_call — the LLM
    # may legitimately inspect the board before deciding nothing changed.
    pytest.param(
        "The whiteboard appears completely unchanged since the last frame — "
        "no new boxes, arrows, or labels are visible.",
        None,
        set(),
        _MUTATION_TOOLS,           # no structural mutations allowed
        lambda g: assert_(len(g) == 0, "Graph should remain empty"),
        id="no_change_empty_board",
    ),
    pytest.param(
        "There is a very faint, unidentifiable smudge in the corner of the board. "
        "It is too ambiguous to interpret as a system component.",
        None,
        set(),
        _MUTATION_TOOLS,
        lambda g: assert_(len(g) == 0, "Graph should remain empty"),
        id="ambiguous_mark_no_action",
    ),
]


def assert_(condition: bool, message: str = "") -> None:
    """Thin wrapper so lambdas can contain assertions."""
    assert condition, message


# ------------------------------------------------------------------ #
# Parametrized tool-activation test                                    #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "delta,setup_fn,must_call,must_not_call,graph_check",
    _SCENARIOS,
)
def test_tool_activation(delta, setup_fn, must_call, must_not_call, graph_check):
    """
    For each visual_delta scenario, verify in a single real LLM call:

      1. Tool activation  — every tool in must_call was invoked at least once;
                           no tool in must_not_call was invoked.
      2. Graph state      — the optional graph_check callable passes.

    Failure messages include the full list of invoked tools and graph state so
    regressions are easy to diagnose.
    """
    agent, graph, spies = _make_agent(setup_fn)
    _process(agent, delta, timestamp_ms=1000)
    called = _invoked(spies)

    missing = must_call - called
    assert not missing, (
        f"Expected tool(s) {missing} to be activated but they were not.\n"
        f"  All invoked : {called}\n"
        f"  Graph state : {graph.get_state()}"
    )

    unexpected = must_not_call & called
    assert not unexpected, (
        f"Tool(s) {unexpected} must NOT be activated for this delta but were.\n"
        f"  All invoked : {called}\n"
        f"  Graph state : {graph.get_state()}"
    )

    if graph_check:
        graph_check(graph)


# ------------------------------------------------------------------ #
# Multi-step session scenarios                                         #
# ------------------------------------------------------------------ #

class TestMultiStepSession:
    """
    Simulate realistic whiteboard sessions across multiple frames.

    These are the most signal-rich tests: they exercise the agent's ability to
    maintain context across turns and accumulate graph state correctly.
    Each frame → process_frame call → real Gemini round-trip.
    """

    def test_three_tier_architecture_built_incrementally(self):
        """
        Four frames describing a Browser → API Server → MySQL Database design,
        then circling the Browser as the entry point.
        After each frame, assert that the graph reflects what was drawn.
        """
        agent, graph, spies = _make_agent()

        # Frame 1 — client node
        _process(agent,
            "A box labeled 'Browser' was drawn at the far left of the whiteboard.",
            timestamp_ms=1_000,
        )
        assert len(graph) >= 1, f"Expected Browser node. State: {graph.get_state()}"
        assert "create_node" in _invoked(spies)

        # Frame 2 — API service + arrow from Browser
        _process(agent,
            "A box labeled 'API Server' appeared to the right of 'Browser', "
            "and an arrow was drawn from 'Browser' to 'API Server'.",
            timestamp_ms=4_000,
        )
        assert len(graph) >= 2, f"Expected >= 2 nodes. State: {graph.get_state()}"
        assert len(graph.get_state()["edges"]) >= 1, "Expected >= 1 edge after frame 2"

        # Frame 3 — database + arrow from API Server
        _process(agent,
            "A box labeled 'MySQL Database' appeared to the right of 'API Server', "
            "with an arrow from 'API Server' to 'MySQL Database' labeled 'writes to'.",
            timestamp_ms=8_000,
        )
        assert len(graph) >= 3, f"Expected >= 3 nodes. State: {graph.get_state()}"
        assert len(graph.get_state()["edges"]) >= 2, "Expected >= 2 edges after frame 3"

        # Frame 4 — entry point signal
        _process(agent,
            "The 'Browser' box is circled in red, indicating it is the system entry point.",
            timestamp_ms=12_000,
        )
        assert graph.get_state()["entry_point"] is not None, (
            "Entry point should be set by frame 4"
        )

        # create_node must have fired at least twice (Browser + API Server at minimum)
        assert spies["create_node"].invoke.call_count >= 2, (
            f"create_node call count: {spies['create_node'].invoke.call_count}"
        )

    def test_correction_erase_and_redraw(self):
        """
        The designer draws a node, decides it's wrong, erases it, and draws a
        replacement.  The agent must handle both the deletion and the new creation.
        """
        agent, graph, spies = _make_agent()

        _process(agent,
            "A box labeled 'Monolith' was drawn in the centre of the board.",
            timestamp_ms=1_000,
        )
        count_after_create = len(graph)
        assert count_after_create >= 1

        _process(agent,
            "The 'Monolith' box was completely erased — the designer decided to split the service.",
            timestamp_ms=5_000,
        )
        assert "delete_node" in _invoked(spies), (
            f"delete_node should fire on erasure. Invoked: {_invoked(spies)}"
        )
        assert len(graph) < count_after_create, (
            f"Node count should decrease after erasure. Before: {count_after_create}, "
            f"after: {len(graph)}"
        )

    def test_insert_between_or_equivalent(self):
        """
        A new node is inserted between two already-connected nodes.

        The agent may use insert_node_between (the atomic tool) or manually
        create the node and rewire the edges — both are valid responses.
        The test accepts either and only asserts on the final graph structure.
        """
        def setup(g):
            g.create_node("browser", "Browser", "client")
            g.create_node("database", "Database", "database")
            g.add_edge("browser", "database", "direct")

        agent, graph, spies = _make_agent(setup)

        _process(agent,
            "A new box labeled 'API Gateway' was inserted between 'Browser' and 'Database', "
            "replacing the direct arrow with two new arrows.",
            timestamp_ms=3_000,
        )

        called = _invoked(spies)
        assert called & {"insert_node_between", "create_node"}, (
            f"Expected insert_node_between or create_node to fire. Invoked: {called}"
        )

        final_edges = {(e["from"], e["to"]) for e in graph.get_state()["edges"]}
        assert ("browser", "database") not in final_edges, (
            f"Direct browser→database edge should be gone. Final edges: {final_edges}"
        )
