"""
Tests for authentication and session-ownership enforcement in server/app.py.

These tests patch server.app.require_auth (the sync function imported from
server.auth) to control the auth result precisely and verify:
  - Every protected endpoint returns 401 when no Bearer token is supplied.
  - Every protected endpoint returns 401 when the token is invalid/expired.
  - Session-scoped endpoints return 403 when a different user presents a
    valid token but does not own the requested session.
  - The session owner can always access their own session.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("GOOGLE_API_KEY", "test-key-stub")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("CLERK_JWKS_URL", "https://test.clerk.test/.well-known/jwks.json")

from starlette.responses import JSONResponse  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from server.app import app, _sessions, _session_owners  # noqa: E402
from server.auth import AuthContext  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)

USER_A = "user_alice_111"
USER_B = "user_bob_222"


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _auth_as(user_id: str) -> dict[str, str]:
    """Return Authorization header for a fake user (no real JWT needed)."""
    return {"Authorization": f"Bearer fake-token-for-{user_id}"}


def _make_auth_context(user_id: str) -> AuthContext:
    return AuthContext(user_id=user_id, clerk_session_id=None, payload={"sub": user_id})


def _mock_auth_ok(user_id: str):
    """Return a mock require_auth that succeeds for user_id."""
    return MagicMock(return_value=_make_auth_context(user_id))


def _mock_auth_401(message: str = "Authentication required."):
    """Return a mock require_auth that returns a 401 JSONResponse."""
    return MagicMock(return_value=JSONResponse({"error": message}, status_code=401))


def _mock_auth_500(message: str = "Server authentication is not configured."):
    """Return a mock require_auth that returns a 500 JSONResponse."""
    return MagicMock(return_value=JSONResponse({"error": message}, status_code=500))


def _create_session_as(user_id: str) -> str:
    """Create a session owned by user_id and return the session_id."""
    import server.app as srv
    with patch.object(srv, "require_auth", _mock_auth_ok(user_id)):
        res = client.post("/new-session", headers=_auth_as(user_id))
    assert res.status_code == 200, res.text
    return res.json()["session_id"]


# ------------------------------------------------------------------ #
# 401 — No token / bad token on every protected endpoint              #
# ------------------------------------------------------------------ #

class TestUnauthenticatedRequests:
    """Every protected endpoint must return 401 when no valid token is given."""

    def _assert_401(self, response) -> None:
        assert response.status_code == 401, response.text
        assert "error" in response.json()

    def test_new_session_no_token(self):
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_401("Missing or malformed Authorization header.")):
            res = client.post("/new-session")
        self._assert_401(res)

    def test_process_frame_no_token(self):
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_401("Missing or malformed Authorization header.")):
            res = client.post("/agent/process-frame", json={"session_id": "x", "visual_delta": "y"})
        self._assert_401(res)

    def test_process_capture_no_token(self):
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_401("Missing or malformed Authorization header.")):
            res = client.post(
                "/agent/process-capture",
                data={"session_id": "x"},
                files={"frame": ("f.jpg", b"\xff\xd8", "image/jpeg")},
            )
        self._assert_401(res)

    def test_end_session_no_token(self):
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_401("Missing or malformed Authorization header.")):
            res = client.post(
                "/end-session",
                data={"session_id": "x"},
                files={"audio": ("a.webm", b"audio", "audio/webm")},
            )
        self._assert_401(res)

    def test_analysis_status_no_token(self):
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_401("Missing or malformed Authorization header.")):
            res = client.get("/analysis/some-session-id")
        self._assert_401(res)

    def test_chat_no_token(self):
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_401("Missing or malformed Authorization header.")):
            res = client.post("/chat", json={"session_id": "x", "message": "hi"})
        self._assert_401(res)

    def test_invalid_token_returns_401(self):
        """simulate an expired/malformed JWT being rejected"""
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_401("Token has expired and is no longer valid.")):
            res = client.post("/new-session", headers={"Authorization": "Bearer expired.token.here"})
        self._assert_401(res)
        body = res.json()
        assert "token" in body["error"].lower() or "authorization" in body["error"].lower() or "expired" in body["error"].lower()


# ------------------------------------------------------------------ #
# 403 — Valid token but wrong user tries to access another's session  #
# ------------------------------------------------------------------ #

class TestOwnershipEnforcement:
    """A valid user must not be able to access another user's session."""

    def test_process_frame_wrong_user_returns_403(self):
        import server.app as srv
        sid = _create_session_as(USER_A)
        with patch.object(srv, "require_auth", _mock_auth_ok(USER_B)):
            res = client.post(
                "/agent/process-frame",
                json={"session_id": sid, "visual_delta": "boxes drawn", "timestamp_ms": 0},
                headers=_auth_as(USER_B),
            )
        assert res.status_code == 403, res.text
        assert "forbidden" in res.json()["error"].lower()
        # cleanup
        _sessions.pop(sid, None)
        _session_owners.pop(sid, None)

    def test_process_capture_wrong_user_returns_403(self):
        import server.app as srv
        sid = _create_session_as(USER_A)
        with patch.object(srv, "require_auth", _mock_auth_ok(USER_B)):
            res = client.post(
                "/agent/process-capture",
                data={"session_id": sid, "timestamp_ms": "0"},
                files={"frame": ("f.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")},
                headers=_auth_as(USER_B),
            )
        assert res.status_code == 403, res.text
        _sessions.pop(sid, None)
        _session_owners.pop(sid, None)

    def test_end_session_wrong_user_returns_403(self):
        import server.app as srv
        sid = _create_session_as(USER_A)
        with patch.object(srv, "require_auth", _mock_auth_ok(USER_B)):
            res = client.post(
                "/end-session",
                data={"session_id": sid},
                files={"audio": ("a.webm", b"audio-data", "audio/webm")},
                headers=_auth_as(USER_B),
            )
        assert res.status_code == 403, res.text
        # Session should still exist — the wrong user did not end it
        assert sid in _sessions
        _sessions.pop(sid, None)
        _session_owners.pop(sid, None)

    def test_analysis_status_wrong_user_returns_403(self):
        import server.app as srv
        sid = _create_session_as(USER_A)
        # Simulate the analysis job being queued (as if end_session was called by owner)
        srv._analysis_jobs[sid] = {"session_id": sid, "status": "processing", "stage": "queued", "user_id": USER_A}
        with patch.object(srv, "require_auth", _mock_auth_ok(USER_B)):
            res = client.get(f"/analysis/{sid}", headers=_auth_as(USER_B))
        assert res.status_code == 403, res.text
        _sessions.pop(sid, None)
        _session_owners.pop(sid, None)
        srv._analysis_jobs.pop(sid, None)

    def test_chat_wrong_user_returns_403(self):
        import server.app as srv
        sid = _create_session_as(USER_A)
        analysis_doc = {
            "_id": sid,
            "user_id": USER_A,
            "chat_seed_context": "Session context for Alice.",
        }
        with (
            patch.object(srv, "require_auth", _mock_auth_ok(USER_B)),
            patch.object(srv._store, "get_analysis", AsyncMock(return_value=analysis_doc)),
        ):
            res = client.post(
                "/chat",
                json={"session_id": sid, "message": "How can I improve?"},
                headers=_auth_as(USER_B),
            )
        assert res.status_code == 403, res.text
        _sessions.pop(sid, None)
        _session_owners.pop(sid, None)


# ------------------------------------------------------------------ #
# 200/202 — Owner can always access their own session                 #
# ------------------------------------------------------------------ #

class TestOwnerAccess:
    """The session owner must be able to access every endpoint for their session."""

    def test_owner_can_call_process_frame(self):
        from langchain_core.messages import AIMessage
        import server.app as srv

        sid = _create_session_as(USER_A)

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            AIMessage(
                content="",
                tool_calls=[{"id": "c0", "name": "create_node",
                              "args": {"id": "api", "label": "API", "type": "service"}}],
            ),
            AIMessage(content="Added API node."),
        ]
        original = srv._sessions[sid]["agent"].llm_with_tools
        srv._sessions[sid]["agent"].llm_with_tools = mock_llm

        try:
            with patch.object(srv, "require_auth", _mock_auth_ok(USER_A)):
                res = client.post(
                    "/agent/process-frame",
                    json={"session_id": sid, "visual_delta": "API box drawn", "timestamp_ms": 0},
                    headers=_auth_as(USER_A),
                )
            assert res.status_code == 200, res.text
            assert res.json()["verbal_response"] == "Added API node."
        finally:
            if sid in srv._sessions:
                srv._sessions[sid]["agent"].llm_with_tools = original
            _sessions.pop(sid, None)
            _session_owners.pop(sid, None)

    def test_owner_can_call_end_session(self):
        import server.app as srv

        sid = _create_session_as(USER_A)
        srv._sessions[sid]["graph"].create_node("svc", "Service", "service")

        mock_save = AsyncMock(return_value={
            "session_id": sid, "nodes_saved": 1, "edges_saved": 0, "traversal_order": ["svc"],
        })
        mock_save_analysis = AsyncMock(return_value={"session_id": sid, "analysis_saved": True})

        with (
            patch.object(srv, "require_auth", _mock_auth_ok(USER_A)),
            patch.object(srv._store, "save_session", mock_save),
            patch.object(srv._store, "save_analysis", mock_save_analysis),
        ):
            res = client.post(
                "/end-session",
                data={"session_id": sid},
                files={"audio": ("a.webm", b"audio-data", "audio/webm")},
                headers=_auth_as(USER_A),
            )
        assert res.status_code == 202, res.text
        assert sid not in srv._sessions

    def test_owner_can_poll_analysis_status(self):
        import server.app as srv

        sid = _create_session_as(USER_A)
        srv._analysis_jobs[sid] = {"session_id": sid, "status": "complete", "stage": "complete", "user_id": USER_A}

        with patch.object(srv, "require_auth", _mock_auth_ok(USER_A)):
            res = client.get(f"/analysis/{sid}", headers=_auth_as(USER_A))

        assert res.status_code == 200, res.text
        assert res.json()["status"] == "complete"
        _sessions.pop(sid, None)
        _session_owners.pop(sid, None)
        srv._analysis_jobs.pop(sid, None)

    def test_owner_can_chat(self):
        import server.app as srv

        sid = _create_session_as(USER_A)
        analysis_doc = {
            "_id": sid,
            "user_id": USER_A,
            "chat_seed_context": "Session context for Alice.",
        }

        class FakeChatAgent:
            def __init__(self, chat_seed_context: str):
                pass
            def respond(self, _message: str) -> str:
                return "Consider adding a cache layer."

        with (
            patch.object(srv, "require_auth", _mock_auth_ok(USER_A)),
            patch.object(srv._store, "get_analysis", AsyncMock(return_value=analysis_doc)),
            patch.object(srv, "ChatAgent", FakeChatAgent),
        ):
            res = client.post(
                "/chat",
                json={"session_id": sid, "message": "How can I improve?"},
                headers=_auth_as(USER_A),
            )

        assert res.status_code == 200, res.text
        assert res.json()["response"] == "Consider adding a cache layer."
        _sessions.pop(sid, None)
        _session_owners.pop(sid, None)


# ------------------------------------------------------------------ #
# Session isolation by user                                           #
# ------------------------------------------------------------------ #

class TestUserSessionIsolation:
    """Two users' sessions must be fully independent."""

    def test_two_users_sessions_are_independent(self):
        """User A and User B each create a session; neither can see the other's."""
        import server.app as srv

        sid_a = _create_session_as(USER_A)
        sid_b = _create_session_as(USER_B)

        assert _session_owners.get(sid_a) == USER_A
        assert _session_owners.get(sid_b) == USER_B

        # User A cannot touch User B's session
        with patch.object(srv, "require_auth", _mock_auth_ok(USER_A)):
            res = client.post(
                "/agent/process-frame",
                json={"session_id": sid_b, "visual_delta": "intruder", "timestamp_ms": 0},
                headers=_auth_as(USER_A),
            )
        assert res.status_code == 403

        # User B cannot touch User A's session
        with patch.object(srv, "require_auth", _mock_auth_ok(USER_B)):
            res = client.post(
                "/agent/process-frame",
                json={"session_id": sid_a, "visual_delta": "intruder", "timestamp_ms": 0},
                headers=_auth_as(USER_B),
            )
        assert res.status_code == 403

        _sessions.pop(sid_a, None)
        _sessions.pop(sid_b, None)
        _session_owners.pop(sid_a, None)
        _session_owners.pop(sid_b, None)

    def test_session_owner_stored_with_new_session(self):
        """_session_owners must record the creator's user_id on POST /new-session."""
        import server.app as srv

        sid = _create_session_as(USER_A)
        assert _session_owners.get(sid) == USER_A
        assert srv._sessions[sid].get("user_id") == USER_A

        _sessions.pop(sid, None)
        _session_owners.pop(sid, None)


# ------------------------------------------------------------------ #
# CLERK_SECRET_KEY misconfiguration — must return 500, not crash      #
# ------------------------------------------------------------------ #

class TestMisconfiguredAuth:
    """
    When the server-side auth config is broken, endpoints must return a clean
    JSON 500 response instead of crashing.
    """

    def _assert_config_error(self, response) -> None:
        assert response.status_code == 500, response.text
        body = response.json()
        assert "error" in body
        assert (
            "configuration" in body["error"].lower()
            or "configured" in body["error"].lower()
            or "clerk" in body["error"].lower()
        )

    def test_new_session_returns_500_when_auth_misconfigured(self):
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_500()):
            res = client.post("/new-session")
        self._assert_config_error(res)

    def test_process_frame_returns_500_when_auth_misconfigured(self):
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_500()):
            res = client.post(
                "/agent/process-frame",
                json={"session_id": "x", "visual_delta": "y"},
                headers={"Authorization": "Bearer some-token"},
            )
        self._assert_config_error(res)

    def test_end_session_returns_500_when_auth_misconfigured(self):
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_500()):
            res = client.post(
                "/end-session",
                data={"session_id": "x"},
                files={"audio": ("a.webm", b"audio", "audio/webm")},
                headers={"Authorization": "Bearer some-token"},
            )
        self._assert_config_error(res)

    def test_analysis_status_returns_500_when_auth_misconfigured(self):
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_500()):
            res = client.get(
                "/analysis/some-session",
                headers={"Authorization": "Bearer some-token"},
            )
        self._assert_config_error(res)

    def test_chat_returns_500_when_auth_misconfigured(self):
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_500()):
            res = client.post(
                "/chat",
                json={"session_id": "x", "message": "hi"},
                headers={"Authorization": "Bearer some-token"},
            )
        self._assert_config_error(res)

    def test_config_error_response_is_json(self):
        """The 500 response must be valid JSON with an 'error' key, not an HTML crash page."""
        import server.app as srv
        with patch.object(srv, "require_auth", _mock_auth_500()):
            res = client.post("/new-session")
        assert "application/json" in res.headers.get("content-type", "")
        assert "error" in res.json()
