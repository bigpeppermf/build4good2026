"""
Unit tests for core/graph.py — SystemDesignGraph.

All tests are pure in-memory; no external services required.
"""

import pytest

from core.graph import Edge, Node, SystemDesignGraph


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def three_node_graph() -> SystemDesignGraph:
    """client → api → database"""
    g = SystemDesignGraph()
    g.create_node("client", "Client Browser", "client")
    g.create_node("api", "API", "service")
    g.create_node("db", "Database", "database")
    g.add_edge("client", "api", "HTTP")
    g.add_edge("api", "db", "writes to")
    g.set_entry_point("client")
    return g


# ------------------------------------------------------------------ #
# create_node                                                          #
# ------------------------------------------------------------------ #

class TestCreateNode:
    def test_returns_node_with_correct_fields(self):
        g = SystemDesignGraph()
        node = g.create_node("api", "API Gateway", "service")
        assert isinstance(node, Node)
        assert node.id == "api"
        assert node.label == "API Gateway"
        assert node.type == "service"
        assert node.details == {}

    def test_increments_len(self):
        g = SystemDesignGraph()
        assert len(g) == 0
        g.create_node("a", "A", "service")
        assert len(g) == 1
        g.create_node("b", "B", "service")
        assert len(g) == 2

    def test_duplicate_id_raises(self):
        g = SystemDesignGraph()
        g.create_node("api", "API", "service")
        with pytest.raises(ValueError, match="already exists"):
            g.create_node("api", "Another API", "service")

    def test_node_appears_in_get_state(self):
        g = SystemDesignGraph()
        g.create_node("cache", "Redis", "cache")
        state = g.get_state()
        ids = [n["id"] for n in state["nodes"]]
        assert "cache" in ids


# ------------------------------------------------------------------ #
# add_details_to_node                                                  #
# ------------------------------------------------------------------ #

class TestAddDetailsToNode:
    def test_merges_new_keys(self):
        g = SystemDesignGraph()
        g.create_node("db", "DB", "database")
        g.add_details_to_node("db", {"technology": "PostgreSQL"})
        g.add_details_to_node("db", {"role": "primary"})
        state = g.get_state()
        node = next(n for n in state["nodes"] if n["id"] == "db")
        assert node["details"] == {"technology": "PostgreSQL", "role": "primary"}

    def test_overwrites_existing_key(self):
        g = SystemDesignGraph()
        g.create_node("db", "DB", "database")
        g.add_details_to_node("db", {"technology": "MySQL"})
        g.add_details_to_node("db", {"technology": "PostgreSQL"})
        state = g.get_state()
        node = next(n for n in state["nodes"] if n["id"] == "db")
        assert node["details"]["technology"] == "PostgreSQL"

    def test_missing_node_raises(self):
        g = SystemDesignGraph()
        with pytest.raises(ValueError, match="not found"):
            g.add_details_to_node("ghost", {"key": "val"})


# ------------------------------------------------------------------ #
# delete_node                                                          #
# ------------------------------------------------------------------ #

class TestDeleteNode:
    def test_removes_node_from_state(self):
        g = three_node_graph()
        g.delete_node("api")
        ids = [n["id"] for n in g.get_state()["nodes"]]
        assert "api" not in ids

    def test_removes_outgoing_edges(self):
        g = three_node_graph()
        g.delete_node("api")
        edges = g.get_state()["edges"]
        assert not any(e["from"] == "api" for e in edges)

    def test_removes_incoming_edges(self):
        g = three_node_graph()
        g.delete_node("api")
        edges = g.get_state()["edges"]
        assert not any(e["to"] == "api" for e in edges)

    def test_decrements_len(self):
        g = three_node_graph()
        assert len(g) == 3
        g.delete_node("db")
        assert len(g) == 2

    def test_missing_node_raises(self):
        g = SystemDesignGraph()
        with pytest.raises(ValueError, match="not found"):
            g.delete_node("ghost")


# ------------------------------------------------------------------ #
# add_edge                                                             #
# ------------------------------------------------------------------ #

class TestAddEdge:
    def test_returns_edge_with_correct_fields(self):
        g = SystemDesignGraph()
        g.create_node("a", "A", "service")
        g.create_node("b", "B", "service")
        edge = g.add_edge("a", "b", "calls")
        assert isinstance(edge, Edge)
        assert edge.from_id == "a"
        assert edge.to_id == "b"
        assert edge.label == "calls"

    def test_default_label_is_empty_string(self):
        g = SystemDesignGraph()
        g.create_node("a", "A", "service")
        g.create_node("b", "B", "service")
        edge = g.add_edge("a", "b")
        assert edge.label == ""

    def test_edge_appears_in_get_state(self):
        g = SystemDesignGraph()
        g.create_node("lb", "Load Balancer", "load_balancer")
        g.create_node("api", "API", "service")
        g.add_edge("lb", "api", "routes to")
        edges = g.get_state()["edges"]
        assert any(e["from"] == "lb" and e["to"] == "api" for e in edges)

    def test_duplicate_edge_raises(self):
        g = SystemDesignGraph()
        g.create_node("a", "A", "service")
        g.create_node("b", "B", "service")
        g.add_edge("a", "b")
        with pytest.raises(ValueError, match="already exists"):
            g.add_edge("a", "b")

    def test_missing_from_node_raises(self):
        g = SystemDesignGraph()
        g.create_node("b", "B", "service")
        with pytest.raises(ValueError, match="not found"):
            g.add_edge("ghost", "b")

    def test_missing_to_node_raises(self):
        g = SystemDesignGraph()
        g.create_node("a", "A", "service")
        with pytest.raises(ValueError, match="not found"):
            g.add_edge("a", "ghost")


# ------------------------------------------------------------------ #
# remove_edge                                                          #
# ------------------------------------------------------------------ #

class TestRemoveEdge:
    def test_edge_no_longer_in_state(self):
        g = three_node_graph()
        g.remove_edge("client", "api")
        edges = g.get_state()["edges"]
        assert not any(e["from"] == "client" and e["to"] == "api" for e in edges)

    def test_other_edges_unaffected(self):
        g = three_node_graph()
        g.remove_edge("client", "api")
        edges = g.get_state()["edges"]
        assert any(e["from"] == "api" and e["to"] == "db" for e in edges)

    def test_missing_edge_raises(self):
        g = SystemDesignGraph()
        g.create_node("a", "A", "service")
        g.create_node("b", "B", "service")
        with pytest.raises(ValueError, match="No edge"):
            g.remove_edge("a", "b")

    def test_missing_from_node_raises(self):
        g = SystemDesignGraph()
        g.create_node("b", "B", "service")
        with pytest.raises(ValueError, match="not found"):
            g.remove_edge("ghost", "b")


# ------------------------------------------------------------------ #
# set_entry_point                                                      #
# ------------------------------------------------------------------ #

class TestSetEntryPoint:
    def test_entry_point_appears_in_state(self):
        g = SystemDesignGraph()
        g.create_node("client", "Client", "client")
        g.set_entry_point("client")
        assert g.get_state()["entry_point"] == "client"

    def test_entry_point_can_be_changed(self):
        g = SystemDesignGraph()
        g.create_node("a", "A", "client")
        g.create_node("b", "B", "client")
        g.set_entry_point("a")
        g.set_entry_point("b")
        assert g.get_state()["entry_point"] == "b"

    def test_missing_node_raises(self):
        g = SystemDesignGraph()
        with pytest.raises(ValueError, match="not found"):
            g.set_entry_point("ghost")

    def test_default_entry_point_is_none(self):
        g = SystemDesignGraph()
        assert g.get_state()["entry_point"] is None


# ------------------------------------------------------------------ #
# insert_node_between                                                  #
# ------------------------------------------------------------------ #

class TestInsertNodeBetween:
    def test_new_node_exists_in_state(self):
        g = three_node_graph()
        g.insert_node_between("client", "lb", "Load Balancer", "load_balancer", "api")
        ids = [n["id"] for n in g.get_state()["nodes"]]
        assert "lb" in ids

    def test_old_direct_edge_removed(self):
        g = three_node_graph()
        g.insert_node_between("client", "lb", "Load Balancer", "load_balancer", "api")
        edges = g.get_state()["edges"]
        assert not any(e["from"] == "client" and e["to"] == "api" for e in edges)

    def test_two_new_edges_created(self):
        g = three_node_graph()
        g.insert_node_between("client", "lb", "Load Balancer", "load_balancer", "api",
                               from_label="forwards to", to_label="distributes to")
        edges = g.get_state()["edges"]
        assert any(e["from"] == "client" and e["to"] == "lb" and e["label"] == "forwards to"
                   for e in edges)
        assert any(e["from"] == "lb" and e["to"] == "api" and e["label"] == "distributes to"
                   for e in edges)

    def test_no_edge_raises(self):
        g = SystemDesignGraph()
        g.create_node("a", "A", "service")
        g.create_node("b", "B", "service")
        with pytest.raises(ValueError, match="No edge"):
            g.insert_node_between("a", "mid", "Mid", "service", "b")

    def test_duplicate_new_id_raises(self):
        g = three_node_graph()
        with pytest.raises(ValueError, match="already exists"):
            # edge client→api exists; "db" is the new_id but already exists in graph
            g.insert_node_between("client", "db", "DB Copy", "database", "api")


# ------------------------------------------------------------------ #
# get_state                                                            #
# ------------------------------------------------------------------ #

class TestGetState:
    def test_empty_graph(self):
        g = SystemDesignGraph()
        state = g.get_state()
        assert state == {"entry_point": None, "nodes": [], "edges": []}

    def test_node_fields_present(self):
        g = SystemDesignGraph()
        g.create_node("svc", "Service", "service")
        node = g.get_state()["nodes"][0]
        assert set(node.keys()) == {"id", "label", "type", "details"}

    def test_edge_fields_present(self):
        g = SystemDesignGraph()
        g.create_node("a", "A", "service")
        g.create_node("b", "B", "service")
        g.add_edge("a", "b", "calls")
        edge = g.get_state()["edges"][0]
        assert set(edge.keys()) == {"from", "to", "label"}


# ------------------------------------------------------------------ #
# bfs_order                                                            #
# ------------------------------------------------------------------ #

class TestBfsOrder:
    def test_starts_from_entry_point(self):
        g = three_node_graph()
        order = g.bfs_order()
        assert order[0] == "client"

    def test_correct_traversal_order(self):
        g = three_node_graph()
        order = g.bfs_order()
        # client → api → db
        assert order.index("client") < order.index("api") < order.index("db")

    def test_disconnected_nodes_appended(self):
        g = three_node_graph()
        g.create_node("orphan", "Orphan", "service")
        order = g.bfs_order()
        assert "orphan" in order
        # orphan comes after all reachable nodes
        assert order.index("orphan") > order.index("db")

    def test_explicit_start_overrides_entry_point(self):
        g = three_node_graph()
        order = g.bfs_order(start_id="api")
        assert order[0] == "api"

    def test_empty_graph_returns_empty_list(self):
        g = SystemDesignGraph()
        assert g.bfs_order() == []

    def test_unknown_start_raises(self):
        g = three_node_graph()
        with pytest.raises(ValueError, match="not found"):
            g.bfs_order(start_id="ghost")


# ------------------------------------------------------------------ #
# bfs_serialize                                                        #
# ------------------------------------------------------------------ #

class TestBfsSerialize:
    def test_returns_string(self):
        g = three_node_graph()
        result = g.bfs_serialize()
        assert isinstance(result, str)

    def test_contains_node_labels(self):
        g = three_node_graph()
        result = g.bfs_serialize()
        assert "Client Browser" in result
        assert "API" in result
        assert "Database" in result

    def test_contains_node_ids(self):
        g = three_node_graph()
        result = g.bfs_serialize()
        assert "client" in result
        assert "api" in result
        assert "db" in result

    def test_empty_graph_message(self):
        g = SystemDesignGraph()
        assert g.bfs_serialize() == "Graph is empty."

    def test_disconnected_section_present(self):
        g = three_node_graph()
        g.create_node("orphan", "Orphan Service", "service")
        result = g.bfs_serialize()
        assert "Disconnected" in result
        assert "Orphan Service" in result

    def test_details_included(self):
        g = three_node_graph()
        g.add_details_to_node("db", {"technology": "PostgreSQL"})
        result = g.bfs_serialize()
        assert "PostgreSQL" in result


# ------------------------------------------------------------------ #
# __len__                                                              #
# ------------------------------------------------------------------ #

class TestLen:
    def test_empty(self):
        assert len(SystemDesignGraph()) == 0

    def test_after_creates(self):
        g = SystemDesignGraph()
        g.create_node("a", "A", "service")
        g.create_node("b", "B", "service")
        assert len(g) == 2

    def test_after_delete(self):
        g = three_node_graph()
        g.delete_node("db")
        assert len(g) == 2
