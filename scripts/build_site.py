"""Write the GitHub Pages workspace from the committed examples."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qlineage.dbt import DbtManifest, LineageSelector  # noqa: E402
from qlineage.parser import parse_sql_graph  # noqa: E402
from qlineage.ui.html import render_html  # noqa: E402

MANIFEST = ROOT / "examples" / "dbt" / "target" / "manifest.json"
QUERY = ROOT / "examples" / "sql" / "customer_revenue.sql"


def _links(current: str) -> list[dict]:
    pages = (("index.html", "Models"), ("query.html", "SQL"))
    return [{"href": href, "label": label, "current": href == current} for href, label in pages]


def build_site(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    manifest = DbtManifest.load(MANIFEST)
    match = manifest.find_model("fct_customer_revenue")
    if match is None:
        raise SystemExit("examples/dbt has no fct_customer_revenue model")
    unique_id, _node = match
    graph = manifest.neighborhood(unique_id, LineageSelector.around("fct_customer_revenue"))
    (out / "index.html").write_text(
        render_html(
            graph,
            static=True,
            dialect="snowflake",
            root_name=manifest.display_name(unique_id),
            mode="neighborhood",
            models=manifest.embedded_models(graph, "snowflake"),
            links=_links("index.html"),
        )
    )

    sql = QUERY.read_text()
    query_graph = parse_sql_graph(sql, dialect="snowflake", root_name=QUERY.stem)
    (out / "query.html").write_text(
        render_html(
            query_graph,
            sql,
            static=True,
            dialect="snowflake",
            root_name=QUERY.stem,
            links=_links("query.html"),
        )
    )


def main() -> None:
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site"
    build_site(destination)
    print(f"qlineage: wrote {destination}")


if __name__ == "__main__":
    main()
