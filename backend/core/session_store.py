"""
Persists a completed design session to MongoDB Atlas.

Schema
------
Database : system_design

Collection: sessions
  {
    "_id":              str   (session_id),
    "created_at":       datetime,
    "traversal_order":  [str, ...],   # node IDs in BFS order
    "edges":            [{"from": str, "to": str, "label": str}, ...]
  }

Collection: nodes
  {
    "session_id":       str,
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
    "timestamp_ms":     int,
    "visual_delta":     str,
    "verbal_response":  str,
    "created_at":       datetime
  }
"""

from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from core.graph import SystemDesignGraph

DB_NAME = "system_design"


class SessionStore:
    def __init__(self, uri: str) -> None:
        self._client = AsyncIOMotorClient(uri)
        self._db = self._client[DB_NAME]

    async def save_frame(
        self,
        session_id: str,
        timestamp_ms: int,
        visual_delta: str,
        verbal_response: str,
    ) -> None:
        """Persist a single processed frame result for a session."""
        await self._db.frames.insert_one(
            {
                "session_id": session_id,
                "timestamp_ms": timestamp_ms,
                "visual_delta": visual_delta,
                "verbal_response": verbal_response,
                "created_at": datetime.now(timezone.utc),
            }
        )

    async def save_session(self, graph: SystemDesignGraph, session_id: str) -> dict:
        """
        Persist the completed graph to MongoDB.
        Returns a summary dict with counts for confirmation.
        """
        state = graph.get_state()
        traversal_order = graph.bfs_order()
        order_index = {node_id: idx for idx, node_id in enumerate(traversal_order)}
        now = datetime.now(timezone.utc)

        # Count frames already saved for this session.
        frames_saved = await self._db.frames.count_documents(
            {"session_id": session_id}
        )

        session_doc = {
            "_id": session_id,
            "created_at": now,
            "traversal_order": traversal_order,
            "edges": state["edges"],
            "frames_count": frames_saved,
        }
        await self._db.sessions.insert_one(session_doc)

        if state["nodes"]:
            node_docs = [
                {
                    "session_id": session_id,
                    "node_id": n["id"],
                    "label": n["label"],
                    "type": n["type"],
                    "traversal_index": order_index.get(n["id"], -1),
                    "details": n["details"],
                    "created_at": now,
                }
                for n in state["nodes"]
            ]
            await self._db.nodes.insert_many(node_docs)

        return {
            "session_id": session_id,
            "nodes_saved": len(state["nodes"]),
            "edges_saved": len(state["edges"]),
            "frames_saved": frames_saved,
            "traversal_order": traversal_order,
        }

    async def close(self) -> None:
        self._client.close()
