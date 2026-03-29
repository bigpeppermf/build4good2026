"""
Persists a completed design session to MongoDB Atlas.

Schema
------
Database : system_design

Collection: sessions
  {
    "_id":              str   (session_id),
    "user_id":          str   (Clerk user ID — owner of this session),
    "clerk_session_id": str | null,
    "created_at":       datetime,
    "traversal_order":  [str, ...],   # node IDs in BFS order
    "edges":            [{"from": str, "to": str, "label": str}, ...],
    "audio_transcript": str,
    "validation_corrections": int,
    "validation_summary": str,
    "graph_confidence": float
  }

Collection: nodes
  {
    "session_id":       str,
    "user_id":          str | null,
    "clerk_session_id": str | null,
    "node_id":          str,
    "label":            str,
    "type":             str,
    "traversal_index":  int,   # position in traversal_order, -1 if disconnected
    "details":          dict,
    "created_at":       datetime
  }

Collection: frames
  {
    "session_id":       str,
    "user_id":          str | null,
    "clerk_session_id": str | null,
    "timestamp_ms":     int,
    "visual_delta":     str,
    "verbal_response":  str,
    "created_at":       datetime
  }

Collection: analysis
  {
    "_id":              str   (session_id),
    "user_id":          str   (Clerk user ID — owner of this session),
    "clerk_session_id": str | null,
    "created_at":       datetime,
    "analysis":         dict,
    "feedback":         dict,
    "score":            dict,
    "chat_seed_context": str
  }
"""

from __future__ import annotations

from datetime import datetime, timezone

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from core.graph import SystemDesignGraph

DB_NAME = "system_design"


class SessionStore:
    def __init__(self, uri: str) -> None:
        # Atlas URIs use TLS; supply certifi's CA bundle so macOS Python can
        # verify the certificate chain without relying on the system keychain.
        use_tls = "mongodb.net" in uri or "+srv" in uri
        self._client = (
            AsyncIOMotorClient(uri, tlsCAFile=certifi.where())
            if use_tls
            else AsyncIOMotorClient(uri)
        )
        self._db = self._client[DB_NAME]

    async def _save_without_transaction(
        self,
        session_id: str,
        session_doc: dict,
        node_docs: list[dict],
    ) -> None:
        """
        Fallback write path used when Mongo transactions are unavailable.

        ``replace_one + delete_many + insert_many`` makes writes idempotent if the
        same session_id is persisted more than once.
        """
        await self._db.sessions.replace_one({"_id": session_id}, session_doc, upsert=True)
        await self._db.nodes.delete_many({"session_id": session_id})
        if node_docs:
            await self._db.nodes.insert_many(node_docs)

    async def _save_atomic(
        self,
        session_id: str,
        session_doc: dict,
        node_docs: list[dict],
    ) -> None:
        """
        Persist session + node documents in one transaction when supported.

        For local standalone MongoDB (no replica set), transactions are not
        available. In that case we gracefully fall back to non-transactional
        idempotent writes.
        """
        unsupported_txn_keywords = (
            "transaction numbers are only allowed on a replica set member or mongos",
            "transaction not supported",
            "replica set",
        )

        try:
            async with await self._client.start_session() as mongo_session:
                async with mongo_session.start_transaction():
                    await self._db.sessions.replace_one(
                        {"_id": session_id},
                        session_doc,
                        upsert=True,
                        session=mongo_session,
                    )
                    await self._db.nodes.delete_many(
                        {"session_id": session_id},
                        session=mongo_session,
                    )
                    if node_docs:
                        await self._db.nodes.insert_many(node_docs, session=mongo_session)
                return
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if not any(token in message for token in unsupported_txn_keywords):
                raise

        await self._save_without_transaction(session_id, session_doc, node_docs)

    async def save_frame(
        self,
        session_id: str,
        timestamp_ms: int,
        visual_delta: str,
        verbal_response: str,
        *,
        user_id: str | None = None,
        clerk_session_id: str | None = None,
    ) -> None:
        """Persist a single processed frame result for a session."""
        await self._db.frames.insert_one(
            {
                "session_id": session_id,
                "user_id": user_id,
                "clerk_session_id": clerk_session_id,
                "timestamp_ms": timestamp_ms,
                "visual_delta": visual_delta,
                "verbal_response": verbal_response,
                "created_at": datetime.now(timezone.utc),
            }
        )

    async def save_session(
        self,
        graph: SystemDesignGraph,
        session_id: str,
        *,
        user_id: str | None = None,
        clerk_session_id: str | None = None,
        audio_transcript: str = "",
        validation_corrections: int = 0,
        validation_summary: str = "Graph matches transcript",
        graph_confidence: float = 1.0,
    ) -> dict:
        """
        Persist the completed graph to MongoDB.
        Returns a summary dict with counts for confirmation.
        """
        state = graph.get_state()
        traversal_order = graph.bfs_order()
        order_index = {node_id: idx for idx, node_id in enumerate(traversal_order)}
        now = datetime.now(timezone.utc)
        normalized_transcript = (audio_transcript or "").strip()
        normalized_summary = (validation_summary or "").strip() or "Graph matches transcript"
        normalized_corrections = max(0, int(validation_corrections))
        try:
            normalized_confidence = float(graph_confidence)
        except (TypeError, ValueError):
            normalized_confidence = 1.0
        normalized_confidence = max(0.0, min(1.0, normalized_confidence))

        # Count frames already saved for this session.
        frames_saved = await self._db.frames.count_documents(
            {"session_id": session_id}
        )

        session_doc = {
            "_id": session_id,
            "user_id": user_id or "",
            "clerk_session_id": clerk_session_id,
            "created_at": now,
            "traversal_order": traversal_order,
            "edges": state["edges"],
            "audio_transcript": normalized_transcript,
            "validation_corrections": normalized_corrections,
            "validation_summary": normalized_summary,
            "graph_confidence": normalized_confidence,
            "frames_count": frames_saved,
        }
        node_docs = [
            {
                "session_id": session_id,
                "user_id": user_id,
                "clerk_session_id": clerk_session_id,
                "node_id": n["id"],
                "label": n["label"],
                "type": n["type"],
                "traversal_index": order_index.get(n["id"], -1),
                "details": n["details"],
                "created_at": now,
            }
            for n in state["nodes"]
        ]
        await self._save_atomic(session_id, session_doc, node_docs)

        return {
            "session_id": session_id,
            "nodes_saved": len(state["nodes"]),
            "edges_saved": len(state["edges"]),
            "frames_saved": frames_saved,
            "traversal_order": traversal_order,
            "validation_corrections": normalized_corrections,
            "validation_summary": normalized_summary,
            "graph_confidence": normalized_confidence,
        }

    def _build_chat_seed_context(
        self,
        session_id: str,
        analysis: dict,
        feedback: dict,
        score: dict,
    ) -> str:
        """
        Build a compact text context for follow-up chat grounded in saved analysis.
        """
        pattern = str(analysis.get("architecture_pattern", "")).strip()
        summary = str(analysis.get("summary", "")).strip()
        strengths = feedback.get("strengths")
        improvements = feedback.get("improvements")
        total_score = score.get("total")
        grade = str(score.get("grade", "")).strip().upper()

        top_strength = ""
        if isinstance(strengths, list) and strengths:
            top_strength = str(strengths[0]).strip()

        top_improvement = ""
        if isinstance(improvements, list) and improvements:
            top_improvement = str(improvements[0]).strip()

        lines = [
            f"Session {session_id} analysis context.",
            f"Architecture pattern: {pattern or 'unknown'}.",
            f"Summary: {summary or 'No summary provided.'}",
            (
                f"Score: {total_score}/100"
                + (f" ({grade})" if grade else "")
                + "."
            ),
        ]
        if top_strength:
            lines.append(f"Top strength: {top_strength}")
        if top_improvement:
            lines.append(f"Top improvement: {top_improvement}")
        return " ".join(lines)

    async def save_analysis(
        self,
        session_id: str,
        analysis_output: dict,
        *,
        user_id: str | None = None,
        clerk_session_id: str | None = None,
    ) -> dict:
        """
        Persist post-session analysis output to the analysis collection.
        """
        payload = analysis_output if isinstance(analysis_output, dict) else {}
        analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
        feedback = payload.get("feedback") if isinstance(payload.get("feedback"), dict) else {}
        score = payload.get("score") if isinstance(payload.get("score"), dict) else {}

        chat_seed_context = self._build_chat_seed_context(
            session_id=session_id,
            analysis=analysis,
            feedback=feedback,
            score=score,
        )
        now = datetime.now(timezone.utc)
        analysis_doc = {
            "_id": session_id,
            "user_id": user_id or "",
            "clerk_session_id": clerk_session_id,
            "created_at": now,
            "analysis": analysis,
            "feedback": feedback,
            "score": score,
            "chat_seed_context": chat_seed_context,
        }
        await self._db.analysis.replace_one({"_id": session_id}, analysis_doc, upsert=True)

        return {
            "session_id": session_id,
            "analysis_saved": True,
            "score_total": score.get("total"),
        }

    async def get_analysis(
        self,
        session_id: str,
        *,
        user_id: str | None = None,
    ) -> dict | None:
        """
        Load a stored analysis document for chat follow-up.
        """
        if not session_id:
            return None
        filter_doc: dict[str, str] = {"_id": session_id}
        if user_id:
            filter_doc["user_id"] = user_id
        doc = await self._db.analysis.find_one(filter_doc)
        return doc if isinstance(doc, dict) else None

    async def close(self) -> None:
        self._client.close()
