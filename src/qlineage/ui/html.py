from __future__ import annotations

import json
from pathlib import Path

from ..columns import ColumnNode
from ..models import Graph

BOOTSTRAP_PLACEHOLDER = "__QLINEAGE_BOOTSTRAP__"
TEMPLATE_PATH = Path(__file__).with_name("workspace.html")


def _load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


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
    payload = {
        "sql": sql or "",
        "graph": graph.to_dict() if graph else None,
        "column": column.to_dict() if column else None,
        "dialect": dialect,
        "rootName": root_name,
        "static": static,
        "mode": mode,
        "models": models or {},
        "links": links or [],
    }
    encoded = json.dumps(payload, indent=2).replace("<", "\\u003c")
    return _load_template().replace(BOOTSTRAP_PLACEHOLDER, encoded)
