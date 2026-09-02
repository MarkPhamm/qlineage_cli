from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .columns import trace_column
from .dbt import DbtManifest, ManifestError
from .parser import ParseError, parse_sql_graph
from .render import render_column_tree, render_json, render_mermaid, render_tree


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qlineage",
        description="Inspect local SQL/dbt lineage without connecting to your warehouse.",
    )
    parser.add_argument("sql_file", nargs="?", type=Path, help="SQL or dbt model file")
    parser.add_argument("--dialect", choices=["snowflake", "redshift"], default="snowflake")
    parser.add_argument("--manifest", type=Path, help="Path to dbt target/manifest.json")
    parser.add_argument("--model", help="dbt model name/unique_id; useful when no SQL file is passed")
    parser.add_argument("--format", choices=["tree", "json", "mermaid"], default="tree")
    parser.add_argument("--column", help="Trace a single output column through the SQL")
    parser.add_argument(
        "--dbt-graph",
        action="store_true",
        help="Show recursive dbt model/source dependencies instead of internal SQL/CTE lineage",
    )
    parser.add_argument("--depth", type=int, help="Maximum dbt graph depth")
    parser.add_argument(
        "--no-dbt",
        action="store_true",
        help="Do not auto-discover dbt target/manifest.json",
    )
    return parser


def _load_manifest(args, start: Path) -> DbtManifest | None:
    if args.no_dbt:
        return None
    manifest_path = args.manifest
    if manifest_path is None:
        manifest_path = DbtManifest.discover(start)
    return DbtManifest.load(manifest_path) if manifest_path else None


def _resolve_model(manifest: DbtManifest, args):
    if args.model:
        return manifest.find_model(args.model)
    if args.sql_file:
        return manifest.find_model_for_file(args.sql_file)
    return None


def _render_graph(graph, fmt: str) -> str:
    if fmt == "json":
        return render_json(graph)
    if fmt == "mermaid":
        return render_mermaid(graph)
    return render_tree(graph)


def run(args: argparse.Namespace) -> int:
    if not args.sql_file and not args.model:
        raise ParseError("Provide a SQL file or --model MODEL_NAME.")

    start = args.sql_file or Path.cwd()
    manifest = _load_manifest(args, start)
    model = _resolve_model(manifest, args) if manifest else None

    if args.dbt_graph:
        if not manifest:
            raise ManifestError("--dbt-graph requires a dbt manifest.json.")
        if not model:
            raise ManifestError("Could not match the requested model in manifest.json.")
        unique_id, _node = model
        print(_render_graph(manifest.dependency_graph(unique_id, args.depth), args.format))
        return 0

    sql: str
    root_name: str
    relation_labels: dict[str, str] = {}

    if model and manifest:
        unique_id, node = model
        root_name = str(node.get("name") or (args.sql_file.stem if args.sql_file else unique_id))
        sql = manifest.compiled_sql(unique_id, node) or (args.sql_file.read_text() if args.sql_file else "")
        relation_labels = manifest.relation_map()
    elif args.sql_file:
        if not args.sql_file.exists():
            raise ParseError(f"File not found: {args.sql_file}")
        root_name = args.sql_file.stem
        sql = args.sql_file.read_text()
    else:
        raise ManifestError("Could not resolve --model in manifest.json.")

    if not sql.strip():
        raise ParseError("No SQL was available to analyze. Run `dbt compile` or pass a SQL file.")

    if args.column:
        print(render_column_tree(trace_column(sql, args.column, dialect=args.dialect)))
        return 0

    graph = parse_sql_graph(
        sql,
        dialect=args.dialect,
        root_name=root_name,
        relation_labels=relation_labels,
    )
    print(_render_graph(graph, args.format))
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raise SystemExit(run(args))
    except (ParseError, ManifestError, OSError) as exc:
        print(f"qlineage: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
