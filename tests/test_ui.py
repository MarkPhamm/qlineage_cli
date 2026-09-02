from pathlib import Path

from qlineage.cli import build_parser, run
from qlineage.columns import ColumnNode
from qlineage.parser import parse_sql_graph
from qlineage.ui.html import render_html
from qlineage.ui.server import analyze_column, analyze_lineage

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


def test_column_node_to_dict():
    tree = ColumnNode("revenue", [ColumnNode("amount")])
    assert tree.to_dict() == {
        "name": "revenue",
        "children": [{"name": "amount", "children": []}],
    }
