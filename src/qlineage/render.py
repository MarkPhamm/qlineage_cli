from __future__ import annotations

import json
import re

from .columns import ColumnNode
from .models import Graph
from .ui.html import render_html as _render_html


def _tree_lines(
    graph: Graph,
    node_id: str,
    prefix: str = "",
    seen: set[str] | None = None,
) -> list[str]:
    seen = seen or set()
    node = graph.nodes[node_id]
    lines = [f"{prefix}{node.label}"]
    if node_id in seen:
        lines[-1] += " (shared)"
        return lines
    next_seen = {*seen, node_id}
    children = graph.upstream(node_id)
    for i, child in enumerate(children):
        last = i == len(children) - 1
        connector = "└── " if last else "├── "
        child_prefix = prefix + ("    " if last else "│   ")
        child_lines = _tree_lines(graph, child, "", next_seen)
        lines.append(prefix + connector + child_lines[0])
        for continuation in child_lines[1:]:
            lines.append(child_prefix + continuation)
    return lines


def render_tree(graph: Graph) -> str:
    return "\n".join(_tree_lines(graph, graph.root))


def render_json(graph: Graph) -> str:
    return json.dumps(graph.to_dict(), indent=2, sort_keys=True)


def _mermaid_id(value: str) -> str:
    return "n_" + re.sub(r"[^a-zA-Z0-9_]", "_", value)


def render_mermaid(graph: Graph) -> str:
    lines = ["flowchart TD"]
    for node in graph.nodes.values():
        safe_label = node.label.replace('"', "'")
        lines.append(f'  {_mermaid_id(node.id)}["{safe_label}"]')
    for edge in graph.edges:
        lines.append(f"  {_mermaid_id(edge.source)} --> {_mermaid_id(edge.target)}")
    return "\n".join(lines)


def render_html(
    graph: Graph | None,
    sql: str = "",
    *,
    column: ColumnNode | None = None,
    static: bool = True,
    dialect: str = "snowflake",
    root_name: str = "query",
) -> str:
    return _render_html(
        graph,
        sql,
        column=column,
        static=static,
        dialect=dialect,
        root_name=root_name,
    )


def render_column_tree(root: ColumnNode) -> str:
    lines: list[str] = []

    def visit(node: ColumnNode, prefix: str, is_last: bool, is_root: bool = False) -> None:
        if is_root:
            lines.append(node.name)
        else:
            lines.append(prefix + ("└── " if is_last else "├── ") + node.name)
        child_prefix = prefix + ("    " if is_last else "│   ") if not is_root else ""
        for i, child in enumerate(node.children):
            visit(child, child_prefix, i == len(node.children) - 1)

    visit(root, "", True, True)
    return "\n".join(lines)
