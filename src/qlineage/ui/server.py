from __future__ import annotations

import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..columns import ColumnNode, trace_column
from ..dbt import DbtManifest, ManifestError
from ..models import Graph
from ..parser import ParseError, parse_sql_graph
from .html import render_html

SUPPORTED_DIALECTS = {"snowflake", "redshift"}


def analyze_lineage(
    sql: str,
    dialect: str,
    *,
    root_name: str | None = None,
    relation_labels: dict[str, str] | None = None,
) -> dict:
    if not sql.strip():
        raise ParseError("Provide SQL to analyze.")
    return parse_sql_graph(
        sql,
        dialect=dialect,
        root_name=root_name,
        relation_labels=relation_labels,
    ).to_dict()


def analyze_column(sql: str, column: str, dialect: str) -> dict:
    if not sql.strip():
        raise ParseError("Provide SQL to analyze.")
    if not column.strip():
        raise ParseError("Provide a column name.")
    return trace_column(sql, column, dialect=dialect).to_dict()


class UiServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(
        self,
        server_address,
        dialect: str,
        *,
        sql: str = "",
        graph: Graph | None = None,
        column: ColumnNode | None = None,
        root_name: str = "query",
        relation_labels: dict[str, str] | None = None,
        manifest: DbtManifest | None = None,
        mode: str = "sql",
    ):
        super().__init__(server_address, UiHandler)
        self.dialect = dialect
        self.sql = sql
        self.graph = graph
        self.column = column
        self.root_name = root_name
        self.relation_labels = relation_labels or {}
        self.manifest = manifest
        self.mode = mode


class UiHandler(BaseHTTPRequestHandler):
    server: UiServer

    def log_message(self, format: str, *args) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] not in {"/", "/index.html"}:
            self._json(404, {"error": "Not found"})
            return
        html = render_html(
            self.server.graph,
            self.server.sql,
            column=self.server.column,
            static=False,
            dialect=self.server.dialect,
            root_name=self.server.root_name,
            mode=self.server.mode,
        )
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "Invalid JSON"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"error": "Invalid JSON"})
            return

        sql = str(payload.get("sql") or "")
        dialect = str(payload.get("dialect") or self.server.dialect)
        if dialect not in SUPPORTED_DIALECTS:
            self._json(400, {"error": "Unsupported dialect."})
            return

        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/lineage":
                # An empty root_name means the SQL no longer matches the file we
                # were launched with, so the output node is named from the query.
                requested = payload.get("root_name")
                root_name = str(requested) if requested else None
                graph = analyze_lineage(
                    sql,
                    dialect,
                    root_name=root_name,
                    relation_labels=self.server.relation_labels,
                )
                self.server.sql = sql
                self._json(200, {"graph": graph})
                return
            if path == "/api/column":
                column = str(payload.get("column") or "")
                self._json(200, {"column": analyze_column(sql, column, dialect)})
                return
            if path == "/api/model":
                self._open_model(str(payload.get("id") or ""), dialect)
                return
        except ParseError as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(404, {"error": "Not found"})

    def _open_model(self, unique_id: str, dialect: str) -> None:
        manifest = self.server.manifest
        if manifest is None:
            self._json(400, {"error": "No dbt manifest is loaded."})
            return
        try:
            node, sql = manifest.model_sql(unique_id)
            root_name = str(node.get("name") or unique_id)
            graph = parse_sql_graph(
                sql,
                dialect=dialect,
                root_name=root_name,
                relation_labels=self.server.relation_labels or manifest.relation_map(),
            )
        except (ManifestError, ParseError) as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(200, {"sql": sql, "graph": graph.to_dict(), "rootName": root_name})


def build_server(port: int, dialect: str, **initial) -> UiServer:
    try:
        return UiServer(("127.0.0.1", port), dialect, **initial)
    except OSError:
        return UiServer(("127.0.0.1", 0), dialect, **initial)


def serve(
    port: int = 8765,
    dialect: str = "snowflake",
    open_browser: bool = True,
    *,
    sql: str = "",
    graph: Graph | None = None,
    column: ColumnNode | None = None,
    root_name: str = "query",
    relation_labels: dict[str, str] | None = None,
    manifest: DbtManifest | None = None,
    mode: str = "sql",
) -> None:
    server = build_server(
        port,
        dialect,
        sql=sql,
        graph=graph,
        column=column,
        root_name=root_name,
        relation_labels=relation_labels,
        manifest=manifest,
        mode=mode,
    )
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"QLineage CLI: workspace ready at {url} (Ctrl-C to stop)", file=sys.stderr)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nQLineage CLI: stopped", file=sys.stderr)
    finally:
        server.server_close()
