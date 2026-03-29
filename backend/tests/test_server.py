"""
Integration tests for the HTTP endpoints in graph_mcp/server.py.

Uses Starlette's TestClient (synchronous, no real network needed).
These tests do NOT require GOOGLE_API_KEY or MONGODB_URI — they exercise
only the request validation layer, session lifecycle, and routes that return
early (400/404 responses) before touching external services.
"""

import os

import pytest

# Provide stub env vars before the server module is imported so that
# ChatGoogleGenerativeAI and Motor do not raise on missing keys.
os.environ.setdefault("GOOGLE_API_KEY", "test-key-stub")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")

from starlette.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def create_session() -> str:
    """Create a new session and return its session_id."""
    res = client.post("/new-session")
    assert res.status_code == 200
    return res.json()["session_id"]


# ------------------------------------------------------------------ #
# GET /docs                                                            #
# ------------------------------------------------------------------ #

class TestDocsEndpoint:
    def test_returns_200(self):
        res = client.get("/docs")
        assert res.status_code == 200

    def test_content_type_is_html(self):
        res = client.get("/docs")
        assert "text/html" in res.headers["content-type"]

    def test_body_contains_api_reference_heading(self):
        res = client.get("/docs")
        assert "API Reference" in res.text

    def test_body_contains_graph_tools_section(self):
        res = client.get("/docs")
        assert "Graph Tools" in res.text or "create_node" in res.text


# ------------------------------------------------------------------ #
# POST /new-session                                                    #
# ------------------------------------------------------------------ #

class TestNewSessionEndpoint:
    def test_returns_200(self):
        res = client.post("/new-session")
        assert res.status_code == 200

    def test_returns_session_id(self):
        res = client.post("/new-session")
        assert "session_id" in res.json()
        assert len(res.json()["session_id"]) > 0

    def test_each_call_returns_unique_session_id(self):
        id1 = client.post("/new-session").json()["session_id"]
        id2 = client.post("/new-session").json()["session_id"]
        assert id1 != id2

    def test_multiple_active_sessions_coexist(self):
        ids = {client.post("/new-session").json()["session_id"] for _ in range(5)}
        assert len(ids) == 5


# ------------------------------------------------------------------ #
# POST /agent/process-frame                                            #
# ------------------------------------------------------------------ #

class TestProcessFrameEndpoint:
    def test_missing_session_id_returns_404(self):
        res = client.post(
            "/agent/process-frame",
            json={"visual_delta": "something", "timestamp_ms": 100},
        )
        assert res.status_code == 404
        assert "session_id" in res.json()["error"].lower()

    def test_invalid_session_id_returns_404(self):
        res = client.post(
            "/agent/process-frame",
            json={"session_id": "not-a-real-id", "visual_delta": "something"},
        )
        assert res.status_code == 404

    def test_missing_visual_delta_returns_400(self):
        sid = create_session()
        res = client.post(
            "/agent/process-frame",
            json={"session_id": sid, "timestamp_ms": 100},
        )
        assert res.status_code == 400
        assert "visual_delta" in res.json()["error"].lower()

    def test_empty_visual_delta_returns_400(self):
        sid = create_session()
        res = client.post(
            "/agent/process-frame",
            json={"session_id": sid, "visual_delta": "   ", "timestamp_ms": 100},
        )
        assert res.status_code == 400
        assert "visual_delta" in res.json()["error"].lower()

    def test_non_json_body_returns_400(self):
        res = client.post(
            "/agent/process-frame",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 400
        assert "json" in res.json()["error"].lower()


# ------------------------------------------------------------------ #
# POST /end-session                                                    #
# ------------------------------------------------------------------ #

class TestEndSessionEndpoint:
    def test_missing_session_id_returns_404(self):
        res = client.post("/end-session", json={})
        assert res.status_code == 404

    def test_invalid_session_id_returns_404(self):
        res = client.post("/end-session", json={"session_id": "not-a-real-id"})
        assert res.status_code == 404

    def test_non_json_body_returns_400(self):
        res = client.post(
            "/end-session",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 400

    def test_empty_graph_returns_400(self):
        sid = create_session()
        res = client.post("/end-session", json={"session_id": sid})
        assert res.status_code == 400
        assert "empty" in res.json()["error"].lower()


# ------------------------------------------------------------------ #
# Session isolation                                                    #
# ------------------------------------------------------------------ #

class TestSessionIsolation:
    def test_two_sessions_have_independent_graphs(self):
        from unittest.mock import MagicMock
        from langchain_core.messages import AIMessage
        import server.app as srv

        sid1 = create_session()
        sid2 = create_session()

        # Mock the LLM for session 1 only — creates one node
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            AIMessage(
                content="",
                tool_calls=[{"id": "c0", "name": "create_node",
                              "args": {"id": "api", "label": "API", "type": "service"}}],
            ),
            AIMessage(content="Added API node."),
        ]
        original = srv._sessions[sid1]["agent"].llm_with_tools
        srv._sessions[sid1]["agent"].llm_with_tools = mock_llm

        try:
            res = client.post(
                "/agent/process-frame",
                json={"session_id": sid1, "visual_delta": "API box drawn", "timestamp_ms": 1000},
            )
            assert res.status_code == 200

            # Session 1 graph should have 1 node
            assert len(srv._sessions[sid1]["graph"]) == 1
            # Session 2 graph should still be empty
            assert len(srv._sessions[sid2]["graph"]) == 0
        finally:
            srv._sessions[sid1]["agent"].llm_with_tools = original

    def test_ended_session_is_removed_from_registry(self):
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        sid = create_session()
        # Manually add a node so the graph isn't empty
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(return_value={
            "session_id": sid,
            "nodes_saved": 1,
            "edges_saved": 0,
            "traversal_order": ["svc"],
        })
        with patch.object(srv._store, "save_session", mock_save):
            res = client.post("/end-session", json={"session_id": sid})

        assert res.status_code == 200
        assert sid not in srv._sessions

    def test_ended_session_id_cannot_be_reused(self):
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        sid = create_session()
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(return_value={
            "session_id": sid, "nodes_saved": 1, "edges_saved": 0, "traversal_order": ["svc"],
        })
        with patch.object(srv._store, "save_session", mock_save):
            client.post("/end-session", json={"session_id": sid})

        # Trying to use the same session_id again should 404
        res = client.post(
            "/agent/process-frame",
            json={"session_id": sid, "visual_delta": "something"},
        )
        assert res.status_code == 404


# ------------------------------------------------------------------ #
# Session cleanup guarantees                                           #
# ------------------------------------------------------------------ #

class TestSessionCleanup:
    """
    Verify that in-memory session state is always removed from the registry,
    even when external services (e.g. MongoDB) fail.
    """

    def test_empty_graph_end_session_does_not_remove_session(self):
        """
        If end-session is rejected because the graph is empty (400), the session
        must remain in the registry so the user can add nodes and retry.
        """
        import server.app as srv

        sid = create_session()
        res = client.post("/end-session", json={"session_id": sid})

        assert res.status_code == 400
        assert sid in srv._sessions  # session still alive — user can continue
        srv._sessions.pop(sid, None)  # cleanup

    def test_session_removed_when_save_raises(self):
        """
        If MongoDB save throws an unexpected exception, the session must still
        be removed from the in-memory registry to prevent a permanent leak.
        """
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        sid = create_session()
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(side_effect=RuntimeError("MongoDB unreachable"))
        with patch.object(srv._store, "save_session", mock_save):
            res = client.post("/end-session", json={"session_id": sid})

        assert res.status_code == 500
        assert "failed to save" in res.json()["error"].lower()
        assert sid not in srv._sessions  # cleaned up despite the error

    def test_failed_save_session_cannot_be_reused(self):
        """
        After a failed save, the session ID should not be reusable (it was popped).
        """
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        sid = create_session()
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(side_effect=RuntimeError("DB down"))
        with patch.object(srv._store, "save_session", mock_save):
            client.post("/end-session", json={"session_id": sid})

        res = client.post(
            "/agent/process-frame",
            json={"session_id": sid, "visual_delta": "something"},
        )
        assert res.status_code == 404

    def test_successful_save_removes_session(self):
        """Sanity-check: normal end-session still removes the session."""
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        sid = create_session()
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(return_value={
            "session_id": sid, "nodes_saved": 1,
            "edges_saved": 0, "traversal_order": ["svc"],
        })
        with patch.object(srv._store, "save_session", mock_save):
            res = client.post("/end-session", json={"session_id": sid})

        assert res.status_code == 200
        assert sid not in srv._sessions


# ------------------------------------------------------------------ #
# End-to-end: frame processed → graph mutated → session saved         #
# ------------------------------------------------------------------ #

class TestEndToEnd:
    """
    Exercises the full happy path without real external services:

        POST /new-session
        POST /agent/process-frame  (LLM mocked → creates two nodes + an edge)
        POST /agent/process-frame  (LLM mocked → sets entry point)
        POST /end-session          (MongoDB mocked → returns correct summary)
    """

    def test_full_session_flow(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from langchain_core.messages import AIMessage
        import server.app as srv

        # --- Start session ---
        sid = create_session()

        def make_tool_response(*calls):
            return AIMessage(
                content="",
                tool_calls=[
                    {"id": f"c{i}", "name": name, "args": args}
                    for i, (name, args) in enumerate(calls)
                ],
            )

        frame1_llm_calls = [
            make_tool_response(
                ("create_node", {"id": "browser", "label": "Browser", "type": "client"}),
                ("create_node", {"id": "api",     "label": "API",     "type": "service"}),
                ("add_edge",    {"from_id": "browser", "to_id": "api", "label": "requests"}),
            ),
            AIMessage(content="Got it — browser connects to API."),
        ]
        frame2_llm_calls = [
            make_tool_response(("set_entry_point", {"id": "browser"})),
            AIMessage(content="Entry point is the browser."),
        ]

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = frame1_llm_calls + frame2_llm_calls
        original = srv._sessions[sid]["agent"].llm_with_tools
        srv._sessions[sid]["agent"].llm_with_tools = mock_llm

        try:
            # --- Frame 1 ---
            res1 = client.post(
                "/agent/process-frame",
                json={
                    "session_id": sid,
                    "visual_delta": "Browser and API boxes drawn with an arrow between them.",
                    "timestamp_ms": 1000,
                },
            )
            assert res1.status_code == 200, res1.text
            assert res1.json()["verbal_response"] == "Got it — browser connects to API."

            state = srv._sessions[sid]["graph"].get_state()
            assert len(state["nodes"]) == 2
            assert len(state["edges"]) == 1

            # --- Frame 2 ---
            res2 = client.post(
                "/agent/process-frame",
                json={
                    "session_id": sid,
                    "visual_delta": "Browser box is circled, indicating it is the entry point.",
                    "timestamp_ms": 3000,
                },
            )
            assert res2.status_code == 200
            assert srv._sessions[sid]["graph"].get_state()["entry_point"] == "browser"

            # --- End session (mock MongoDB) ---
            mock_save = AsyncMock(return_value={
                "session_id": sid,
                "nodes_saved": 2,
                "edges_saved": 1,
                "traversal_order": ["browser", "api"],
            })
            with patch.object(srv._store, "save_session", mock_save):
                res3 = client.post("/end-session", json={"session_id": sid})

            assert res3.status_code == 200
            data = res3.json()
            assert data["status"] == "saved"
            assert data["nodes_saved"] == 2
            assert data["edges_saved"] == 1
            assert data["traversal_order"] == ["browser", "api"]

            # Session should be cleaned up after saving
            assert sid not in srv._sessions

        finally:
            # Restore LLM if session still exists (e.g. test failed mid-way)
            if sid in srv._sessions:
                srv._sessions[sid]["agent"].llm_with_tools = original
                srv._sessions.pop(sid, None)
