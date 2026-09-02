from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    kind: str


@dataclass(frozen=True)
class Edge:
    source: str
    target: str


@dataclass
class Graph:
    root: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node_id: str, label: str | None = None, kind: str = "unknown") -> None:
        existing = self.nodes.get(node_id)
        if existing:
            if existing.kind == "unknown" and kind != "unknown":
                self.nodes[node_id] = Node(node_id, label or existing.label, kind)
            return
        self.nodes[node_id] = Node(node_id, label or node_id, kind)

    def add_edge(self, source: str, target: str) -> None:
        edge = Edge(source, target)
        if edge not in self.edges:
            self.edges.append(edge)

    def upstream(self, node_id: str) -> list[str]:
        return [edge.target for edge in self.edges if edge.source == node_id]

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "nodes": [
                {"id": node.id, "label": node.label, "kind": node.kind}
                for node in self.nodes.values()
            ],
            "edges": [
                {"source": edge.source, "target": edge.target}
                for edge in self.edges
            ],
        }
