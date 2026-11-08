from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Graph
from .parser import ParseError, parse_sql_graph

# One model, optional hop counts. `+name` is upstream, `name+` is downstream.
_SELECTOR_RE = re.compile(
    r"^(?:(?P<up>\d*)\+)?(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)(?:\+(?P<down>\d*))?$"
)


class ManifestError(RuntimeError):
    pass


@dataclass(frozen=True)
class LineageSelector:
    """Hop limits are None when that direction is unlimited. A direction not walked stays off."""

    name: str
    upstream: int | None
    downstream: int | None
    walk_upstream: bool
    walk_downstream: bool

    @classmethod
    def around(cls, name: str) -> LineageSelector:
        return cls(name, None, None, True, True)

    def capped(self, depth: int | None) -> LineageSelector:
        if depth is None:
            return self

        def tighten(enabled: bool, limit: int | None) -> tuple[bool, int | None]:
            if not enabled:
                return False, None
            if limit is None:
                return True, depth
            return True, min(limit, depth)

        walk_up, upstream = tighten(self.walk_upstream, self.upstream)
        walk_down, downstream = tighten(self.walk_downstream, self.downstream)
        return LineageSelector(self.name, upstream, downstream, walk_up, walk_down)


def parse_selector(text: str) -> LineageSelector:
    """Parse `+model`, `model+`, `model+N`, or `+model+`. Anything wider is refused."""
    match = _SELECTOR_RE.fullmatch((text or "").strip())
    if match is None:
        raise ManifestError(
            "Lineage selectors name one model: +model, model+, model+N, or +model+. "
            "Refusing to draw the whole project."
        )
    up_raw = match.group("up")
    down_raw = match.group("down")

    def hops(raw: str | None) -> int | None:
        if raw is None or raw == "":
            return None
        return int(raw)

    return LineageSelector(
        match.group("name"),
        hops(up_raw) if up_raw is not None else None,
        hops(down_raw) if down_raw is not None else None,
        up_raw is not None,
        down_raw is not None,
    )


class DbtManifest:
    def __init__(self, path: Path, data: dict[str, Any]):
        self.path = path
        self.data = data
        self.nodes: dict[str, dict[str, Any]] = data.get("nodes", {})
        self.sources: dict[str, dict[str, Any]] = data.get("sources", {})
        self.parents: dict[str, tuple[str, ...]] = {}
        self.children: dict[str, tuple[str, ...]] = {}
        self._index_dependencies()

    def _index_dependencies(self) -> None:
        """Parents and children from depends_on, so a manifest without child_map still works."""
        resources = self.all_resources()
        parents: dict[str, list[str]] = {}
        children: dict[str, list[str]] = {}
        for unique_id, resource in resources.items():
            deps = resource.get("depends_on", {}).get("nodes", []) or []
            for dep in deps:
                if dep not in resources or dep in parents.get(unique_id, ()):
                    continue
                parents.setdefault(unique_id, []).append(dep)
                children.setdefault(dep, [])
                if unique_id not in children[dep]:
                    children[dep].append(unique_id)
        self.parents = {key: tuple(value) for key, value in parents.items()}
        self.children = {key: tuple(value) for key, value in children.items()}

    @classmethod
    def load(cls, path: Path) -> DbtManifest:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestError(f"Could not read dbt manifest: {path}: {exc}") from exc
        return cls(path, data)

    @staticmethod
    def discover(start: Path) -> Path | None:
        current = start.resolve()
        if current.is_file():
            current = current.parent
        for directory in [current, *current.parents]:
            candidate = directory / "target" / "manifest.json"
            if candidate.exists():
                return candidate
        return None

    def all_resources(self) -> dict[str, dict[str, Any]]:
        return {**self.nodes, **self.sources}

    def find_model_for_file(self, file_path: Path) -> tuple[str, dict[str, Any]] | None:
        normalized = file_path.resolve().as_posix()
        matches: list[tuple[str, dict[str, Any]]] = []
        for unique_id, node in self.nodes.items():
            if node.get("resource_type") != "model":
                continue
            original = str(node.get("original_file_path") or "").replace("\\", "/")
            if original and normalized.endswith(original):
                matches.append((unique_id, node))
        if not matches:
            return None
        return max(matches, key=lambda item: len(str(item[1].get("original_file_path", ""))))

    def find_model(self, selector: str) -> tuple[str, dict[str, Any]] | None:
        candidates = []
        for unique_id, node in self.nodes.items():
            if node.get("resource_type") != "model":
                continue
            if selector in {unique_id, node.get("name"), node.get("alias")}:
                candidates.append((unique_id, node))
        return candidates[0] if len(candidates) == 1 else None

    def relation_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for unique_id, resource in self.all_resources().items():
            parts = [
                resource.get("database"),
                resource.get("schema"),
                resource.get("alias") or resource.get("name"),
            ]
            parts = [str(part) for part in parts if part]
            labels = []
            if parts:
                labels.extend(
                    [
                        ".".join(parts).lower(),
                        ".".join(parts[-2:]).lower(),
                        parts[-1].lower(),
                    ]
                )
            for relation_key in labels:
                mapping[relation_key] = self.display_name(unique_id)
        return mapping

    def display_name(self, unique_id: str) -> str:
        resource = self.all_resources().get(unique_id, {})
        resource_type = resource.get("resource_type")
        if resource_type == "source":
            return f"source:{resource.get('source_name')}.{resource.get('name')}"
        if resource_type == "model":
            return f"ref:{resource.get('name')}"
        return resource.get("name") or unique_id

    def compiled_sql(self, unique_id: str, node: dict[str, Any]) -> str | None:
        compiled = node.get("compiled_code") or node.get("compiled_sql")
        if compiled:
            return str(compiled)

        compiled_path = node.get("compiled_path")
        if compiled_path:
            project_root = self.path.parent.parent
            raw_path = Path(str(compiled_path))
            candidates = [project_root / raw_path, project_root / "target" / "compiled" / raw_path]
            for candidate in candidates:
                if candidate.exists():
                    return candidate.read_text()
        return None

    def dependency_graph(self, unique_id: str, max_depth: int | None = None) -> Graph:
        """Upstream refs only. `--dbt-graph` keeps this walk."""
        graph = Graph(root=unique_id)
        resources = self.all_resources()

        def visit(current: str, depth: int, seen: set[str]) -> None:
            resource = resources.get(current, {})
            graph.add_node(
                current,
                self.display_name(current),
                resource.get("resource_type", "dbt"),
            )
            if current in seen or (max_depth is not None and depth >= max_depth):
                return
            seen = {*seen, current}
            for dep in self.parents.get(current, ()):
                dep_resource = resources[dep]
                graph.add_node(
                    dep,
                    self.display_name(dep),
                    dep_resource.get("resource_type", "dbt"),
                )
                graph.add_edge(current, dep)
                visit(dep, depth + 1, seen)

        visit(unique_id, 0, set())
        return graph

    def neighborhood(self, unique_id: str, selector: LineageSelector) -> Graph:
        """Upstream and downstream hops around one model. Edges point at what a node reads."""
        if unique_id not in self.all_resources():
            raise ManifestError(f"Could not match {selector.name} in manifest.json.")
        graph = Graph(root=unique_id)
        self._put(graph, unique_id)
        if selector.walk_upstream:
            self._walk(graph, unique_id, downstream=False, limit=selector.upstream)
        if selector.walk_downstream:
            self._walk(graph, unique_id, downstream=True, limit=selector.downstream)
        return graph

    def embedded_models(self, graph: Graph, dialect: str) -> dict[str, dict]:
        """Compiled SQL graphs for a static page, so a click works without the local server."""
        labels = self.relation_map()
        pages: dict[str, dict] = {}
        for node in graph.nodes.values():
            if node.kind != "model":
                continue
            try:
                resource, sql = self.model_sql(node.id)
                root_name = str(resource.get("name") or node.id)
                cte = parse_sql_graph(
                    sql,
                    dialect=dialect,
                    root_name=root_name,
                    relation_labels=labels,
                )
            except (ManifestError, ParseError):
                continue
            pages[node.id] = {"sql": sql, "graph": cte.to_dict(), "rootName": root_name}
        return pages

    def model_sql(self, unique_id: str) -> tuple[dict[str, Any], str]:
        node = self.nodes.get(unique_id)
        if not node or node.get("resource_type") != "model":
            raise ManifestError("Only dbt models have SQL to open.")
        compiled = self.compiled_sql(unique_id, node)
        if compiled and compiled.strip():
            return node, compiled
        original = node.get("original_file_path")
        if original:
            candidate = self.path.parent.parent / str(original)
            if candidate.is_file():
                return node, candidate.read_text()
        name = node.get("name") or unique_id
        raise ManifestError(f"No compiled SQL for {name}. Run dbt compile.")

    def _put(self, graph: Graph, unique_id: str) -> None:
        resource = self.all_resources().get(unique_id, {})
        graph.add_node(
            unique_id,
            self.display_name(unique_id),
            resource.get("resource_type", "dbt"),
        )

    def _walk(self, graph: Graph, start: str, *, downstream: bool, limit: int | None) -> None:
        seen = {start}
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        while queue:
            current, depth = queue.popleft()
            if limit is not None and depth >= limit:
                continue
            neighbors = (
                self.children.get(current, ()) if downstream else self.parents.get(current, ())
            )
            for other in neighbors:
                self._put(graph, other)
                if downstream:
                    graph.add_edge(other, current)
                else:
                    graph.add_edge(current, other)
                if other not in seen:
                    seen.add(other)
                    queue.append((other, depth + 1))
