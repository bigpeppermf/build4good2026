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

    async def find_one(self, filter_doc: dict) -> Any:
        self.find_one_calls.append(filter_doc)
        return self.find_one_result


@dataclass
class FakeDb:
    sessions: FakeCollection = field(default_factory=FakeCollection)
    nodes: FakeCollection = field(default_factory=FakeCollection)
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
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    graph = _make_graph()
    summary = asyncio.run(
        store.save_session(
            graph,
            "session-123",
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

    assert len(fake_db.sessions.replace_one_calls) == 1
    session_write = fake_db.sessions.replace_one_calls[0]
    assert session_write.filter_doc == {"_id": "session-123"}
    assert session_write.upsert is True
    assert session_write.session is fake_client.last_session
    assert session_write.payload["audio_transcript"] == "Browser sends traffic to API then DB."
    assert session_write.payload["validation_corrections"] == 2
    assert session_write.payload["validation_summary"] == "Added DB connection from transcript."
    assert session_write.payload["graph_confidence"] == pytest.approx(0.66)

    assert len(fake_db.nodes.delete_many_calls) == 1
    assert fake_db.nodes.delete_many_calls[0].filter_doc == {"session_id": "session-123"}
    assert fake_db.nodes.delete_many_calls[0].session is fake_client.last_session

    assert len(fake_db.nodes.insert_many_calls) == 1
    node_write = fake_db.nodes.insert_many_calls[0]
    assert node_write.session is fake_client.last_session
    node_ids = {doc["node_id"] for doc in node_write.payload}
    assert node_ids == {"client", "api", "db"}


def test_save_session_falls_back_when_transactions_are_unsupported(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_db = FakeDb()
    fake_client = NoTransactionClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    graph = _make_graph()
    asyncio.run(store.save_session(graph, "session-no-tx"))

    assert len(fake_db.sessions.replace_one_calls) == 1
    session_write = fake_db.sessions.replace_one_calls[0]
    assert session_write.session is None
    assert session_write.payload["audio_transcript"] == ""
    assert session_write.payload["validation_corrections"] == 0
    assert session_write.payload["validation_summary"] == "Graph matches transcript"
    assert session_write.payload["graph_confidence"] == 1.0

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
    result = asyncio.run(store.save_analysis("session-ana-1", analysis_output))

    assert result["session_id"] == "session-ana-1"
    assert result["analysis_saved"] is True
    assert result["score_total"] == 78

    assert len(fake_db.analysis.replace_one_calls) == 1
    analysis_write = fake_db.analysis.replace_one_calls[0]
    assert analysis_write.filter_doc == {"_id": "session-ana-1"}
    assert analysis_write.upsert is True
    doc = analysis_write.payload
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


def test_get_analysis_returns_doc(monkeypatch: pytest.MonkeyPatch):
    fake_db = FakeDb()
    fake_db.analysis.find_one_result = {"_id": "session-ana-3", "chat_seed_context": "ctx"}
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    result = asyncio.run(store.get_analysis("session-ana-3"))

    assert result == {"_id": "session-ana-3", "chat_seed_context": "ctx"}
    assert fake_db.analysis.find_one_calls == [{"_id": "session-ana-3"}]


def test_get_analysis_returns_none_for_empty_session_id(monkeypatch: pytest.MonkeyPatch):
    fake_db = FakeDb()
    fake_client = FakeClient(fake_db)
    monkeypatch.setattr(session_store, "AsyncIOMotorClient", lambda _uri: fake_client)
    store = session_store.SessionStore("mongodb://unit-test")

    result = asyncio.run(store.get_analysis(""))

    assert result is None
    assert fake_db.analysis.find_one_calls == []
