from __future__ import annotations

from dataclasses import dataclass, field

from .jinja import replace_dbt_refs
from .parser import ParseError


@dataclass
class ColumnNode:
    name: str
    children: list["ColumnNode"] = field(default_factory=list)


def trace_column(sql: str, column: str, *, dialect: str) -> ColumnNode:
    try:
        from sqlglot.lineage import lineage
    except ImportError as exc:  # pragma: no cover
        raise ParseError("sqlglot is required for column lineage.") from exc

    prepared = replace_dbt_refs(sql)
    try:
        node = lineage(column, prepared, dialect=dialect)
    except Exception as exc:
        raise ParseError(str(exc)) from exc

    visited: set[int] = set()

    def convert(current) -> ColumnNode:
        if id(current) in visited:
            return ColumnNode(f"{current.name} (shared)")
        visited.add(id(current))
        return ColumnNode(current.name, [convert(child) for child in current.downstream])

    return convert(node)
