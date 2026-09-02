import json
from pathlib import Path

from qlineage.dbt import DbtManifest


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


def test_relation_mapping(tmp_path):
    manifest = _manifest(tmp_path)
    mapping = manifest.relation_map()
    assert mapping["analytics.staging.stg_orders"] == "ref:stg_orders"
    assert mapping["raw.shop.orders"] == "source:raw.orders"
