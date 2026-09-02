from __future__ import annotations

import re

_REF_RE = re.compile(r"\{\{\s*ref\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}")
_SOURCE_RE = re.compile(
    r"\{\{\s*source\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}"
)
_CONFIG_RE = re.compile(r"\{\{\s*config\([^}]*\)\s*\}\}", re.DOTALL)


def replace_dbt_refs(sql: str) -> str:
    """Replace common dbt ref/source calls with parser-friendly identifiers.

    This is a fallback for raw model SQL when no compiled SQL is available.
    Complex Jinja is intentionally not evaluated.
    """
    sql = _CONFIG_RE.sub("", sql)
    sql = _REF_RE.sub(lambda m: f"__dbt_ref__.{m.group(1)}", sql)
    sql = _SOURCE_RE.sub(lambda m: f"__dbt_source__.{m.group(1)}__{m.group(2)}", sql)
    return sql


def display_name_for_placeholder(name: str) -> str:
    if name.startswith("__dbt_ref__."):
        return f"ref:{name.split('.', 1)[1]}"
    if name.startswith("__dbt_source__."):
        value = name.split(".", 1)[1]
        source, _, table = value.partition("__")
        return f"source:{source}.{table}"
    return name
