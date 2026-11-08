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


def _seen_upstream(graph: Graph, node_id: str, seen: set[str]) -> None:
    if node_id in seen:
        return
    seen.add(node_id)
    for child in graph.upstream(node_id):
        _seen_upstream(graph, child, seen)


def render_tree(graph: Graph) -> str:
    lines = _tree_lines(graph, graph.root)
    shown: set[str] = set()
    _seen_upstream(graph, graph.root, shown)
    if not any(node_id not in shown for node_id in graph.downstream(graph.root)):
        return "\n".join(lines)
    lines.append("downstream")
    lines.extend(_downstream_lines(graph, graph.root, "", shown))
    return "\n".join(lines)


def _downstream_lines(graph: Graph, node_id: str, prefix: str, shown: set[str]) -> list[str]:
    children = [child for child in graph.downstream(node_id) if child not in shown]
    lines: list[str] = []
    for index, child in enumerate(children):
        last = index == len(children) - 1
        connector = "└── " if last else "├── "
        child_prefix = prefix + ("    " if last else "│   ")
        label = graph.nodes[child].label
        lines.append(f"{prefix}{connector}{label}")
        shown.add(child)
        lines.extend(_downstream_lines(graph, child, child_prefix, shown))
    return lines


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


def render_markdown(graph: Graph, *, title: str = "query", source: str | None = None) -> str:
    lines = [f"# Lineage: {title}", ""]
    if source:
        lines.append(f"Source: `{source}`")
        lines.append("")
    lines.append("```mermaid")
    lines.append(render_mermaid(graph))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def render_html(
    graph: Graph | None,
    sql: str = "",
    *,
    column: ColumnNode | None = None,
    static: bool = True,
    dialect: str = "snowflake",
    root_name: str = "query",
    mode: str = "sql",
    models: dict | None = None,
    links: list[dict] | None = None,
) -> str:
    return _render_html(
        graph,
        sql,
        column=column,
        static=static,
        dialect=dialect,
        root_name=root_name,
        mode=mode,
        models=models,
        links=links,
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
