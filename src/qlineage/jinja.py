from __future__ import annotations

import re

_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)
_STATEMENT_RE = re.compile(r"\{%-?\s*(.*?)\s*-?%\}", re.DOTALL)
_EXPRESSION_RE = re.compile(r"\{\{-?\s*(.*?)\s*-?\}\}", re.DOTALL)

_SET_RE = re.compile(r"^set\s+(\w+)\s*=\s*(.+)$", re.DOTALL)
_CALL_RE = re.compile(r"^(?:[\w.]+\.)*(\w+)\s*\((.*)\)$", re.DOTALL)
_STRING_RE = re.compile(r"['\"]([^'\"]*)['\"]")
_COUNT_ARG_RE = re.compile(r"^(?:n\s*=\s*)?(\d+)$")

_REF_PREFIX = "__dbt_ref__."
_SOURCE_PREFIX = "__dbt_source__."
_THIS = "__dbt_this__"
_UNRESOLVED = "__dbt_jinja__"

# Jinja standing where SQL expects an expression, a column, or a relation has to
# leave an identifier behind. Everywhere else it is usually a macro emitting a
# whole clause, and dropping it keeps the rest of the statement parseable.
_EXPRESSION_BEFORE_RE = re.compile(
    r"(?:[,(+\-*/%=<>]|\|\||\b(?:select|distinct|where|and|or|not|on|using|case|when|then"
    r"|else|by|from|join|as|in|over|partition)\b)\s*$",
    re.IGNORECASE,
)
_EXPRESSION_AFTER_RE = re.compile(r"^\s*(?:,|\|\||as\b)", re.IGNORECASE)


def _string_args(args: str) -> list[str]:
    return _STRING_RE.findall(args)


def _column_args(args: str, variables: dict[str, list[str]]) -> list[str]:
    """Columns passed to a macro, either inline or through a `{% set %}` list."""
    literals = _string_args(args)
    if literals:
        return literals
    return list(variables.get(args.strip(), ()))


def _expand_call(name: str, args: str, variables: dict[str, list[str]]) -> str | None:
    """Expansion for the macros worth emulating, or None when unknown."""
    if name == "config":
        return ""
    if name == "ref":
        names = _string_args(args)
        return f"{_REF_PREFIX}{names[-1]}" if names else None
    if name == "source":
        names = _string_args(args)
        return f"{_SOURCE_PREFIX}{names[0]}__{names[1]}" if len(names) >= 2 else None
    if name == "group_by":
        match = _COUNT_ARG_RE.match(args.strip())
        if match is None:
            return None
        count = int(match.group(1))
        return "group by " + ", ".join(str(i) for i in range(1, count + 1))
    if name == "star":
        return "*"
    if name in {"generate_surrogate_key", "surrogate_key"}:
        columns = _column_args(args, variables)
        if not columns:
            return None
        return f"md5(concat_ws('-', {', '.join(columns)}))"
    return None


def _expand_expression(body: str, variables: dict[str, list[str]]) -> str | None:
    if body == "this":
        return _THIS
    match = _CALL_RE.match(body)
    if match is None:
        return None
    return _expand_call(match.group(1).lower(), match.group(2), variables)


def _collect_statements(sql: str) -> tuple[str, dict[str, list[str]]]:
    """Drop `{% ... %}` tags, remembering the lists assigned by `{% set %}`."""
    variables: dict[str, list[str]] = {}

    def record(match: re.Match[str]) -> str:
        assignment = _SET_RE.match(match.group(1))
        if assignment is not None:
            values = _string_args(assignment.group(2))
            if values:
                variables[assignment.group(1)] = values
        return ""

    return _STATEMENT_RE.sub(record, sql), variables


def _fallback(before: str, after: str) -> str:
    if _EXPRESSION_BEFORE_RE.search(before.rstrip("\n\r\t ")) or _EXPRESSION_AFTER_RE.match(after):
        return _UNRESOLVED
    return ""


def replace_dbt_refs(sql: str) -> str:
    """Rewrite dbt Jinja into parser-friendly SQL.

    This is a fallback for raw model SQL when no compiled SQL is available, so
    macros are approximated rather than executed: `ref`/`source` become
    placeholder relations, a few common `dbt_utils` macros are emulated to keep
    their column references visible, and anything left over is replaced by a
    placeholder identifier or dropped depending on where it sits in the SQL.
    """
    sql = _COMMENT_RE.sub("", sql)
    sql, variables = _collect_statements(sql)

    chunks: list[str] = []
    position = 0
    for match in _EXPRESSION_RE.finditer(sql):
        chunks.append(sql[position : match.start()])
        replacement = _expand_expression(match.group(1).strip(), variables)
        if replacement is None:
            replacement = _fallback("".join(chunks), sql[match.end() :])
        chunks.append(replacement)
        position = match.end()
    chunks.append(sql[position:])
    return "".join(chunks)


def display_name_for_placeholder(name: str) -> str:
    if name.startswith(_REF_PREFIX):
        return f"ref:{name.split('.', 1)[1]}"
    if name.startswith(_SOURCE_PREFIX):
        value = name.split(".", 1)[1]
        source, _, table = value.partition("__")
        return f"source:{source}.{table}"
    if name == _THIS:
        return "this"
    if name == _UNRESOLVED:
        return "unresolved jinja"
    return name
