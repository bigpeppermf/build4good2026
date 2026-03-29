"""
Integration tests for the HTTP endpoints in graph_mcp/server.py.

Uses Starlette's TestClient (synchronous, no real network needed).
These tests do NOT require GOOGLE_API_KEY or MONGODB_URI — they exercise
only the request validation layer, session lifecycle, and routes that return
early (400/404 responses) before touching external services.
"""

import os
import time
from unittest.mock import AsyncMock

import pytest

# Force stub keys before importing server.app so no real external calls are made.
os.environ["GOOGLE_API_KEY"] = "test-key-stub"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("CLERK_JWKS_URL", "https://test.clerk.test/.well-known/jwks.json")

from starlette.testclient import TestClient  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402

from server.app import app  # noqa: E402
import server.app as srv  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

# Default user ID injected by the autouse auth patch below.
TEST_USER_ID = "user_test_default_abc123"



# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def auth_headers(user_id: str = "user-test") -> dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


@pytest.fixture(autouse=True)
def fake_clerk_auth(monkeypatch: pytest.MonkeyPatch):
    def _fake_require_auth(request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return JSONResponse({"error": "Authentication required."}, status_code=401)

        user_id = header.replace("Bearer ", "", 1).strip()
        if not user_id:
            return JSONResponse({"error": "Authentication required."}, status_code=401)

        return srv.AuthContext(
            user_id=user_id,
            clerk_session_id=f"sess_{user_id}",
            payload={"sub": user_id, "sid": f"sess_{user_id}"},
        )

    monkeypatch.setattr(srv, "require_auth", _fake_require_auth)
    srv._sessions.clear()
    srv._analysis_jobs.clear()
    yield
    srv._sessions.clear()
    srv._analysis_jobs.clear()


def create_session(user_id: str = "user-test") -> str:
    """Create a new session and return its session_id."""
    res = client.post("/new-session", headers=auth_headers(user_id))
    assert res.status_code == 200
    return res.json()["session_id"]


def end_session_with_audio(
    session_id: str,
    user_id: str = "user-test",
    audio_bytes: bytes = b"fake-audio",
) -> object:
    """
    Call POST /end-session using the Step 2 multipart contract.
    """
    return client.post(
        "/end-session",
        data={"session_id": session_id},
        files={"audio": ("session.webm", audio_bytes, "audio/webm")},
        headers=auth_headers(user_id),
    )


def wait_for_analysis_final(
    session_id: str,
    user_id: str = "user-test",
    timeout_s: float = 1.0,
) -> dict:
    """
    Poll GET /analysis/{session_id} until status becomes complete/failed.
    """
    deadline = time.time() + timeout_s
    latest_payload: dict | None = None
    latest_code: int | None = None

    while time.time() < deadline:
        res = client.get(f"/analysis/{session_id}", headers=auth_headers(user_id))
        latest_code = res.status_code
        if res.status_code == 200:
            latest_payload = res.json()
            if latest_payload.get("status") in {"complete", "failed"}:
                return latest_payload
        time.sleep(0.01)

    pytest.fail(
        "Timed out waiting for analysis completion. "
        f"last_code={latest_code}, last_payload={latest_payload}",
    )


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
    def test_requires_authentication(self):
        res = client.post("/new-session")
        assert res.status_code == 401

    def test_returns_200(self):
        res = client.post("/new-session", headers=auth_headers())
        assert res.status_code == 200

    def test_returns_session_id(self):
        res = client.post("/new-session", headers=auth_headers())
        assert "session_id" in res.json()
        assert len(res.json()["session_id"]) > 0

    def test_each_call_returns_unique_session_id(self):
        id1 = client.post("/new-session", headers=auth_headers()).json()["session_id"]
        id2 = client.post("/new-session", headers=auth_headers()).json()["session_id"]
        assert id1 != id2

    def test_multiple_active_sessions_coexist(self):
        ids = {
            client.post("/new-session", headers=auth_headers()).json()["session_id"]
            for _ in range(5)
        }
        assert len(ids) == 5


# ------------------------------------------------------------------ #
# POST /agent/process-frame                                            #
# ------------------------------------------------------------------ #

class TestProcessFrameEndpoint:
    def test_requires_authentication(self):
        res = client.post(
            "/agent/process-frame",
            json={"session_id": "not-a-real-id", "visual_delta": "something"},
        )
        assert res.status_code == 401

    def test_missing_session_id_returns_404(self):
        res = client.post(
            "/agent/process-frame",
            json={"visual_delta": "something", "timestamp_ms": 100},
            headers=auth_headers(),
        )
        assert res.status_code == 404
        assert "session_id" in res.json()["error"].lower()

    def test_invalid_session_id_returns_404(self):
        res = client.post(
            "/agent/process-frame",
            json={"session_id": "not-a-real-id", "visual_delta": "something"},
            headers=auth_headers(),
        )
        assert res.status_code == 404

    def test_missing_visual_delta_returns_400(self):
        sid = create_session()
        res = client.post(
            "/agent/process-frame",
            json={"session_id": sid, "timestamp_ms": 100},
            headers=auth_headers(),
        )
        assert res.status_code == 400
        assert "visual_delta" in res.json()["error"].lower()

    def test_empty_visual_delta_returns_400(self):
        sid = create_session()
        res = client.post(
            "/agent/process-frame",
            json={"session_id": sid, "visual_delta": "   ", "timestamp_ms": 100},
            headers=auth_headers(),
        )
        assert res.status_code == 400
        assert "visual_delta" in res.json()["error"].lower()

    def test_non_json_body_returns_400(self):
        res = client.post(
            "/agent/process-frame",
            content=b"not json",
            headers={"Content-Type": "application/json", **auth_headers()},
        )
        assert res.status_code == 400
        assert "json" in res.json()["error"].lower()


# ------------------------------------------------------------------ #
# POST /agent/process-capture                                          #
# ------------------------------------------------------------------ #


class TestProcessCaptureEndpoint:
    def test_requires_authentication(self):
        res = client.post(
            "/agent/process-capture",
            data={"session_id": "not-a-real-id", "timestamp_ms": "0"},
            files={"frame": ("f.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")},
        )
        assert res.status_code == 401

    def test_invalid_session_id_returns_404(self):
        # Multipart: text fields in ``data``, file in ``files`` (httpx/Starlette).
        res = client.post(
            "/agent/process-capture",
            data={"session_id": "not-a-real-id", "timestamp_ms": "0"},
            files={"frame": ("f.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")},
            headers=auth_headers(),
        )
        assert res.status_code == 404
        assert "session_id" in res.json()["error"].lower()

    def test_missing_frame_returns_400(self):
        sid = create_session()
        res = client.post(
            "/agent/process-capture",
            data={"session_id": sid, "timestamp_ms": "0"},
            headers=auth_headers(),
        )
        assert res.status_code == 400
        assert "frame" in res.json()["error"].lower()

    def test_empty_frame_returns_400(self):
        sid = create_session()
        res = client.post(
            "/agent/process-capture",
            data={"session_id": sid, "timestamp_ms": "0"},
            files={"frame": ("empty.jpg", b"", "image/jpeg")},
            headers=auth_headers(),
        )
        assert res.status_code == 400

    def test_successful_capture_persists_frame_with_user_ownership(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        import server.app as srv

        sid = create_session(user_id="owner-user")
        srv._sessions[sid]["pipeline"] = MagicMock()
        srv._sessions[sid]["pipeline"].process_frame.return_value = {
            "visual_delta": "API box added",
        }
        srv._sessions[sid]["agent"].process_frame = MagicMock(
            return_value="Added the API service to the graph."
        )

        with patch.object(srv._store, "save_frame", AsyncMock()) as mock_save_frame:
            res = client.post(
                "/agent/process-capture",
                data={"session_id": sid, "timestamp_ms": "1500"},
                files={"frame": ("frame.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")},
                headers=auth_headers("owner-user"),
            )

        assert res.status_code == 200
        assert res.json() == {
            "verbal_response": "Added the API service to the graph.",
            "visual_delta": "API box added",
            "timestamp_ms": 1500,
        }
        mock_save_frame.assert_awaited_once_with(
            session_id=sid,
            timestamp_ms=1500,
            visual_delta="API box added",
            verbal_response="Added the API service to the graph.",
            user_id="owner-user",
            clerk_session_id="sess_owner-user",
        )

    def test_other_user_cannot_process_another_users_capture(self):
        sid = create_session(user_id="owner-user")

        res = client.post(
            "/agent/process-capture",
            data={"session_id": sid, "timestamp_ms": "1500"},
            files={"frame": ("frame.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")},
            headers=auth_headers("other-user"),
        )

        assert res.status_code == 403


# ------------------------------------------------------------------ #
# POST /end-session                                                    #
# ------------------------------------------------------------------ #

class TestEndSessionEndpoint:
    def test_requires_authentication(self):
        res = client.post(
            "/end-session",
            data={"session_id": "not-a-real-id"},
            files={"audio": ("session.webm", b"audio", "audio/webm")},
        )
        assert res.status_code == 401

    def test_missing_session_id_returns_404(self):
        res = client.post(
            "/end-session",
            data={},
            files={"audio": ("session.webm", b"audio", "audio/webm")},
            headers=auth_headers(),
        )
        assert res.status_code == 404

    def test_invalid_session_id_returns_404(self):
        res = end_session_with_audio("not-a-real-id")
        assert res.status_code == 404

    def test_non_form_body_returns_400(self):
        res = client.post(
            "/end-session",
            content=b"not form",
            headers={"Content-Type": "application/json", **auth_headers()},
        )
        assert res.status_code == 400

    def test_missing_audio_returns_400(self):
        sid = create_session()
        res = client.post(
            "/end-session",
            data={"session_id": sid},
            files={"placeholder": ("placeholder.txt", b"x", "text/plain")},
            headers=auth_headers(),
        )
        assert res.status_code == 400
        assert "audio" in res.json()["error"].lower()

    def test_empty_audio_returns_400(self):
        sid = create_session()
        res = client.post(
            "/end-session",
            data={"session_id": sid},
            files={"audio": ("session.webm", b"", "audio/webm")},
            headers=auth_headers(),
        )
        assert res.status_code == 400
        assert "empty audio" in res.json()["error"].lower()

    def test_empty_graph_returns_400(self):
        sid = create_session()
        res = end_session_with_audio(sid)
        assert res.status_code == 400
        assert "empty" in res.json()["error"].lower()


# ------------------------------------------------------------------ #
# GET /analysis/{session_id}                                          #
# ------------------------------------------------------------------ #

class TestAnalysisStatusEndpoint:
    def test_requires_authentication(self):
        res = client.get("/analysis/not-a-real-id")
        assert res.status_code == 401

    def test_unknown_session_id_returns_404(self):
        res = client.get("/analysis/not-a-real-id", headers=auth_headers())
        assert res.status_code == 404

    def test_polling_eventually_reaches_complete(self):
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        sid = create_session()
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(return_value={
            "session_id": sid,
            "nodes_saved": 1,
            "edges_saved": 0,
            "traversal_order": ["svc"],
        })
        mock_save_analysis = AsyncMock(return_value={"session_id": sid, "analysis_saved": True})
        with (
            patch.object(srv._store, "save_session", mock_save),
            patch.object(srv._store, "save_analysis", mock_save_analysis),
        ):
            res = end_session_with_audio(sid)
            assert res.status_code == 202
            payload = wait_for_analysis_final(sid)

        assert payload["status"] == "complete"
        assert payload["stage"] == "complete"
        assert payload["session_summary"]["session_id"] == sid

    def test_pipeline_passes_validation_fields_into_save_session(self):
        from unittest.mock import AsyncMock, patch

        from agent.validation_agent import ValidationResult
        import server.app as srv

        sid = create_session()
        graph = srv._sessions[sid]["graph"]
        graph.create_node("svc", "Service", "service")

        expected_validation = ValidationResult(
            transcript="Browser traffic reaches API and Redis cache.",
            corrections_made=2,
            validation_summary="Added missing Redis cache from transcript.",
            graph_confidence=0.5,
        )

        class FakeValidationAgent:
            def __init__(self, _graph):
                self.graph = _graph

            async def validate_audio(self, _audio_bytes, _mime_type):
                return expected_validation

        mock_save = AsyncMock(return_value={
            "session_id": sid,
            "nodes_saved": 1,
            "edges_saved": 0,
            "traversal_order": ["svc"],
        })
        mock_save_analysis = AsyncMock(return_value={"session_id": sid, "analysis_saved": True})
        with (
            patch.object(srv, "ValidationAgent", FakeValidationAgent),
            patch.object(srv._store, "save_session", mock_save),
            patch.object(srv._store, "save_analysis", mock_save_analysis),
        ):
            res = end_session_with_audio(sid)
            assert res.status_code == 202
            payload = wait_for_analysis_final(sid)

        assert payload["status"] == "complete"
        mock_save.assert_awaited_once()
        assert mock_save.await_args.args[0] is graph
        assert mock_save.await_args.args[1] == sid
        assert mock_save.await_args.kwargs["audio_transcript"] == expected_validation.transcript
        assert (
            mock_save.await_args.kwargs["validation_corrections"]
            == expected_validation.corrections_made
        )
        assert (
            mock_save.await_args.kwargs["validation_summary"]
            == expected_validation.validation_summary
        )
        assert (
            mock_save.await_args.kwargs["graph_confidence"]
            == expected_validation.graph_confidence
        )
        assert mock_save.await_args.kwargs["user_id"] == "user-test"
        assert mock_save.await_args.kwargs["clerk_session_id"] == "sess_user-test"

    def test_complete_payload_includes_analysis_output(self):
        from unittest.mock import AsyncMock, patch

        from agent.validation_agent import ValidationResult
        import server.app as srv

        sid = create_session()
        graph = srv._sessions[sid]["graph"]
        graph.create_node("browser", "Browser", "client")
        graph.create_node("api", "API", "service")
        graph.add_edge("browser", "api", "requests")
        graph.set_entry_point("browser")

        expected_validation = ValidationResult(
            transcript="Browser sends requests to API.",
            corrections_made=0,
            validation_summary="Graph matches transcript",
            graph_confidence=1.0,
        )
        expected_analysis = {
            "analysis": {
                "architecture_pattern": "3-tier web architecture",
                "component_count": 2,
                "identified_components": ["Browser", "API"],
                "connection_density": "moderate",
                "entry_point": "Browser",
                "disconnected_components": [],
                "bottlenecks": [],
                "missing_standard_components": ["Cache layer", "Message queue"],
                "summary": "Compact architecture with a clear entry point.",
            },
            "feedback": {
                "strengths": ["Entry point is clearly set."],
                "improvements": ["Add a data layer and caching strategy."],
                "critical_gaps": ["No database component detected."],
                "narrative": "Good start; focus next on persistence and scale paths.",
            },
            "score": {
                "total": 64,
                "breakdown": {
                    "completeness": 16,
                    "scalability": 14,
                    "reliability": 14,
                    "clarity": 20,
                },
                "grade": "C",
            },
        }

        class FakeValidationAgent:
            def __init__(self, _graph):
                self.graph = _graph

            async def validate_audio(self, _audio_bytes, _mime_type):
                return expected_validation

        class FakeAnalysisAgent:
            seen_transcripts: list[str] = []
            seen_metadata: list[dict] = []

            async def analyze(self, *, graph, transcript, session_metadata):
                self.__class__.seen_transcripts.append(transcript)
                self.__class__.seen_metadata.append(session_metadata)
                assert graph is not None
                return expected_analysis

        mock_save = AsyncMock(return_value={
            "session_id": sid,
            "nodes_saved": 2,
            "edges_saved": 1,
            "traversal_order": ["browser", "api"],
        })
        mock_save_analysis = AsyncMock(return_value={"session_id": sid, "analysis_saved": True})
        with (
            patch.object(srv, "ValidationAgent", FakeValidationAgent),
            patch.object(srv, "AnalysisAgent", FakeAnalysisAgent),
            patch.object(srv._store, "save_session", mock_save),
            patch.object(srv._store, "save_analysis", mock_save_analysis),
        ):
            res = end_session_with_audio(sid)
            assert res.status_code == 202
            payload = wait_for_analysis_final(sid)

        assert payload["status"] == "complete"
        assert payload["stage"] == "complete"
        assert payload["analysis"] == expected_analysis["analysis"]
        assert payload["feedback"] == expected_analysis["feedback"]
        assert payload["score"] == expected_analysis["score"]
        assert payload["analysis_summary"]["analysis_saved"] is True
        mock_save_analysis.assert_awaited_once_with(
            sid,
            expected_analysis,
            user_id="user-test",
            clerk_session_id="sess_user-test",
        )
        assert FakeAnalysisAgent.seen_transcripts[-1] == expected_validation.transcript
        assert FakeAnalysisAgent.seen_metadata[-1]["session_id"] == sid
        assert FakeAnalysisAgent.seen_metadata[-1]["nodes_saved"] == 2

    def test_other_user_cannot_poll_another_users_job(self):
        from unittest.mock import AsyncMock, patch

        sid = create_session(user_id="owner-user")
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(return_value={
            "session_id": sid,
            "nodes_saved": 1,
            "edges_saved": 0,
            "traversal_order": ["svc"],
        })
        mock_save_analysis = AsyncMock(return_value={"session_id": sid, "analysis_saved": True})
        with (
            patch.object(srv._store, "save_session", mock_save),
            patch.object(srv._store, "save_analysis", mock_save_analysis),
        ):
            res = end_session_with_audio(sid, user_id="owner-user")
            assert res.status_code == 202
            wait_for_analysis_final(sid, user_id="owner-user")

        foreign = client.get(f"/analysis/{sid}", headers=auth_headers("other-user"))
        assert foreign.status_code == 403


# ------------------------------------------------------------------ #
# POST /chat                                                          #
# ------------------------------------------------------------------ #

class TestChatEndpoint:
    def test_requires_authentication(self):
        res = client.post(
            "/chat",
            json={"session_id": "abc123", "message": "hello"},
        )
        assert res.status_code == 401

    def test_non_json_body_returns_400(self):
        res = client.post(
            "/chat",
            content=b"not-json",
            headers={"Content-Type": "application/json", **auth_headers()},
        )
        assert res.status_code == 400
        assert "json" in res.json()["error"].lower()

    def test_missing_session_id_returns_400(self):
        res = client.post(
            "/chat",
            json={"message": "How do I improve scalability?"},
            headers=auth_headers(),
        )
        assert res.status_code == 400
        assert "session_id" in res.json()["error"].lower()

    def test_missing_message_returns_400(self):
        res = client.post(
            "/chat",
            json={"session_id": "abc123"},
            headers=auth_headers(),
        )
        assert res.status_code == 400
        assert "message" in res.json()["error"].lower()

    def test_unknown_session_id_returns_404(self):
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        with patch.object(srv._store, "get_analysis", AsyncMock(return_value=None)):
            res = client.post(
                "/chat",
                json={
                    "session_id": "missing-session",
                    "message": "Why did reliability score drop?",
                },
                headers=auth_headers(),
            )

        assert res.status_code == 404
        assert "session_id" in res.json()["error"].lower()

    def test_returns_chat_agent_response(self):
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        class FakeChatAgent:
            seen_context: list[str] = []
            seen_messages: list[str] = []

            def __init__(self, chat_seed_context: str):
                self.__class__.seen_context.append(chat_seed_context)

            def respond(self, message: str) -> str:
                self.__class__.seen_messages.append(message)
                return "Add a Redis cache and replicate your data tier."

        with (
            patch.object(
                srv._store,
                "get_analysis",
                AsyncMock(
                    return_value={
                        "_id": "session-chat",
                        "chat_seed_context": "Session session-chat analysis context.",
                    }
                ),
            ),
            patch.object(srv, "ChatAgent", FakeChatAgent),
        ):
            res = client.post(
                "/chat",
                json={
                    "session_id": "session-chat",
                    "message": "How do I improve scalability?",
                },
                headers=auth_headers(),
            )

        assert res.status_code == 200
        payload = res.json()
        assert payload["session_id"] == "session-chat"
        assert payload["response"] == "Add a Redis cache and replicate your data tier."
        assert FakeChatAgent.seen_context[-1] == "Session session-chat analysis context."
        assert FakeChatAgent.seen_messages[-1] == "How do I improve scalability?"

    def test_other_user_cannot_chat_on_another_users_session(self):
        from unittest.mock import AsyncMock, patch

        with patch.object(
            srv._store,
            "get_analysis",
            AsyncMock(return_value=None),
        ) as mocked_get_analysis:
            res = client.post(
                "/chat",
                json={
                    "session_id": "session-chat",
                    "message": "How do I improve scalability?",
                },
                headers=auth_headers("other-user"),
            )

        assert res.status_code == 404
        mocked_get_analysis.assert_awaited_once_with(
            "session-chat",
            user_id="other-user",
        )


# ------------------------------------------------------------------ #
# Session isolation                                                    #
# ------------------------------------------------------------------ #

class TestSessionIsolation:
    def test_other_user_cannot_mutate_live_session(self):
        sid = create_session(user_id="owner-user")

        res = client.post(
            "/agent/process-frame",
            json={
                "session_id": sid,
                "visual_delta": "API box drawn",
                "timestamp_ms": 1000,
            },
            headers=auth_headers("other-user"),
        )

        assert res.status_code == 403

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
                headers=auth_headers(),
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
        mock_save_analysis = AsyncMock(return_value={"session_id": sid, "analysis_saved": True})
        with (
            patch.object(srv._store, "save_session", mock_save),
            patch.object(srv._store, "save_analysis", mock_save_analysis),
        ):
            res = end_session_with_audio(sid)
            wait_for_analysis_final(sid)

        assert res.status_code == 202
        assert sid not in srv._sessions

    def test_ended_session_id_cannot_be_reused(self):
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        sid = create_session()
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(return_value={
            "session_id": sid, "nodes_saved": 1, "edges_saved": 0, "traversal_order": ["svc"],
        })
        mock_save_analysis = AsyncMock(return_value={"session_id": sid, "analysis_saved": True})
        with (
            patch.object(srv._store, "save_session", mock_save),
            patch.object(srv._store, "save_analysis", mock_save_analysis),
        ):
            end_session_with_audio(sid)
            wait_for_analysis_final(sid)

        # Trying to use the same session_id again should 404
        res = client.post(
            "/agent/process-frame",
            json={"session_id": sid, "visual_delta": "something"},
            headers=auth_headers(),
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
        res = end_session_with_audio(sid)

        assert res.status_code == 400
        assert sid in srv._sessions  # session still alive — user can continue
        srv._sessions.pop(sid, None)  # cleanup

    def test_failed_background_save_reports_failed_status_and_session_is_removed(self):
        """
        If MongoDB save throws in the background worker, /end-session still returns
        202 and /analysis eventually reports failed.
        """
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        sid = create_session()
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(side_effect=RuntimeError("MongoDB unreachable"))
        mock_save_analysis = AsyncMock(return_value={"session_id": sid, "analysis_saved": True})
        with (
            patch.object(srv._store, "save_session", mock_save),
            patch.object(srv._store, "save_analysis", mock_save_analysis),
        ):
            res = end_session_with_audio(sid)
            payload = wait_for_analysis_final(sid)

        assert res.status_code == 202
        assert payload["status"] == "failed"
        assert "post-session pipeline failed" in payload["error"].lower()
        assert sid not in srv._sessions

    def test_failed_analysis_save_reports_failed_status(self):
        """
        If analysis persistence fails after session save, status should be failed
        with stage=saving_analysis.
        """
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        sid = create_session()
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(return_value={
            "session_id": sid,
            "nodes_saved": 1,
            "edges_saved": 0,
            "traversal_order": ["svc"],
        })
        mock_save_analysis = AsyncMock(side_effect=RuntimeError("Analysis collection unavailable"))
        with (
            patch.object(srv._store, "save_session", mock_save),
            patch.object(srv._store, "save_analysis", mock_save_analysis),
        ):
            res = end_session_with_audio(sid)
            payload = wait_for_analysis_final(sid)

        assert res.status_code == 202
        assert payload["status"] == "failed"
        assert payload["stage"] == "saving_analysis"
        assert "post-session pipeline failed" in payload["error"].lower()

    def test_failed_save_session_cannot_be_reused(self):
        """
        After a failed save, the session ID should not be reusable (it was popped).
        """
        from unittest.mock import AsyncMock, patch
        import server.app as srv

        sid = create_session()
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(side_effect=RuntimeError("DB down"))
        mock_save_analysis = AsyncMock(return_value={"session_id": sid, "analysis_saved": True})
        with (
            patch.object(srv._store, "save_session", mock_save),
            patch.object(srv._store, "save_analysis", mock_save_analysis),
        ):
            end_session_with_audio(sid)
            wait_for_analysis_final(sid)

        res = client.post(
            "/agent/process-frame",
            json={"session_id": sid, "visual_delta": "something"},
            headers=auth_headers(),
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
        mock_save_analysis = AsyncMock(return_value={"session_id": sid, "analysis_saved": True})
        with (
            patch.object(srv._store, "save_session", mock_save),
            patch.object(srv._store, "save_analysis", mock_save_analysis),
        ):
            res = end_session_with_audio(sid)
            wait_for_analysis_final(sid)

        assert res.status_code == 202
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
                headers=auth_headers(),
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
                headers=auth_headers(),
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
            mock_save_analysis = AsyncMock(return_value={"session_id": sid, "analysis_saved": True})
            with (
                patch.object(srv._store, "save_session", mock_save),
                patch.object(srv._store, "save_analysis", mock_save_analysis),
            ):
                res3 = end_session_with_audio(sid)
                analysis_payload = wait_for_analysis_final(sid)

            assert res3.status_code == 202
            assert res3.json()["status"] == "processing"
            assert analysis_payload["status"] == "complete"
            assert analysis_payload["session_summary"]["nodes_saved"] == 2
            assert analysis_payload["session_summary"]["edges_saved"] == 1
            assert analysis_payload["session_summary"]["traversal_order"] == ["browser", "api"]
            assert analysis_payload["analysis_summary"]["analysis_saved"] is True

            # Session should be cleaned up after saving
            assert sid not in srv._sessions

        finally:
            # Restore LLM if session still exists (e.g. test failed mid-way)
            if sid in srv._sessions:
                srv._sessions[sid]["agent"].llm_with_tools = original
                srv._sessions.pop(sid, None)
