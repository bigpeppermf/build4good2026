"""
Real-time whiteboard analysis agent using LangChain + Google Gemini.

Architecture
------------
The agent runs in-process alongside the FastMCP server and shares the same
``SystemDesignGraph`` instance.  LangChain @tool wrappers around the graph
methods mirror every tool exposed on the MCP server (createNode, addEdge, etc.)
so the agent's tool calls are functionally identical to what the MCP protocol
would execute — without the HTTP round-trip that would deadlock a single-worker
Uvicorn process.

Input
-----
Visual only.  Periodic JPEG frames from the whiteboard camera are passed in as
raw bytes.  Audio is intentionally excluded.

Model
-----
Google Gemini 2.0 Flash via ``langchain-google-genai``.  The model has
multimodal vision capability and supports function/tool calling.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from core.graph import SystemDesignGraph

# ------------------------------------------------------------------ #
# System prompt                                                        #
# ------------------------------------------------------------------ #

SYSTEM_PROMPT = """\
You are a real-time system design analysis agent. You receive periodic JPEG
frames captured from a whiteboard where a user is sketching a system
architecture diagram.

Your job is to maintain an accurate graph representation of the system design
the user is building.  The graph is your source of truth.  Every time you
receive a new frame, determine what has changed and call the appropriate graph
mutation tool.

Available tools
---------------
- create_node(id, label, type)
    Call when a new component appears on the whiteboard (box drawn, label
    written, etc.).  Valid types: service, database, cache, load_balancer,
    queue, client, storage, external.

- add_details_to_node(id, details)
    Call when the user annotates an existing component with extra information
    (technology stack, role, scaling notes, etc.).

- delete_node(id)
    Call when a component is erased from the whiteboard.

- add_edge(from_id, to_id, label)
    Call when an arrow is drawn between two components.

- remove_edge(from_id, to_id)
    Call when an arrow is erased.

- set_entry_point(id)
    Call as soon as you identify the user-facing entry point of the system
    (Browser, Mobile App, CDN, etc.).  Do this early.

- insert_node_between(from_id, new_id, new_label, new_type, to_id, ...)
    Call when a new component is inserted between two already-connected nodes.
    Atomically removes the old edge and creates two new ones.

- get_graph_state()
    Call to inspect the current graph before making structural decisions that
    depend on existing topology.

Decision rules
--------------
1. Only call a tool when you have sufficient confidence that a structural change
   was intended.  Do not add nodes for vague, incomplete, or ambiguous sketches.
2. You may call multiple tools in one turn if the frame shows multiple changes.
3. If the frame shows no visible changes from the graph's current state, do not
   call any tools.
4. Never fabricate nodes or edges.  Every mutation must be grounded in something
   you visually observe in the frame.
5. If you have received two or more consecutive frames with no structural
   changes, respond with a Socratic question about the most critical missing
   component in the current design.

Response format
---------------
After any tool calls, produce exactly one sentence spoken aloud to the user —
either confirming what you understood or asking a clarifying question.
"""

# ------------------------------------------------------------------ #
# LangChain tool factory                                               #
# ------------------------------------------------------------------ #


def _build_tools(graph: SystemDesignGraph) -> list[Any]:
    """
    Create LangChain @tool functions that mutate the shared graph instance.

    Each tool mirrors its counterpart on the MCP server so that the agent's
    calls are functionally equivalent to what the MCP protocol would execute.
    """

    @tool
    def create_node(id: str, label: str, type: str) -> dict:  # noqa: A002
        """Register a new system component on the graph when it appears on the whiteboard.

        Args:
            id: Unique snake_case identifier (e.g. 'api_gateway').
            label: Human-readable name as drawn (e.g. 'API Gateway').
            type: One of: service, database, cache, load_balancer, queue,
                  client, storage, external.
        """
        node = graph.create_node(id=id, label=label, type=type)
        return {"status": "created", "node": {"id": node.id, "label": node.label, "type": node.type}}

    @tool
    def add_details_to_node(id: str, details: dict) -> dict:  # noqa: A002
        """Add descriptive details to an existing node.

        Args:
            id: ID of the node to annotate.
            details: Key-value pairs
                (e.g. {"technology": "PostgreSQL", "role": "primary write store"}).
        """
        node = graph.add_details_to_node(id=id, details=details)
        return {"status": "updated", "node": {"id": node.id, "details": node.details}}

    @tool
    def delete_node(id: str) -> dict:  # noqa: A002
        """Remove a component and all its edges when it is erased from the whiteboard.

        Args:
            id: ID of the node to delete.
        """
        graph.delete_node(id=id)
        return {"status": "deleted", "id": id}

    @tool
    def add_edge(from_id: str, to_id: str, label: str = "") -> dict:
        """Create a directed connection between two components when an arrow is drawn.

        Args:
            from_id: Source node ID.
            to_id: Destination node ID.
            label: Optional relationship label
                (e.g. 'routes traffic to', 'writes to', 'publishes events').
        """
        edge = graph.add_edge(from_id=from_id, to_id=to_id, label=label)
        return {"status": "added", "edge": {"from": edge.from_id, "to": edge.to_id, "label": edge.label}}

    @tool
    def remove_edge(from_id: str, to_id: str) -> dict:
        """Remove a directed connection when an arrow is erased.

        Args:
            from_id: Source node ID.
            to_id: Destination node ID.
        """
        graph.remove_edge(from_id=from_id, to_id=to_id)
        return {"status": "removed", "from": from_id, "to": to_id}

    @tool
    def set_entry_point(id: str) -> dict:  # noqa: A002
        """Designate the logical entry point of the system (user-facing start).
        Call this as soon as you identify it.

        Args:
            id: ID of the entry-point node (e.g. 'browser', 'mobile_app', 'cdn').
        """
        graph.set_entry_point(id=id)
        return {"status": "entry_point_set", "entry_point": id}

    @tool
    def insert_node_between(
        from_id: str,
        new_id: str,
        new_label: str,
        new_type: str,
        to_id: str,
        from_label: str = "",
        to_label: str = "",
    ) -> dict:
        """Insert a new node between two already-connected nodes.

        Removes the direct edge from_id→to_id and creates two new edges:
        from_id→new_id and new_id→to_id.

        Args:
            from_id: ID of the upstream node.
            new_id: Unique ID for the new node.
            new_label: Human-readable label for the new node.
            new_type: Component type for the new node.
            to_id: ID of the downstream node.
            from_label: Optional label for the upstream edge.
            to_label: Optional label for the downstream edge.
        """
        node = graph.insert_node_between(
            from_id=from_id,
            new_id=new_id,
            new_label=new_label,
            new_type=new_type,
            to_id=to_id,
            from_label=from_label,
            to_label=to_label,
        )
        return {"status": "inserted", "node": {"id": node.id, "label": node.label, "type": node.type}}

    @tool
    def get_graph_state() -> dict:
        """Return the full current state of the graph (all nodes and edges).
        Call this to verify your understanding before structural decisions.
        """
        return graph.get_state()

    return [
        create_node,
        add_details_to_node,
        delete_node,
        add_edge,
        remove_edge,
        set_entry_point,
        insert_node_between,
        get_graph_state,
    ]


# ------------------------------------------------------------------ #
# Agent                                                                #
# ------------------------------------------------------------------ #


class WhiteboardAgent:
    """
    Stateful LangChain agent for real-time whiteboard frame analysis.

    One instance is shared for the lifetime of a session.  The conversation
    history persists across frames so the model maintains context between
    snapshots.

    Audio input is intentionally excluded; analysis is visual-only.
    """

    def __init__(self, graph: SystemDesignGraph) -> None:
        self.graph = graph
        self.llm = ChatGoogleGenerativeAI(
            # gemini-2.0-flash: fast multimodal model with vision and tool-calling.
            # Equivalent to the "Nano" tier available via the Google AI API.
            model="gemini-2.0-flash",
            temperature=0,
            google_api_key=os.environ["GOOGLE_API_KEY"],
        )
        self.tools = _build_tools(graph)
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        self.tool_map: dict[str, Any] = {t.name: t for t in self.tools}

        # Conversation history persists across all frames in a session.
        self.message_history: list = [SystemMessage(content=SYSTEM_PROMPT)]
        # Count consecutive frames with no graph mutations for Socratic prompting.
        self.no_change_streak: int = 0

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def process_frame(self, frame_jpeg: bytes, timestamp_ms: int) -> str:
        """
        Analyze a single whiteboard JPEG frame and apply graph mutations.

        The method runs the full agentic tool-call loop synchronously:
        it keeps sending the conversation back to Gemini until the model
        returns a response with no further tool calls.

        Args:
            frame_jpeg:   Raw JPEG bytes of the whiteboard frame.
            timestamp_ms: Milliseconds since session start.

        Returns:
            One-sentence verbal response suitable for TTS output.
        """
        image_b64 = base64.b64encode(frame_jpeg).decode()

        human_msg = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        f"[t={timestamp_ms}ms] Analyze this whiteboard frame. "
                        "Call the appropriate graph tools for any structural changes you see, "
                        "then respond with a single sentence."
                    ),
                },
                {
                    "type": "media",
                    "data": image_b64,
                    "mime_type": "image/jpeg",
                },
            ]
        )

        self.message_history.append(human_msg)

        # Agentic loop: keep invoking until the model stops requesting tool calls.
        while True:
            response = self.llm_with_tools.invoke(self.message_history)
            self.message_history.append(response)

            if not response.tool_calls:
                # Final verbal response — no more tool calls.
                self.no_change_streak += 1
                return response.content or "I'm watching the board — keep going."

            # Execute every tool call and feed results back into the conversation.
            tool_messages: list[ToolMessage] = []
            for call in response.tool_calls:
                fn = self.tool_map.get(call["name"])
                if fn is None:
                    continue
                result = fn.invoke(call["args"])
                tool_messages.append(
                    ToolMessage(
                        name=call["name"],
                        content=str(result),
                        tool_call_id=call["id"],
                    )
                )

            self.message_history.extend(tool_messages)
            self.no_change_streak = 0
            # Loop: let the model see the tool results and decide next action.

    def reset(self) -> None:
        """Clear conversation history and streak counter for a new session."""
        self.message_history = [SystemMessage(content=SYSTEM_PROMPT)]
        self.no_change_streak = 0
