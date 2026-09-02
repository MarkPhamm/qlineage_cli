from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Graph


class ManifestError(RuntimeError):
    pass


class DbtManifest:
    def __init__(self, path: Path, data: dict[str, Any]):
        self.path = path
        self.data = data
        self.nodes: dict[str, dict[str, Any]] = data.get("nodes", {})
        self.sources: dict[str, dict[str, Any]] = data.get("sources", {})

    @classmethod
    def load(cls, path: Path) -> "DbtManifest":
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
            parts = [resource.get("database"), resource.get("schema"), resource.get("alias") or resource.get("name")]
            parts = [str(part) for part in parts if part]
            labels = []
            if parts:
                labels.extend([".".join(parts).lower(), ".".join(parts[-2:]).lower(), parts[-1].lower()])
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
        graph = Graph(root=unique_id)
        resources = self.all_resources()

        def visit(current: str, depth: int, seen: set[str]) -> None:
            resource = resources.get(current, {})
            graph.add_node(current, self.display_name(current), resource.get("resource_type", "dbt"))
            if current in seen or (max_depth is not None and depth >= max_depth):
                return
            seen = {*seen, current}
            for dep in resource.get("depends_on", {}).get("nodes", []):
                if dep not in resources:
                    continue
                dep_resource = resources[dep]
                graph.add_node(dep, self.display_name(dep), dep_resource.get("resource_type", "dbt"))
                graph.add_edge(current, dep)
                visit(dep, depth + 1, seen)

        visit(unique_id, 0, set())
        return graph
