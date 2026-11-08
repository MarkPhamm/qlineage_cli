import json
from pathlib import Path

import pytest

from qlineage import __version__
from qlineage.cli import build_parser, main, run


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"qlineage {__version__}"


def _manifest(tmp_path: Path) -> Path:
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
                        "depends_on": {"nodes": ["model.demo.stg_orders"]},
                    },
                    "model.demo.stg_orders": {
                        "resource_type": "model",
                        "name": "stg_orders",
                        "depends_on": {"nodes": ["source.demo.raw.orders"]},
                    },
                    "model.demo.fct_revenue": {
                        "resource_type": "model",
                        "name": "fct_revenue",
                        "depends_on": {"nodes": ["model.demo.fct_orders"]},
                    },
                    "model.demo.fct_daily": {
                        "resource_type": "model",
                        "name": "fct_daily",
                        "depends_on": {"nodes": ["model.demo.fct_revenue"]},
                    },
                },
                "sources": {
                    "source.demo.raw.orders": {
                        "resource_type": "source",
                        "source_name": "raw",
                        "name": "orders",
                        "depends_on": {"nodes": []},
                    }
                },
            }
        )
    )
    return path


def test_model_without_a_file_opens_the_neighborhood(tmp_path, capsys):
    path = _manifest(tmp_path)
    args = build_parser().parse_args(
        ["--model", "fct_orders", "--manifest", str(path), "--format", "json", "--no-open"]
    )
    assert run(args) == 0
    ids = {node["id"] for node in json.loads(capsys.readouterr().out)["nodes"]}
    assert "model.demo.fct_revenue" in ids
    assert "source.demo.raw.orders" in ids
    assert "model.demo.fct_daily" in ids


def test_dbt_graph_stays_upstream(tmp_path, capsys):
    path = _manifest(tmp_path)
    args = build_parser().parse_args(
        [
            "--model",
            "fct_orders",
            "--dbt-graph",
            "--manifest",
            str(path),
            "--format",
            "json",
            "--no-open",
        ]
    )
    assert run(args) == 0
    ids = {node["id"] for node in json.loads(capsys.readouterr().out)["nodes"]}
    assert "model.demo.stg_orders" in ids
    assert "model.demo.fct_revenue" not in ids


def test_select_limits_downstream_to_one_hop(tmp_path, capsys):
    path = _manifest(tmp_path)
    args = build_parser().parse_args(
        [
            "--select",
            "fct_orders+1",
            "--manifest",
            str(path),
            "--format",
            "json",
            "--no-open",
        ]
    )
    assert run(args) == 0
    ids = {node["id"] for node in json.loads(capsys.readouterr().out)["nodes"]}
    assert ids == {"model.demo.fct_orders", "model.demo.fct_revenue"}


def test_depth_caps_the_neighborhood(tmp_path, capsys):
    path = _manifest(tmp_path)
    args = build_parser().parse_args(
        [
            "--model",
            "fct_orders",
            "--depth",
            "1",
            "--manifest",
            str(path),
            "--format",
            "json",
            "--no-open",
        ]
    )
    assert run(args) == 0
    ids = {node["id"] for node in json.loads(capsys.readouterr().out)["nodes"]}
    assert ids == {
        "model.demo.fct_orders",
        "model.demo.stg_orders",
        "model.demo.fct_revenue",
    }


def test_neighborhood_page_is_marked_for_drilldown(tmp_path, capsys):
    path = _manifest(tmp_path)
    args = build_parser().parse_args(
        ["--model", "fct_orders", "--manifest", str(path), "--no-open"]
    )
    assert run(args) == 0
    assert '"mode": "neighborhood"' in capsys.readouterr().out


def test_model_and_select_must_agree(tmp_path, capsys):
    path = _manifest(tmp_path)
    with pytest.raises(SystemExit) as exit_info:
        main(
            [
                "--model",
                "fct_orders",
                "--select",
                "+stg_orders",
                "--manifest",
                str(path),
                "--format",
                "json",
            ]
        )
    assert exit_info.value.code == 2
    assert "different models" in capsys.readouterr().err


def test_selector_refuses_the_whole_project(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--select", "*", "--format", "json"])
    assert exit_info.value.code == 2
    assert "whole project" in capsys.readouterr().err


def test_missing_model_does_not_draw_every_node(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--no-dbt"])
    assert exit_info.value.code == 2
    assert "SQL file or --model" in capsys.readouterr().err


def test_ui_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["ui", "--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"qlineage {__version__}"
