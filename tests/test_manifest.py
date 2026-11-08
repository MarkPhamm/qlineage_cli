import json
from pathlib import Path

import pytest

from qlineage.dbt import DbtManifest, LineageSelector, ManifestError, parse_selector
from qlineage.render import render_tree


def _manifest(tmp_path: Path) -> DbtManifest:
    target = tmp_path / "target"
    target.mkdir()
    path = target / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "nodes": {
                    "model.demo.fct_orders": {
                        "resource_type": "model",
                        "name": "fct_orders",
                        "original_file_path": "models/fct_orders.sql",
                        "database": "analytics",
                        "schema": "marts",
                        "alias": "fct_orders",
                        "depends_on": {"nodes": ["model.demo.stg_orders"]},
                    },
                    "model.demo.stg_orders": {
                        "resource_type": "model",
                        "name": "stg_orders",
                        "database": "analytics",
                        "schema": "staging",
                        "alias": "stg_orders",
                        "depends_on": {"nodes": ["source.demo.raw.orders"]},
                    },
                    "model.demo.fct_revenue": {
                        "resource_type": "model",
                        "name": "fct_revenue",
                        "database": "analytics",
                        "schema": "marts",
                        "alias": "fct_revenue",
                        "depends_on": {"nodes": ["model.demo.fct_orders"]},
                    },
                    "model.demo.fct_daily": {
                        "resource_type": "model",
                        "name": "fct_daily",
                        "database": "analytics",
                        "schema": "marts",
                        "alias": "fct_daily",
                        "depends_on": {"nodes": ["model.demo.fct_revenue"]},
                    },
                },
                "sources": {
                    "source.demo.raw.orders": {
                        "resource_type": "source",
                        "source_name": "raw",
                        "name": "orders",
                        "database": "raw",
                        "schema": "shop",
                        "alias": "orders",
                        "depends_on": {"nodes": []},
                    }
                },
            }
        )
    )
    return DbtManifest.load(path)


def test_dependency_graph(tmp_path):
    manifest = _manifest(tmp_path)
    graph = manifest.dependency_graph("model.demo.fct_orders")
    assert graph.root == "model.demo.fct_orders"
    assert graph.upstream("model.demo.fct_orders") == ["model.demo.stg_orders"]
    assert graph.upstream("model.demo.stg_orders") == ["source.demo.raw.orders"]
    assert "model.demo.fct_revenue" not in graph.nodes


def test_dependency_index_has_both_directions_without_child_map(tmp_path):
    manifest = _manifest(tmp_path)
    assert "child_map" not in manifest.data
    assert manifest.parents["model.demo.fct_orders"] == ("model.demo.stg_orders",)
    assert manifest.children["model.demo.fct_orders"] == ("model.demo.fct_revenue",)
    assert manifest.children["model.demo.stg_orders"] == ("model.demo.fct_orders",)


def test_neighborhood_walks_both_directions(tmp_path):
    manifest = _manifest(tmp_path)
    graph = manifest.neighborhood(
        "model.demo.fct_orders",
        LineageSelector.around("fct_orders"),
    )
    assert graph.upstream("model.demo.fct_orders") == ["model.demo.stg_orders"]
    assert graph.downstream("model.demo.fct_orders") == ["model.demo.fct_revenue"]
    assert "source.demo.raw.orders" in graph.nodes
    assert "model.demo.fct_daily" in graph.nodes
    tree = render_tree(graph)
    assert "downstream" in tree
    assert "ref:fct_revenue" in tree
    assert "ref:fct_daily" in tree


def test_selector_bounds_hops(tmp_path):
    manifest = _manifest(tmp_path)
    root = "model.demo.fct_orders"

    upstream = manifest.neighborhood(root, parse_selector("+fct_orders"))
    assert "source.demo.raw.orders" in upstream.nodes
    assert "model.demo.fct_revenue" not in upstream.nodes

    one_down = manifest.neighborhood(root, parse_selector("fct_orders+1"))
    assert set(one_down.nodes) == {root, "model.demo.fct_revenue"}

    one_up = manifest.neighborhood(root, parse_selector("1+fct_orders"))
    assert set(one_up.nodes) == {root, "model.demo.stg_orders"}

    both = manifest.neighborhood(root, parse_selector("+fct_orders+"))
    assert "source.demo.raw.orders" in both.nodes
    assert "model.demo.fct_daily" in both.nodes

    capped = manifest.neighborhood(root, LineageSelector.around("fct_orders").capped(1))
    assert set(capped.nodes) == {root, "model.demo.stg_orders", "model.demo.fct_revenue"}


def test_model_sql_falls_back_to_the_model_file(tmp_path):
    project = tmp_path / "proj"
    models = project / "models"
    models.mkdir(parents=True)
    (models / "fct_orders.sql").write_text("select 1 as id\n")
    target = project / "target"
    target.mkdir()
    path = target / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "nodes": {
                    "model.demo.fct_orders": {
                        "resource_type": "model",
                        "name": "fct_orders",
                        "original_file_path": "models/fct_orders.sql",
                        "depends_on": {"nodes": []},
                    }
                }
            }
        )
    )
    manifest = DbtManifest.load(path)
    _node, sql = manifest.model_sql("model.demo.fct_orders")
    assert sql == "select 1 as id\n"

    bare = tmp_path / "target" / "manifest.json"
    bare.parent.mkdir()
    bare.write_text(
        json.dumps(
            {
                "nodes": {
                    "model.demo.fct_orders": {
                        "resource_type": "model",
                        "name": "fct_orders",
                        "depends_on": {"nodes": []},
                    }
                }
            }
        )
    )
    with pytest.raises(ManifestError, match="dbt compile"):
        DbtManifest.load(bare).model_sql("model.demo.fct_orders")


def test_selector_refuses_an_unbounded_graph():
    for text in ("*", "tag:marts", "+model +other", "", "a b"):
        with pytest.raises(ManifestError, match="whole project"):
            parse_selector(text)


def test_relation_mapping(tmp_path):
    manifest = _manifest(tmp_path)
    mapping = manifest.relation_map()
    assert mapping["analytics.staging.stg_orders"] == "ref:stg_orders"
    assert mapping["raw.shop.orders"] == "source:raw.orders"
