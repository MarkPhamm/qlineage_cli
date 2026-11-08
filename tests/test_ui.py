import json
import sys
import threading
from pathlib import Path
from urllib.request import Request, urlopen

from qlineage.cli import build_parser, run
from qlineage.columns import ColumnNode
from qlineage.dbt import DbtManifest
from qlineage.parser import parse_sql_graph
from qlineage.ui.html import render_html
from qlineage.ui.server import analyze_column, analyze_lineage, build_server

EXAMPLE_SQL = Path("examples/sql/customer_revenue.sql").read_text()


def test_html_export_contains_nodes_and_doctype():
    graph = parse_sql_graph(EXAMPLE_SQL, dialect="snowflake", root_name="customer_revenue")
    html = render_html(graph, EXAMPLE_SQL, static=True)
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "customer_revenue" in html
    assert "raw.shop.orders" in html
    assert "raw.stripe.payments" in html


def test_analyze_lineage_customer_revenue():
    data = analyze_lineage(EXAMPLE_SQL, "snowflake", root_name="customer_revenue")
    labels = {node["label"] for node in data["nodes"]}
    assert data["root"] == "customer_revenue"
    assert "customer_revenue" in labels
    assert "orders" in labels
    assert "raw.shop.orders" in labels
    assert "raw.stripe.payments" in labels


def test_output_node_is_named_from_sql_when_no_file_is_given():
    # The workspace sends no root_name once the query differs from the loaded file.
    assert analyze_lineage("select * from review", "snowflake")["root"] == "final output"
    named = analyze_lineage("select * from review", "snowflake", root_name="customer_revenue")
    assert named["root"] == "customer_revenue"


def test_output_node_uses_ctas_target():
    data = analyze_lineage("create table mart.review_summary as select id from review", "snowflake")
    assert data["root"] == "mart.review_summary"


def test_analyze_column_revenue():
    data = analyze_column(EXAMPLE_SQL, "revenue", "snowflake")
    assert data["name"] == "revenue"
    assert data["children"]


def test_cli_defaults_to_html_stdout_with_no_open(capsys):
    args = build_parser().parse_args(
        ["examples/sql/customer_revenue.sql", "--no-open", "--no-dbt"]
    )
    assert args.format == "html"
    assert run(args) == 0
    html = capsys.readouterr().out
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "customer_revenue" in html
    assert "raw.shop.orders" in html


def test_cli_tree_still_prints_to_terminal(capsys):
    args = build_parser().parse_args(
        ["examples/sql/customer_revenue.sql", "--format", "tree", "--no-dbt"]
    )
    assert run(args) == 0
    tree = capsys.readouterr().out
    assert "customer_revenue" in tree
    assert "raw.shop.orders" in tree


def test_cli_mermaid_writes_a_markdown_file(tmp_path, capsys):
    target = tmp_path / "docs" / "lineage.md"
    args = build_parser().parse_args(
        [
            "examples/sql/customer_revenue.sql",
            "--format",
            "mermaid",
            "--output",
            str(target),
            "--no-dbt",
        ]
    )
    assert run(args) == 0
    markdown = target.read_text()
    assert markdown.startswith("# Lineage: customer_revenue")
    assert "```mermaid\nflowchart TD" in markdown
    assert "raw.shop.orders" in markdown
    assert f"wrote {target}" in capsys.readouterr().err


def test_cli_mermaid_defaults_to_model_named_markdown_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.chdir(tmp_path)
    sql_file = tmp_path / "dim_customers.sql"
    sql_file.write_text("select id from raw.customers")

    args = build_parser().parse_args([str(sql_file), "--format", "mermaid", "--no-dbt"])
    assert run(args) == 0
    capsys.readouterr()
    markdown = (tmp_path / "dim_customers.lineage.md").read_text()
    assert f"Source: `{sql_file}`" in markdown
    assert "raw.customers" in markdown


def test_cli_mermaid_stays_raw_when_piped(capsys):
    args = build_parser().parse_args(
        ["examples/sql/customer_revenue.sql", "--format", "mermaid", "--no-dbt"]
    )
    assert run(args) == 0
    assert capsys.readouterr().out.startswith("flowchart TD")


def test_cli_mermaid_output_without_markdown_suffix_stays_raw(tmp_path):
    target = tmp_path / "lineage.mmd"
    args = build_parser().parse_args(
        ["examples/sql/customer_revenue.sql", "--format", "mermaid", "-o", str(target), "--no-dbt"]
    )
    assert run(args) == 0
    assert target.read_text().startswith("flowchart TD")


def _post(server, path: str, payload: dict) -> dict:
    port = server.server_address[1]
    body = json.dumps(payload).encode()
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request) as response:
        return json.load(response)


def test_lineage_api_keeps_relation_labels_on_reparse(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    manifest_path = target / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "nodes": {
                    "model.demo.stg_orders": {
                        "resource_type": "model",
                        "name": "stg_orders",
                        "database": "analytics",
                        "schema": "staging",
                        "alias": "stg_orders",
                        "compiled_code": "select id from analytics.staging.orders",
                        "depends_on": {"nodes": []},
                    }
                },
                "sources": {
                    "source.demo.raw.orders": {
                        "resource_type": "source",
                        "source_name": "raw",
                        "name": "orders",
                        "database": "analytics",
                        "schema": "staging",
                        "alias": "orders",
                    }
                },
            }
        )
    )
    manifest = DbtManifest.load(manifest_path)
    server = build_server(
        0,
        "snowflake",
        relation_labels=manifest.relation_map(),
        manifest=manifest,
        mode="neighborhood",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = _post(
            server,
            "/api/lineage",
            {"sql": "select id from analytics.staging.orders", "dialect": "snowflake"},
        )
        labels = {node["label"] for node in payload["graph"]["nodes"]}
        assert "source:raw.orders" in labels

        opened = _post(server, "/api/model", {"id": "model.demo.stg_orders"})
        opened_labels = {node["label"] for node in opened["graph"]["nodes"]}
        assert opened["rootName"] == "stg_orders"
        assert "source:raw.orders" in opened_labels
        assert "select id from analytics.staging.orders" in opened["sql"]
    finally:
        server.shutdown()
        server.server_close()


def test_column_node_to_dict():
    tree = ColumnNode("revenue", [ColumnNode("amount")])
    assert tree.to_dict() == {
        "name": "revenue",
        "children": [{"name": "amount", "children": []}],
    }
