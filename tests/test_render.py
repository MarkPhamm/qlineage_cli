from qlineage.models import Graph
from qlineage.render import render_html, render_mermaid, render_tree


def test_tree_and_mermaid():
    graph = Graph(root="orders")
    graph.add_node("orders", "fct_orders", "query")
    graph.add_node("cte:a", "a", "cte")
    graph.add_node("table:raw.orders", "raw.orders", "table")
    graph.add_edge("orders", "cte:a")
    graph.add_edge("cte:a", "table:raw.orders")

    tree = render_tree(graph)
    assert "fct_orders" in tree
    assert "raw.orders" in tree
    assert "flowchart TD" in render_mermaid(graph)
    html = render_html(graph, "select 1", static=True)
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "fct_orders" in html
