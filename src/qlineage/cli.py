from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .columns import ColumnNode, trace_column
from .dbt import DbtManifest, LineageSelector, ManifestError, parse_selector
from .models import Graph
from .parser import ParseError, parse_sql_graph
from .render import (
    render_column_tree,
    render_html,
    render_json,
    render_markdown,
    render_mermaid,
    render_tree,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qlineage",
        description="QLineage CLI - inspect SQL/dbt lineage locally, without a warehouse.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"qlineage {__version__}",
    )
    parser.add_argument("sql_file", nargs="?", type=Path, help="SQL or dbt model file")
    parser.add_argument("--dialect", choices=["snowflake", "redshift"], default="snowflake")
    parser.add_argument("--manifest", type=Path, help="Path to dbt target/manifest.json")
    parser.add_argument(
        "--model",
        help=(
            "dbt model name or unique id. Without a SQL file, opens that model's "
            "upstream and downstream neighborhood"
        ),
    )
    parser.add_argument(
        "--select",
        help=(
            "Lineage around one model: +model (upstream), model+ (downstream), "
            "model+N (N hops), +model+ (both). Refuses a whole-project graph"
        ),
    )
    parser.add_argument(
        "--format",
        choices=["tree", "json", "mermaid", "html"],
        default="html",
        help=(
            "html opens in a browser; mermaid writes a markdown file; "
            "tree/json print to the terminal"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write the rendered lineage to this file instead of stdout",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Write a standalone HTML snapshot to stdout instead of opening a browser",
    )
    parser.add_argument("--port", type=int, default=8765, help="Port for the local workspace")
    parser.add_argument("--column", help="Trace a single output column through the SQL")
    parser.add_argument(
        "--dbt-graph",
        action="store_true",
        help="Show upstream dbt dependencies instead of the neighborhood or CTE graph",
    )
    parser.add_argument(
        "--depth",
        type=int,
        help="Maximum hops for --dbt-graph and --select",
    )
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


def _render_graph(graph, fmt: str, *, sql: str = "", dialect: str = "snowflake") -> str:
    if fmt == "json":
        return render_json(graph)
    if fmt == "mermaid":
        return render_mermaid(graph)
    if fmt == "html":
        return render_html(graph, sql, static=True, dialect=dialect)
    return render_tree(graph)


def _write_output(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n")
    print(f"qlineage: wrote {path}", file=sys.stderr)


def _emit(args: argparse.Namespace, text: str) -> int:
    if args.output:
        _write_output(args.output, text)
    else:
        print(text)
    return 0


def _present(
    args: argparse.Namespace,
    graph: Graph,
    *,
    sql: str = "",
    column: ColumnNode | None = None,
    root_name: str = "query",
    manifest: DbtManifest | None = None,
    mode: str = "sql",
) -> int:
    if args.format == "mermaid":
        # Piping stays raw mermaid; an interactive run gets a markdown file it can commit.
        if not args.output and not sys.stdout.isatty():
            print(render_mermaid(graph))
            return 0
        path = args.output or Path(f"{root_name}.lineage.md")
        if path.suffix.lower() in {".md", ".markdown"}:
            source = str(args.sql_file) if args.sql_file else None
            _write_output(path, render_markdown(graph, title=root_name, source=source))
        else:
            _write_output(path, render_mermaid(graph))
        return 0

    if args.format != "html":
        return _emit(args, _render_graph(graph, args.format, sql=sql, dialect=args.dialect))

    if args.output or args.no_open or not sys.stdout.isatty():
        return _emit(
            args,
            render_html(
                graph,
                sql,
                column=column,
                static=True,
                dialect=args.dialect,
                root_name=root_name,
                mode=mode,
            ),
        )

    from .ui.server import serve

    serve(
        port=args.port,
        dialect=args.dialect,
        open_browser=True,
        sql=sql,
        graph=graph,
        column=column,
        root_name=root_name,
        relation_labels=manifest.relation_map() if manifest else None,
        manifest=manifest,
        mode=mode,
    )
    return 0


def build_ui_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qlineage ui",
        description="Open the QLineage CLI workspace in a browser.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"qlineage {__version__}",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dialect", choices=["snowflake", "redshift"], default="snowflake")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open a browser window",
    )
    return parser


def run_ui(argv: list[str]) -> int:
    args = build_ui_parser().parse_args(argv)
    from .ui.server import serve

    serve(port=args.port, dialect=args.dialect, open_browser=not args.no_open)
    return 0


def _selector_for(args: argparse.Namespace) -> LineageSelector | None:
    if args.select:
        return parse_selector(args.select)
    # A model with no SQL file opens both directions. --dbt-graph stays upstream-only.
    if args.model and not args.sql_file and not args.dbt_graph:
        return LineageSelector.around(args.model)
    return None


def _require_model(manifest: DbtManifest, *names: str) -> tuple[str, dict]:
    found: list[str] = []
    for name in names:
        if not name:
            continue
        match = manifest.find_model(name)
        if match is None:
            raise ManifestError(f"Could not match {name} in manifest.json.")
        found.append(match[0])
    if len(set(found)) != 1:
        raise ManifestError("--model and --select name different models.")
    unique_id = found[0]
    return unique_id, manifest.nodes[unique_id]


def run(args: argparse.Namespace) -> int:
    if not args.sql_file and not args.model and not args.select:
        raise ParseError("Provide a SQL file or --model MODEL_NAME.")

    start = args.sql_file or Path.cwd()
    manifest = _load_manifest(args, start)
    selector = _selector_for(args)
    if selector is not None:
        if not manifest:
            raise ManifestError("A lineage selector requires a dbt manifest.json.")
        unique_id, _node = _require_model(manifest, args.model, selector.name)
        graph = manifest.neighborhood(unique_id, selector.capped(args.depth))
        return _present(
            args,
            graph,
            root_name=manifest.display_name(unique_id),
            manifest=manifest,
            mode="neighborhood",
        )

    model = _resolve_model(manifest, args) if manifest else None

    if args.dbt_graph:
        if not manifest:
            raise ManifestError("--dbt-graph requires a dbt manifest.json.")
        if not model:
            raise ManifestError("Could not match the requested model in manifest.json.")
        unique_id, _node = model
        graph = manifest.dependency_graph(unique_id, args.depth)
        return _present(
            args,
            graph,
            root_name=manifest.display_name(unique_id),
            manifest=manifest,
            mode="neighborhood",
        )

    sql: str
    root_name: str
    relation_labels: dict[str, str] = {}

    if model and manifest:
        unique_id, node = model
        root_name = str(node.get("name") or (args.sql_file.stem if args.sql_file else unique_id))
        compiled = manifest.compiled_sql(unique_id, node)
        file_sql = args.sql_file.read_text() if args.sql_file else ""
        sql = compiled or file_sql
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

    column = trace_column(sql, args.column, dialect=args.dialect) if args.column else None
    if args.column and args.format != "html":
        return _emit(args, render_column_tree(column))

    graph = parse_sql_graph(
        sql,
        dialect=args.dialect,
        root_name=root_name,
        relation_labels=relation_labels,
    )
    return _present(
        args,
        graph,
        sql=sql,
        column=column,
        root_name=root_name,
        manifest=manifest,
    )


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        if argv and argv[0] == "ui":
            raise SystemExit(run_ui(argv[1:]))
        parser = build_parser()
        args = parser.parse_args(argv)
        raise SystemExit(run(args))
    except (ParseError, ManifestError, OSError) as exc:
        print(f"qlineage: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
