from __future__ import annotations

from pathlib import Path

from .jinja import display_name_for_placeholder, replace_dbt_refs
from .models import Graph


class ParseError(RuntimeError):
    pass


def _sqlglot():
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError as exc:  # pragma: no cover
        raise ParseError("sqlglot is required. Install qlineage-cli normally or run `pip install sqlglot`.") from exc
    return sqlglot, exp


def _table_name(table) -> str:
    parts = [getattr(table, "catalog", None), getattr(table, "db", None), getattr(table, "name", None)]
    return ".".join(str(part) for part in parts if part)


def _normalize_relation(name: str) -> str:
    return name.replace('"', "").lower()


def parse_sql_graph(
    sql: str,
    *,
    dialect: str,
    root_name: str = "query",
    relation_labels: dict[str, str] | None = None,
) -> Graph:
    sqlglot, exp = _sqlglot()
    relation_labels = relation_labels or {}
    prepared = replace_dbt_refs(sql)

    try:
        expression = sqlglot.parse_one(prepared, read=dialect)
    except Exception as exc:  # sqlglot exposes multiple parse error classes
        raise ParseError(str(exc)) from exc

    graph = Graph(root=root_name)
    graph.add_node(root_name, root_name, "query")

    ctes = {cte.alias_or_name: cte for cte in expression.ctes}
    cte_names = set(ctes)

    def add_dependency(parent: str, table) -> None:
        name = _table_name(table)
        if not name:
            return
        if not getattr(table, "db", None) and not getattr(table, "catalog", None) and table.name in cte_names:
            dep_id = f"cte:{table.name}"
            graph.add_node(dep_id, table.name, "cte")
        else:
            normalized = _normalize_relation(name)
            label = relation_labels.get(normalized)
            if label is None and "." in normalized:
                label = relation_labels.get(".".join(normalized.split(".")[-2:]))
            if label is None:
                label = relation_labels.get(normalized.split(".")[-1])
            label = label or display_name_for_placeholder(name)
            dep_id = f"table:{name}"
            graph.add_node(dep_id, label, "table")
        graph.add_edge(parent, dep_id)

    # CTE definitions are separate query scopes. We intentionally keep nested subquery
    # tables as dependencies of the containing CTE because they are still upstream inputs.
    for name, cte in ctes.items():
        cte_id = f"cte:{name}"
        graph.add_node(cte_id, name, "cte")
        for table in cte.this.find_all(exp.Table):
            add_dependency(cte_id, table)

    # Remove the WITH clause before scanning the top-level query so tables inside CTE
    # definitions do not become direct dependencies of the output node.
    top = expression.copy()
    if "with_" in top.args:
        top.set("with_", None)
    for table in top.find_all(exp.Table):
        add_dependency(root_name, table)

    return graph


def parse_file(
    path: Path,
    *,
    dialect: str,
    relation_labels: dict[str, str] | None = None,
    root_name: str | None = None,
) -> Graph:
    return parse_sql_graph(
        path.read_text(),
        dialect=dialect,
        root_name=root_name or path.stem,
        relation_labels=relation_labels,
    )
