"""
Unit tests for core/session_store.py.

These tests run without a real MongoDB instance by patching AsyncIOMotorClient
with lightweight in-memory fakes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from core.graph import SystemDesignGraph
import core.session_store as session_store


@dataclass
class RecordedCall:
    filter_doc: dict
    payload: Any
    upsert: bool = False
    session: Any = None


@dataclass
class FakeCollection:
    replace_one_calls: list[RecordedCall] = field(default_factory=list)
    delete_many_calls: list[RecordedCall] = field(default_factory=list)
    insert_many_calls: list[RecordedCall] = field(default_factory=list)
    insert_one_calls: list[dict] = field(default_factory=list)
    count_documents_calls: list[dict] = field(default_factory=list)
    count_documents_result: int = 0
    find_one_calls: list[dict] = field(default_factory=list)
    find_one_result: Any = None

    async def replace_one(
        self,
        filter_doc: dict,
        document: dict,
        *,
        upsert: bool = False,
        session: Any = None,
    ) -> None:
        self.replace_one_calls.append(
            RecordedCall(filter_doc=filter_doc, payload=document, upsert=upsert, session=session)
        )

    async def delete_many(self, filter_doc: dict, *, session: Any = None) -> None:
        self.delete_many_calls.append(
            RecordedCall(filter_doc=filter_doc, payload=None, session=session)
        )

    async def insert_many(self, documents: list[dict], *, session: Any = None) -> None:
        self.insert_many_calls.append(
            RecordedCall(filter_doc={}, payload=documents, session=session)
        )

    async def insert_one(self, document: dict) -> None:
        self.insert_one_calls.append(document)

    async def find_one(self, filter_doc: dict) -> Any:
        self.find_one_calls.append(filter_doc)
        return self.find_one_result

    async def count_documents(self, filter_doc: dict) -> int:
        self.count_documents_calls.append(filter_doc)
        return self.count_documents_result


@dataclass
class FakeDb:
    sessions: FakeCollection = field(default_factory=FakeCollection)
    nodes: FakeCollection = field(default_factory=FakeCollection)
    frames: FakeCollection = field(default_factory=FakeCollection)
    analysis: FakeCollection = field(default_factory=FakeCollection)


class FakeTransactionContext:
    async def __aenter__(self) -> "FakeTransactionContext":
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        return None


class FakeMongoSession:
    def start_transaction(self) -> FakeTransactionContext:
        return FakeTransactionContext()

    async def __aenter__(self) -> "FakeMongoSession":
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        return None


class FakeClient:
    def __init__(self, db: FakeDb) -> None:
        self.db = db
        self.last_session: FakeMongoSession | None = None
        self.closed = False

    def __getitem__(self, _db_name: str) -> FakeDb:
        return self.db

    async def start_session(self) -> FakeMongoSession:
        self.last_session = FakeMongoSession()
        return self.last_session

    def close(self) -> None:
        self.closed = True


class NoTransactionClient(FakeClient):
    async def start_session(self) -> FakeMongoSession:
        raise RuntimeError("Transaction numbers are only allowed on a replica set member or mongos")


def _make_graph() -> SystemDesignGraph:
    graph = SystemDesignGraph()
    graph.create_node("client", "Client", "client")
    graph.create_node("api", "API", "service")
    graph.create_node("db", "Database", "database")
    graph.add_edge("client", "api", "requests")
    graph.add_edge("api", "db", "writes")
    graph.set_entry_point("client")
    return graph


def test_save_session_persists_validation_fields_with_transaction(monkeypatch: pytest.MonkeyPatch):
    fake_db = FakeDb()
    fake_db.frames.count_documents_result = 3
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    graph = _make_graph()
    summary = asyncio.run(
        store.save_session(
            graph,
            "session-123",
            user_id="user_123",
            clerk_session_id="sess_123",
            audio_transcript="Browser sends traffic to API then DB.",
            validation_corrections=2,
            validation_summary="Added DB connection from transcript.",
            graph_confidence=0.66,
        )
    )

    assert summary["session_id"] == "session-123"
    assert summary["nodes_saved"] == 3
    assert summary["edges_saved"] == 2
    assert summary["traversal_order"] == ["client", "api", "db"]
    assert summary["validation_corrections"] == 2
    assert summary["validation_summary"] == "Added DB connection from transcript."
    assert summary["graph_confidence"] == pytest.approx(0.66)
    assert summary["frames_saved"] == 3

    assert len(fake_db.sessions.replace_one_calls) == 1
    session_write = fake_db.sessions.replace_one_calls[0]
    assert session_write.filter_doc == {"_id": "session-123"}
    assert session_write.upsert is True
    assert session_write.session is fake_client.last_session
    assert session_write.payload["user_id"] == "user_123"
    assert session_write.payload["clerk_session_id"] == "sess_123"
    assert session_write.payload["audio_transcript"] == "Browser sends traffic to API then DB."
    assert session_write.payload["validation_corrections"] == 2
    assert session_write.payload["validation_summary"] == "Added DB connection from transcript."
    assert session_write.payload["graph_confidence"] == pytest.approx(0.66)
    assert session_write.payload["frames_count"] == 3
    assert fake_db.frames.count_documents_calls == [{"session_id": "session-123"}]

    assert len(fake_db.nodes.delete_many_calls) == 1
    assert fake_db.nodes.delete_many_calls[0].filter_doc == {"session_id": "session-123"}
    assert fake_db.nodes.delete_many_calls[0].session is fake_client.last_session

    assert len(fake_db.nodes.insert_many_calls) == 1
    node_write = fake_db.nodes.insert_many_calls[0]
    assert node_write.session is fake_client.last_session
    node_ids = {doc["node_id"] for doc in node_write.payload}
    assert node_ids == {"client", "api", "db"}
    assert all(doc["user_id"] == "user_123" for doc in node_write.payload)
    assert all(doc["clerk_session_id"] == "sess_123" for doc in node_write.payload)
    assert fake_db.frames.count_documents_calls == [{"session_id": "session-123"}]


def test_save_session_falls_back_when_transactions_are_unsupported(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_db = FakeDb()
    fake_db.frames.count_documents_result = 1
    fake_client = NoTransactionClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    graph = _make_graph()
    asyncio.run(store.save_session(graph, "session-no-tx"))

    assert len(fake_db.sessions.replace_one_calls) == 1
    session_write = fake_db.sessions.replace_one_calls[0]
    assert session_write.session is None
    assert session_write.payload["user_id"] == ""
    assert session_write.payload["audio_transcript"] == ""
    assert session_write.payload["validation_corrections"] == 0
    assert session_write.payload["validation_summary"] == "Graph matches transcript"
    assert session_write.payload["graph_confidence"] == 1.0
    assert session_write.payload["frames_count"] == 1
    assert fake_db.frames.count_documents_calls == [{"session_id": "session-no-tx"}]

    assert len(fake_db.nodes.delete_many_calls) == 1
    assert fake_db.nodes.delete_many_calls[0].session is None
    assert len(fake_db.nodes.insert_many_calls) == 1
    assert fake_db.nodes.insert_many_calls[0].session is None


def test_save_analysis_persists_analysis_document(monkeypatch: pytest.MonkeyPatch):
    fake_db = FakeDb()
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    analysis_output = {
        "analysis": {
            "architecture_pattern": "3-tier web architecture",
            "summary": "Client to API to DB with clear request flow.",
        },
        "feedback": {
            "strengths": ["Layering is clear."],
            "improvements": ["Add cache for repeated reads."],
        },
        "score": {
            "total": 78,
            "grade": "B",
        },
    }
    result = asyncio.run(
        store.save_analysis(
            "session-ana-1",
            analysis_output,
            user_id="user_ana",
            clerk_session_id="sess_ana",
        )
    )

    assert result["session_id"] == "session-ana-1"
    assert result["analysis_saved"] is True
    assert result["score_total"] == 78

    assert len(fake_db.analysis.replace_one_calls) == 1
    analysis_write = fake_db.analysis.replace_one_calls[0]
    assert analysis_write.filter_doc == {"_id": "session-ana-1"}
    assert analysis_write.upsert is True
    doc = analysis_write.payload
    assert doc["user_id"] == "user_ana"
    assert doc["clerk_session_id"] == "sess_ana"
    assert doc["analysis"]["architecture_pattern"] == "3-tier web architecture"
    assert doc["feedback"]["strengths"] == ["Layering is clear."]
    assert doc["score"]["total"] == 78
    assert "chat_seed_context" in doc
    assert "session-ana-1" in doc["chat_seed_context"]
    assert "3-tier web architecture" in doc["chat_seed_context"]
    assert "78/100" in doc["chat_seed_context"]


def test_save_analysis_accepts_invalid_payload(monkeypatch: pytest.MonkeyPatch):
    fake_db = FakeDb()
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    result = asyncio.run(store.save_analysis("session-ana-2", analysis_output={}))

    assert result["session_id"] == "session-ana-2"
    assert result["analysis_saved"] is True
    assert result["score_total"] is None
    assert len(fake_db.analysis.replace_one_calls) == 1
    doc = fake_db.analysis.replace_one_calls[0].payload
    assert doc["analysis"] == {}
    assert doc["feedback"] == {}
    assert doc["score"] == {}
    assert "session-ana-2" in doc["chat_seed_context"]


def test_save_frame_persists_user_and_clerk_session(monkeypatch: pytest.MonkeyPatch):
    fake_db = FakeDb()
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    asyncio.run(
        store.save_frame(
            "session-frame-1",
            15_000,
            "API node added",
            "Noted the API service.",
            user_id="user_frame",
            clerk_session_id="sess_frame",
        )
    )

    assert len(fake_db.frames.insert_one_calls) == 1
    frame_doc = fake_db.frames.insert_one_calls[0]
    assert frame_doc["session_id"] == "session-frame-1"
    assert frame_doc["user_id"] == "user_frame"
    assert frame_doc["clerk_session_id"] == "sess_frame"
    assert frame_doc["timestamp_ms"] == 15_000
    assert frame_doc["visual_delta"] == "API node added"
    assert frame_doc["verbal_response"] == "Noted the API service."
    assert frame_doc["created_at"] is not None


def test_get_analysis_returns_doc(monkeypatch: pytest.MonkeyPatch):
    fake_db = FakeDb()
    fake_db.analysis.find_one_result = {"_id": "session-ana-3", "chat_seed_context": "ctx"}
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    result = asyncio.run(store.get_analysis("session-ana-3", user_id="user-3"))

    assert result == {"_id": "session-ana-3", "chat_seed_context": "ctx"}
    assert fake_db.analysis.find_one_calls == [{"_id": "session-ana-3", "user_id": "user-3"}]


def test_get_analysis_returns_none_for_empty_session_id(monkeypatch: pytest.MonkeyPatch):
    fake_db = FakeDb()
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    result = asyncio.run(store.get_analysis(""))

    assert result is None
    assert fake_db.analysis.find_one_calls == []


# ------------------------------------------------------------------ #
# user_id persistence tests                                            #
# ------------------------------------------------------------------ #

def test_save_session_stores_user_id_in_document(monkeypatch: pytest.MonkeyPatch):
    """user_id must be written into the sessions collection document."""
    fake_db = FakeDb()
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    graph = _make_graph()
    asyncio.run(store.save_session(graph, "sess-uid-1", user_id="user_alice_111"))

    doc = fake_db.sessions.replace_one_calls[0].payload
    assert doc["user_id"] == "user_alice_111"


def test_save_session_defaults_user_id_to_empty_string(monkeypatch: pytest.MonkeyPatch):
    """When user_id is omitted, the field must still be present but empty."""
    fake_db = FakeDb()
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    graph = _make_graph()
    asyncio.run(store.save_session(graph, "sess-uid-2"))

    doc = fake_db.sessions.replace_one_calls[0].payload
    assert doc["user_id"] == ""


def test_save_analysis_stores_user_id_in_document(monkeypatch: pytest.MonkeyPatch):
    """user_id must be written into the analysis collection document."""
    fake_db = FakeDb()
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    asyncio.run(store.save_analysis("sess-uid-3", {}, user_id="user_bob_222"))

    doc = fake_db.analysis.replace_one_calls[0].payload
    assert doc["user_id"] == "user_bob_222"


def test_save_analysis_defaults_user_id_to_empty_string(monkeypatch: pytest.MonkeyPatch):
    """When user_id is omitted on save_analysis, field must still be present but empty."""
    fake_db = FakeDb()
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    asyncio.run(store.save_analysis("sess-uid-4", {}))

    doc = fake_db.analysis.replace_one_calls[0].payload
    assert doc["user_id"] == ""


def test_get_analysis_returns_user_id_from_stored_document(monkeypatch: pytest.MonkeyPatch):
    """get_analysis must return the full document including user_id."""
    fake_db = FakeDb()
    fake_db.analysis.find_one_result = {
        "_id": "sess-uid-5",
        "user_id": "user_alice_111",
        "chat_seed_context": "ctx",
    }
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    result = asyncio.run(store.get_analysis("sess-uid-5"))

    assert result["user_id"] == "user_alice_111"


def test_different_users_sessions_store_distinct_user_ids(monkeypatch: pytest.MonkeyPatch):
    """Two save_session calls with different user_ids must each write the correct value."""
    fake_db_a = FakeDb()
    fake_client_a = FakeClient(fake_db_a)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client_a)
    store_a = session_store.SessionStore("mongodb://unit-test")

    graph = _make_graph()
    asyncio.run(store_a.save_session(graph, "sess-user-a", user_id="user_alice_111"))

    fake_db_b = FakeDb()
    fake_client_b = FakeClient(fake_db_b)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client_b)
    store_b = session_store.SessionStore("mongodb://unit-test")

    asyncio.run(store_b.save_session(graph, "sess-user-b", user_id="user_bob_222"))

    doc_a = fake_db_a.sessions.replace_one_calls[0].payload
    doc_b = fake_db_b.sessions.replace_one_calls[0].payload
    assert doc_a["user_id"] == "user_alice_111"
    assert doc_b["user_id"] == "user_bob_222"
    assert doc_a["user_id"] != doc_b["user_id"]
