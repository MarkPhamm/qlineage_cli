from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Column:
    name: str
    type: str = "UNKNOWN"


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    kind: str
    sql: str | None = None
    columns: tuple[Column, ...] = ()
    join_keys: tuple[str, ...] = ()
    join_count: int = 0


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    columns: tuple[str, ...] = ()


@dataclass
class Graph:
    root: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node_id: str, label: str | None = None, kind: str = "unknown") -> None:
        existing = self.nodes.get(node_id)
        if existing:
            if existing.kind == "unknown" and kind != "unknown":
                self.nodes[node_id] = replace(existing, label=label or existing.label, kind=kind)
            return
        self.nodes[node_id] = Node(node_id, label or node_id, kind)

    def update_node(self, node_id: str, **changes) -> None:
        node = self.nodes.get(node_id)
        if node is None:
            return
        self.nodes[node_id] = replace(node, **changes)

    def add_edge(self, source: str, target: str, columns: tuple[str, ...] = ()) -> None:
        for index, edge in enumerate(self.edges):
            if edge.source == source and edge.target == target:
                if columns:
                    merged = tuple(dict.fromkeys([*edge.columns, *columns]))
                    self.edges[index] = replace(edge, columns=merged)
                return
        self.edges.append(Edge(source, target, columns))

    def upstream(self, node_id: str) -> list[str]:
        return [edge.target for edge in self.edges if edge.source == node_id]

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "kind": node.kind,
                    "sql": node.sql,
                    "columns": [
                        {"name": column.name, "type": column.type} for column in node.columns
                    ],
                    "joinKeys": list(node.join_keys),
                    "joinCount": node.join_count,
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "columns": list(edge.columns),
                }
                for edge in self.edges
            ],
        }
