"""
In-memory graph data structure for real-time system design analysis.

Nodes represent system components (services, databases, load balancers, etc.).
Edges represent connections/relationships between components.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Node:
    id: str
    label: str
    type: str
    details: dict = field(default_factory=dict)


@dataclass
class Edge:
    from_id: str
    to_id: str
    label: str = ""


class SystemDesignGraph:
    """
    Directed graph representing a system architecture design.
    Maintains nodes (components) and edges (connections) as the
    single source of truth for the AI analysis agent.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        # Adjacency: from_id -> list of Edge
        self._edges: dict[str, list[Edge]] = {}
        # The logical entry point for BFS traversal (set explicitly by the AI)
        self._entry_point: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Node operations                                                      #
    # ------------------------------------------------------------------ #

    def create_node(self, id: str, label: str, type: str) -> Node:
        """Add a new component node. Raises if id already exists."""
        if id in self._nodes:
            raise ValueError(f"Node '{id}' already exists.")
        node = Node(id=id, label=label, type=type)
        self._nodes[id] = node
        self._edges[id] = []
        return node

    def add_details_to_node(self, id: str, details: dict) -> Node:
        """Merge additional details into an existing node."""
        node = self._get_node(id)
        node.details.update(details)
        return node

    def delete_node(self, id: str) -> None:
        """Remove a node and all edges incident to it."""
        self._get_node(id)
        del self._nodes[id]
        del self._edges[id]
        for adj in self._edges.values():
            adj[:] = [e for e in adj if e.to_id != id]

    def set_entry_point(self, id: str) -> None:
        """
        Designate which node is the logical start of the design.
        BFS traversal will begin here instead of the first-inserted node.
        Call this when the AI identifies the user-facing entry (e.g. 'Client Browser').
        """
        self._get_node(id)
        self._entry_point = id

    def insert_node_between(
        self,
        from_id: str,
        new_id: str,
        new_label: str,
        new_type: str,
        to_id: str,
        from_label: str = "",
        to_label: str = "",
    ) -> Node:
        """
        Atomically insert a new node between two already-connected nodes.

        Before: from_id ──[old edge]──▶ to_id
        After:  from_id ──▶ new_id ──▶ to_id

        The old edge is removed and replaced with two new ones.
        Raises if the edge from_id → to_id does not exist.
        """
        # Verify the edge exists before mutating anything
        if not any(e.to_id == to_id for e in self._edges.get(from_id, [])):
            raise ValueError(f"No edge from '{from_id}' to '{to_id}' — cannot insert between them.")

        node = self.create_node(id=new_id, label=new_label, type=new_type)
        self.remove_edge(from_id=from_id, to_id=to_id)
        self.add_edge(from_id=from_id, to_id=new_id, label=from_label)
        self.add_edge(from_id=new_id, to_id=to_id, label=to_label)
        return node

    # ------------------------------------------------------------------ #
    # Edge operations                                                      #
    # ------------------------------------------------------------------ #

    def add_edge(self, from_id: str, to_id: str, label: str = "") -> Edge:
        """Add a directed edge between two existing nodes."""
        self._get_node(from_id)
        self._get_node(to_id)
        for e in self._edges[from_id]:
            if e.to_id == to_id:
                raise ValueError(f"Edge from '{from_id}' to '{to_id}' already exists.")
        edge = Edge(from_id=from_id, to_id=to_id, label=label)
        self._edges[from_id].append(edge)
        return edge

    def remove_edge(self, from_id: str, to_id: str) -> None:
        """Remove the directed edge from from_id to to_id."""
        self._get_node(from_id)
        before = len(self._edges[from_id])
        self._edges[from_id] = [e for e in self._edges[from_id] if e.to_id != to_id]
        if len(self._edges[from_id]) == before:
            raise ValueError(f"No edge from '{from_id}' to '{to_id}'.")

    # ------------------------------------------------------------------ #
    # Query / serialization                                                #
    # ------------------------------------------------------------------ #

    def get_state(self) -> dict:
        """Return current graph state as a plain dict."""
        return {
            "entry_point": self._entry_point,
            "nodes": [
                {"id": n.id, "label": n.label, "type": n.type, "details": n.details}
                for n in self._nodes.values()
            ],
            "edges": [
                {"from": e.from_id, "to": e.to_id, "label": e.label}
                for adj in self._edges.values()
                for e in adj
            ],
        }

    def bfs_order(self, start_id: Optional[str] = None) -> list[str]:
        """Return node IDs in BFS traversal order.
        Priority: explicit start_id > entry_point > first inserted node."""
        if not self._nodes:
            return []
        root = start_id or self._entry_point or next(iter(self._nodes))
        if root not in self._nodes:
            raise ValueError(f"Start node '{root}' not found.")
        visited: set[str] = {root}
        queue: deque[str] = deque([root])
        order: list[str] = []
        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for edge in self._edges.get(node_id, []):
                if edge.to_id not in visited:
                    visited.add(edge.to_id)
                    queue.append(edge.to_id)
        for node_id in self._nodes:
            if node_id not in visited:
                order.append(node_id)
        return order

    def bfs_serialize(self, start_id: Optional[str] = None) -> str:
        """
        BFS traversal from start_id (defaults to first inserted node).
        Returns a structured text document suitable for post-session scoring.
        """
        if not self._nodes:
            return "Graph is empty."

        root = start_id or self._entry_point or next(iter(self._nodes))
        if root not in self._nodes:
            raise ValueError(f"Start node '{root}' not found.")

        visited: set[str] = set()
        queue: deque[str] = deque([root])
        visited.add(root)
        lines: list[str] = ["# System Design — BFS Traversal\n"]

        while queue:
            node_id = queue.popleft()
            node = self._nodes[node_id]
            lines.append(f"## [{node.type}] {node.label}  (id: {node_id})")
            if node.details:
                for k, v in node.details.items():
                    lines.append(f"  - {k}: {v}")
            outgoing = self._edges.get(node_id, [])
            if outgoing:
                lines.append("  Connections:")
                for edge in outgoing:
                    target = self._nodes.get(edge.to_id)
                    target_label = target.label if target else edge.to_id
                    arrow = f" [{edge.label}]" if edge.label else ""
                    lines.append(f"    -> {target_label} (id: {edge.to_id}){arrow}")
                    if edge.to_id not in visited:
                        visited.add(edge.to_id)
                        queue.append(edge.to_id)
            lines.append("")

        unreachable = [n for n in self._nodes if n not in visited]
        if unreachable:
            lines.append("## Disconnected Components")
            for node_id in unreachable:
                node = self._nodes[node_id]
                lines.append(f"  - [{node.type}] {node.label}  (id: {node_id})")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _get_node(self, id: str) -> Node:
        if id not in self._nodes:
            raise ValueError(f"Node '{id}' not found.")
        return self._nodes[id]

    def __len__(self) -> int:
        return len(self._nodes)
