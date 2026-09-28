from __future__ import annotations

import hashlib
import json
from typing import Any

from .catalog import ResolvedPipeline
from .io import nested_get


GRAPH_SCHEMA = "conn_pilot_pipeline_graph_v1"
PLAN_SCHEMA = "conn_pilot_node_execution_plan_v1"


def resolve_pipeline_graph(pipeline: ResolvedPipeline) -> dict[str, Any]:
    """Resolve a catalog pipeline into a typed, immutable dependency graph."""
    providers: dict[str, str] = {"project": "project"}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for order, stage in enumerate(pipeline.stages, start=1):
        node_id = str(stage["id"])
        dependencies: list[str] = []
        for requirement in map(str, stage.get("requires", [])):
            provider = providers.get(requirement)
            if provider and provider != "project" and provider not in dependencies:
                dependencies.append(provider)
                edges.append({"from": provider, "to": node_id, "artifact": requirement})
        node = {
            "id": node_id,
            "version": str(stage["version"]),
            "order": order,
            "kind": str(stage.get("kind", "unknown")),
            "category": str(stage.get("category", node_id)),
            "status": str(stage.get("status", "validated")),
            "requires": list(map(str, stage.get("requires", []))),
            "provides": list(map(str, stage.get("provides", []))),
            "project_inputs": list(map(str, stage.get("project_inputs", []))),
            "depends_on": dependencies,
        }
        nodes.append(node)
        for output in node["provides"]:
            providers[output] = node_id
    identity = {
        "schema_version": GRAPH_SCHEMA,
        "pipeline": {"id": pipeline.id, "version": pipeline.version},
        "status": pipeline.definition.get("status", "unknown"),
        "analysis": pipeline.definition.get("execution", {}).get("analysis", {}),
        "nodes": nodes,
        "edges": edges,
    }
    identity["fingerprint"] = _fingerprint(identity)
    return identity


def build_node_execution_plan(
    project: dict[str, Any], pipeline: ResolvedPipeline
) -> dict[str, Any]:
    """Bind project values to graph nodes and derive stable cache identities."""
    graph = resolve_pipeline_graph(pipeline)
    cache_keys: dict[str, str] = {}
    planned = []
    for node in graph["nodes"]:
        relevant = {
            path: nested_get(project, path)
            for path in node["project_inputs"]
        }
        upstream = {dependency: cache_keys[dependency] for dependency in node["depends_on"]}
        cache_key = "sha256:" + _fingerprint(
            {
                "module": {"id": node["id"], "version": node["version"]},
                "project_inputs": relevant,
                "upstream": upstream,
            }
        )
        cache_keys[node["id"]] = cache_key
        planned.append({**node, "cache_key": cache_key, "bound_inputs": relevant})
    plan = {
        "schema_version": PLAN_SCHEMA,
        "pipeline": graph["pipeline"],
        "graph_fingerprint": graph["fingerprint"],
        "nodes": planned,
        "edges": graph["edges"],
    }
    plan["fingerprint"] = "sha256:" + _fingerprint(plan)
    return plan


def compare_node_plans(
    previous_project: dict[str, Any],
    candidate_project: dict[str, Any],
    pipeline: ResolvedPipeline,
) -> dict[str, Any]:
    """Report exactly which nodes remain reusable after a project change."""
    previous = build_node_execution_plan(previous_project, pipeline)
    candidate = build_node_execution_plan(candidate_project, pipeline)
    previous_by_id = {node["id"]: node for node in previous["nodes"]}
    changed = []
    reusable = []
    for node in candidate["nodes"]:
        old = previous_by_id.get(node["id"])
        if old and old["cache_key"] == node["cache_key"]:
            reusable.append(node["id"])
        else:
            changed.append(node["id"])
    return {
        "previous_plan": previous["fingerprint"],
        "candidate_plan": candidate["fingerprint"],
        "reusable_nodes": reusable,
        "invalidated_nodes": changed,
        "execution_required_from": changed[0] if changed else None,
        "no_execution_change": not changed,
    }


def composition_snapshot(pipeline: ResolvedPipeline) -> dict[str, Any]:
    graph = resolve_pipeline_graph(pipeline)
    return {
        "schema_version": "conn_pilot_composition_v1",
        "graph_fingerprint": graph["fingerprint"],
        "nodes": [
            {"id": node["id"], "version": node["version"]}
            for node in graph["nodes"]
        ],
    }


def validate_composition(
    composition: Any, pipeline: ResolvedPipeline
) -> list[str]:
    if composition is None:
        return []
    if not isinstance(composition, dict):
        return ["composition must be a mapping"]
    expected = composition_snapshot(pipeline)
    errors = []
    if composition.get("schema_version") != expected["schema_version"]:
        errors.append("composition has an unsupported schema_version")
    if composition.get("graph_fingerprint") != expected["graph_fingerprint"]:
        errors.append("composition graph does not match the validated pipeline template")
    if composition.get("nodes") != expected["nodes"]:
        errors.append("composition nodes do not match the validated pipeline template")
    return errors


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
