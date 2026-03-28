"""
Integration tests for agent/agent.py — WhiteboardAgent.

The LLM is replaced with a MagicMock so these tests run without a
GOOGLE_API_KEY.  Each test controls exactly what the model "returns"
and then verifies that the agent's tool-call loop correctly mutated
the shared SystemDesignGraph.

The agent receives plain-text visual_delta strings, NOT raw images.
Raw frame analysis is handled upstream by the CV pipeline.
"""

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent.agent import WhiteboardAgent
from core.graph import SystemDesignGraph

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

SAMPLE_DELTA = "A box labeled 'API Gateway' was drawn with an arrow pointing to 'Database'."


def tool_response(tool_name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    """Simulate an AIMessage that requests a single tool call."""
    return AIMessage(
        content="",
        tool_calls=[{"id": call_id, "name": tool_name, "args": args}],
    )


def multi_tool_response(*calls: tuple[str, dict]) -> AIMessage:
    """Simulate an AIMessage that requests multiple tool calls at once."""
    return AIMessage(
        content="",
        tool_calls=[
            {"id": f"call_{i}", "name": name, "args": args}
            for i, (name, args) in enumerate(calls)
        ],
    )


def text_response(text: str) -> AIMessage:
    """Simulate a final AIMessage with no tool calls (verbal output)."""
    return AIMessage(content=text)


def make_agent() -> tuple[WhiteboardAgent, SystemDesignGraph]:
    """Create a fresh agent + graph pair for each test."""
    graph = SystemDesignGraph()
    agent = WhiteboardAgent(graph)
    agent.llm_with_tools = MagicMock()
    return agent, graph


# ------------------------------------------------------------------ #
# Tool-call loop: single tool                                          #
# ------------------------------------------------------------------ #

class TestSingleToolCall:
    def test_create_node_mutates_graph(self):
        agent, graph = make_agent()
        agent.llm_with_tools.invoke.side_effect = [
            tool_response("create_node", {"id": "api", "label": "API Gateway", "type": "service"}),
            text_response("Got it — I added the API Gateway."),
        ]

        response = agent.process_frame(SAMPLE_DELTA, 1000)

        node_ids = [n["id"] for n in graph.get_state()["nodes"]]
        assert "api" in node_ids
        assert response == "Got it — I added the API Gateway."

    def test_add_edge_mutates_graph(self):
        agent, graph = make_agent()
        graph.create_node("client", "Client", "client")
        graph.create_node("api", "API", "service")

        agent.llm_with_tools.invoke.side_effect = [
            tool_response("add_edge", {"from_id": "client", "to_id": "api", "label": "HTTP"}),
            text_response("Connected client to API."),
        ]

        agent.process_frame(SAMPLE_DELTA, 2000)

        edges = graph.get_state()["edges"]
        assert any(e["from"] == "client" and e["to"] == "api" for e in edges)

    def test_set_entry_point_mutates_graph(self):
        agent, graph = make_agent()
        graph.create_node("browser", "Browser", "client")

        agent.llm_with_tools.invoke.side_effect = [
            tool_response("set_entry_point", {"id": "browser"}),
            text_response("Entry point set."),
        ]

        agent.process_frame(SAMPLE_DELTA, 500)

        assert graph.get_state()["entry_point"] == "browser"

    def test_delete_node_mutates_graph(self):
        agent, graph = make_agent()
        graph.create_node("old", "Old Service", "service")

        agent.llm_with_tools.invoke.side_effect = [
            tool_response("delete_node", {"id": "old"}),
            text_response("Removed the old service."),
        ]

        agent.process_frame(SAMPLE_DELTA, 3000)

        assert "old" not in [n["id"] for n in graph.get_state()["nodes"]]

    def test_add_details_to_node_mutates_graph(self):
        agent, graph = make_agent()
        graph.create_node("db", "Database", "database")

        agent.llm_with_tools.invoke.side_effect = [
            tool_response("add_details_to_node", {
                "id": "db",
                "details": {"technology": "PostgreSQL"},
            }),
            text_response("Noted — PostgreSQL database."),
        ]

        agent.process_frame(SAMPLE_DELTA, 4000)

        node = next(n for n in graph.get_state()["nodes"] if n["id"] == "db")
        assert node["details"]["technology"] == "PostgreSQL"

    def test_remove_edge_mutates_graph(self):
        agent, graph = make_agent()
        graph.create_node("a", "A", "service")
        graph.create_node("b", "B", "service")
        graph.add_edge("a", "b")

        agent.llm_with_tools.invoke.side_effect = [
            tool_response("remove_edge", {"from_id": "a", "to_id": "b"}),
            text_response("Edge removed."),
        ]

        agent.process_frame(SAMPLE_DELTA, 5000)

        assert not any(e["from"] == "a" and e["to"] == "b"
                       for e in graph.get_state()["edges"])

    def test_insert_node_between_mutates_graph(self):
        agent, graph = make_agent()
        graph.create_node("client", "Client", "client")
        graph.create_node("db", "Database", "database")
        graph.add_edge("client", "db")

        agent.llm_with_tools.invoke.side_effect = [
            tool_response("insert_node_between", {
                "from_id": "client",
                "new_id": "api",
                "new_label": "API",
                "new_type": "service",
                "to_id": "db",
            }),
            text_response("Inserted API between client and database."),
        ]

        agent.process_frame(SAMPLE_DELTA, 6000)

        ids = [n["id"] for n in graph.get_state()["nodes"]]
        assert "api" in ids
        edges = graph.get_state()["edges"]
        assert not any(e["from"] == "client" and e["to"] == "db" for e in edges)
        assert any(e["from"] == "client" and e["to"] == "api" for e in edges)
        assert any(e["from"] == "api" and e["to"] == "db" for e in edges)

    def test_get_graph_state_does_not_mutate_graph(self):
        agent, graph = make_agent()
        graph.create_node("existing", "Existing", "service")

        agent.llm_with_tools.invoke.side_effect = [
            tool_response("get_graph_state", {}),
            text_response("I can see one node in the graph."),
        ]

        agent.process_frame(SAMPLE_DELTA, 7000)

        assert len(graph) == 1


# ------------------------------------------------------------------ #
# Tool-call loop: multiple tools in one turn                           #
# ------------------------------------------------------------------ #

class TestMultipleToolCallsInOneTurn:
    def test_two_nodes_created_in_one_response(self):
        agent, graph = make_agent()

        agent.llm_with_tools.invoke.side_effect = [
            multi_tool_response(
                ("create_node", {"id": "lb", "label": "Load Balancer", "type": "load_balancer"}),
                ("create_node", {"id": "api", "label": "API", "type": "service"}),
            ),
            text_response("Added load balancer and API."),
        ]

        agent.process_frame(SAMPLE_DELTA, 1000)

        ids = [n["id"] for n in graph.get_state()["nodes"]]
        assert "lb" in ids
        assert "api" in ids

    def test_node_and_edge_created_in_one_response(self):
        agent, graph = make_agent()
        graph.create_node("client", "Client", "client")

        agent.llm_with_tools.invoke.side_effect = [
            multi_tool_response(
                ("create_node", {"id": "api", "label": "API", "type": "service"}),
                ("add_edge", {"from_id": "client", "to_id": "api", "label": "calls"}),
            ),
            text_response("Added API and connected client to it."),
        ]

        agent.process_frame(SAMPLE_DELTA, 1000)

        ids = [n["id"] for n in graph.get_state()["nodes"]]
        assert "api" in ids
        edges = graph.get_state()["edges"]
        assert any(e["from"] == "client" and e["to"] == "api" for e in edges)


# ------------------------------------------------------------------ #
# No-tool-call (no change) path                                        #
# ------------------------------------------------------------------ #

class TestNoToolCalls:
    def test_verbal_response_returned_directly(self):
        agent, graph = make_agent()

        agent.llm_with_tools.invoke.return_value = text_response(
            "What type of database are you planning to use?"
        )

        response = agent.process_frame(SAMPLE_DELTA, 1000)
        assert response == "What type of database are you planning to use?"

    def test_empty_content_returns_fallback_string(self):
        agent, _ = make_agent()
        agent.llm_with_tools.invoke.return_value = AIMessage(content="")

        response = agent.process_frame(SAMPLE_DELTA, 1000)
        assert isinstance(response, str)
        assert len(response) > 0


# ------------------------------------------------------------------ #
# Conversation history                                                 #
# ------------------------------------------------------------------ #

class TestConversationHistory:
    def test_history_starts_with_system_message(self):
        _, graph = make_agent()
        agent = WhiteboardAgent(graph)
        assert isinstance(agent.message_history[0], SystemMessage)

    def test_history_grows_after_frame(self):
        agent, _ = make_agent()
        agent.llm_with_tools.invoke.return_value = text_response("I see the board.")
        initial_len = len(agent.message_history)

        agent.process_frame(SAMPLE_DELTA, 1000)

        assert len(agent.message_history) > initial_len

    def test_human_message_contains_visual_delta(self):
        agent, _ = make_agent()
        agent.llm_with_tools.invoke.return_value = text_response("OK.")

        agent.process_frame(SAMPLE_DELTA, 1000)

        human_msgs = [m for m in agent.message_history if isinstance(m, HumanMessage)]
        assert len(human_msgs) == 1
        assert SAMPLE_DELTA in human_msgs[0].content

    def test_history_accumulates_across_frames(self):
        agent, _ = make_agent()
        agent.llm_with_tools.invoke.return_value = text_response("OK.")

        agent.process_frame(SAMPLE_DELTA, 1000)
        len_after_first = len(agent.message_history)

        agent.process_frame(SAMPLE_DELTA, 2000)
        assert len(agent.message_history) > len_after_first

    def test_tool_messages_added_to_history(self):
        agent, graph = make_agent()
        graph.create_node("svc", "Service", "service")

        agent.llm_with_tools.invoke.side_effect = [
            tool_response("get_graph_state", {}, call_id="tc_001"),
            text_response("I can see the service node."),
        ]

        agent.process_frame(SAMPLE_DELTA, 1000)

        tool_msgs = [m for m in agent.message_history if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].tool_call_id == "tc_001"


# ------------------------------------------------------------------ #
# reset()                                                              #
# ------------------------------------------------------------------ #

class TestReset:
    def test_reset_clears_history_to_system_message_only(self):
        agent, _ = make_agent()
        agent.llm_with_tools.invoke.return_value = text_response("OK.")
        agent.process_frame(SAMPLE_DELTA, 1000)

        agent.reset()

        assert len(agent.message_history) == 1
        assert isinstance(agent.message_history[0], SystemMessage)

