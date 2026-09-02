from __future__ import annotations

from pathlib import Path

from .jinja import display_name_for_placeholder, replace_dbt_refs
from .models import Column, Graph


class ParseError(RuntimeError):
    pass


def _sqlglot():
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError as exc:  # pragma: no cover
        raise ParseError(
            "sqlglot is required. Install qlineage-cli normally or run `pip install sqlglot`."
        ) from exc
    return sqlglot, exp


def _table_name(table) -> str:
    parts = [
        getattr(table, "catalog", None),
        getattr(table, "db", None),
        getattr(table, "name", None),
    ]
    return ".".join(str(part) for part in parts if part)


def _normalize_relation(name: str) -> str:
    return name.replace('"', "").lower()


def _expr_sql(expression, dialect: str) -> str:
    try:
        return expression.sql(dialect=dialect, pretty=True).strip()
    except Exception:  # pragma: no cover - sqlglot generation is best effort
        return ""


def _infer_type(expression, exp) -> str:
    node = expression
    if isinstance(node, exp.Alias):
        node = node.this
    if isinstance(node, exp.Cast):
        try:
            return node.to.sql().upper()
        except Exception:  # pragma: no cover
            return "UNKNOWN"
    if isinstance(node, (exp.Sum, exp.Avg)):
        return "DECIMAL"
    if isinstance(node, exp.Count):
        return "BIGINT"
    if isinstance(node, exp.Boolean):
        return "BOOLEAN"
    if isinstance(node, exp.Literal):
        return "TEXT" if node.is_string else "NUMBER"
    return "UNKNOWN"


def _select_of(expression, exp):
    if isinstance(expression, exp.Select):
        return expression
    return expression.find(exp.Select)


def _projection_columns(expression, exp) -> tuple[Column, ...]:
    select = _select_of(expression, exp)
    if select is None:
        return ()
    columns: list[Column] = []
    for projection in select.expressions:
        if isinstance(projection, exp.Star):
            columns.append(Column("*"))
            continue
        name = projection.alias_or_name or projection.sql()
        columns.append(Column(name, _infer_type(projection, exp)))
    return tuple(columns)


def _joins_of(select, exp) -> list:
    if select is None:
        return []
    return list(select.args.get("joins") or [])


def _join_key_names(select, exp) -> list[tuple[str | None, str]]:
    """Return (qualifier, column) pairs used to join this scope."""
    pairs: list[tuple[str | None, str]] = []
    for join in _joins_of(select, exp):
        for using in join.args.get("using") or []:
            pairs.append((None, using.name))
        condition = join.args.get("on")
        if condition is not None:
            for equality in condition.find_all(exp.EQ):
                for side in (equality.this, equality.expression):
                    if isinstance(side, exp.Column):
                        pairs.append((side.table or None, side.name))
    return pairs


def _statement_target(expression, exp) -> str | None:
    """Name of the relation a CREATE/INSERT statement writes to, if any."""
    if not isinstance(expression, (exp.Create, exp.Insert)):
        return None
    target = expression.this
    if isinstance(target, exp.Schema):
        target = target.this
    return _table_name(target) if isinstance(target, exp.Table) else None


def parse_sql_graph(
    sql: str,
    *,
    dialect: str,
    root_name: str | None = None,
    relation_labels: dict[str, str] | None = None,
) -> Graph:
    sqlglot, exp = _sqlglot()
    relation_labels = relation_labels or {}
    prepared = replace_dbt_refs(sql)

    try:
        expression = sqlglot.parse_one(prepared, read=dialect)
    except Exception as exc:  # sqlglot exposes multiple parse error classes
        raise ParseError(str(exc)) from exc

    # Without a file or model to name it after, describe the output from the SQL itself.
    root_name = root_name or _statement_target(expression, exp) or "final output"

    graph = Graph(root=root_name)
    ctes = {cte.alias_or_name: cte for cte in expression.ctes}
    cte_names = set(ctes)

    # The outer query without its WITH clause; CTE bodies are separate scopes.
    top = expression.copy()
    if "with_" in top.args:
        top.set("with_", None)

    join_keys: dict[str, list[str]] = {}
    table_columns: dict[str, list[str]] = {}

    def dep_id_for(table) -> str:
        name = _table_name(table)
        is_unqualified = not getattr(table, "db", None) and not getattr(table, "catalog", None)
        if is_unqualified and table.name in cte_names:
            return f"cte:{table.name}"
        return f"table:{name}"

    def register_table(table) -> str | None:
        name = _table_name(table)
        if not name:
            return None
        dep_id = dep_id_for(table)
        if dep_id.startswith("cte:"):
            graph.add_node(dep_id, table.name, "cte")
            return dep_id
        normalized = _normalize_relation(name)
        label = relation_labels.get(normalized)
        if label is None and "." in normalized:
            label = relation_labels.get(".".join(normalized.split(".")[-2:]))
        if label is None:
            label = relation_labels.get(normalized.split(".")[-1])
        label = label or display_name_for_placeholder(name)
        graph.add_node(dep_id, label, "table")
        return dep_id

    def walk_scope(parent_id: str, scope) -> None:
        select = _select_of(scope, exp)
        tables = list(scope.find_all(exp.Table))
        alias_map: dict[str, str] = {}
        dep_ids: list[str] = []
        for table in tables:
            dep_id = register_table(table)
            if dep_id is None:
                continue
            dep_ids.append(dep_id)
            for key in {table.alias, table.name, _table_name(table)}:
                if key:
                    alias_map[key] = dep_id

        unique_deps = list(dict.fromkeys(dep_ids))
        only_dep = unique_deps[0] if len(unique_deps) == 1 else None

        used: dict[str, list[str]] = {dep: [] for dep in unique_deps}

        def note(dep_id: str | None, column_name: str) -> None:
            if not dep_id or dep_id not in used:
                return
            if column_name not in used[dep_id]:
                used[dep_id].append(column_name)

        for column in scope.find_all(exp.Column):
            qualifier = column.table
            dep = alias_map.get(qualifier) if qualifier else only_dep
            note(dep, column.name)

        for qualifier, column_name in _join_key_names(select, exp):
            qualified = alias_map.get(qualifier) if qualifier else None
            targets = [qualified] if qualified else unique_deps
            for dep in targets:
                note(dep, column_name)
                keys = join_keys.setdefault(dep, [])
                if column_name not in keys:
                    keys.append(column_name)

        for dep in unique_deps:
            graph.add_edge(parent_id, dep, tuple(used.get(dep, ())))
            if dep.startswith("table:"):
                known = table_columns.setdefault(dep, [])
                for column_name in used.get(dep, ()):
                    if column_name not in known and column_name != "*":
                        known.append(column_name)

    graph.add_node(root_name, root_name, "query")
    graph.update_node(
        root_name,
        sql=_expr_sql(top, dialect),
        columns=_projection_columns(top, exp),
        join_count=len(_joins_of(_select_of(top, exp), exp)),
    )

    for name, cte in ctes.items():
        cte_id = f"cte:{name}"
        graph.add_node(cte_id, name, "cte")
        graph.update_node(
            cte_id,
            sql=f"{name} as (\n{_expr_sql(cte.this, dialect)}\n)",
            columns=_projection_columns(cte.this, exp),
            join_count=len(_joins_of(_select_of(cte.this, exp), exp)),
        )

    for name, cte in ctes.items():
        walk_scope(f"cte:{name}", cte.this)
    walk_scope(root_name, top)

    for dep_id, names in table_columns.items():
        graph.update_node(dep_id, columns=tuple(Column(name) for name in names))
    for node_id, keys in join_keys.items():
        graph.update_node(node_id, join_keys=tuple(keys))

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
