from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import CatalogError
from .io import load_yaml


@dataclass(frozen=True)
class ResolvedPipeline:
    definition: dict[str, Any]
    stages: tuple[dict[str, Any], ...]

    @property
    def id(self) -> str:
        return str(self.definition["id"])

    @property
    def version(self) -> str:
        return str(self.definition["version"])


class Catalog:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def list_pipelines(self) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for path in sorted((self.root / "pipelines").glob("*/*/pipeline.yaml")):
            value = load_yaml(path)
            records.append(
                {
                    "id": str(value.get("id", "")),
                    "version": str(value.get("version", "")),
                    "family": str(value.get("family", "")),
                    "status": str(value.get("status", "")),
                    "path": str(path),
                }
            )
        return records

    def resolve(self, pipeline_id: str, version: str) -> ResolvedPipeline:
        path = self.root / "pipelines" / pipeline_id / version / "pipeline.yaml"
        if not path.is_file():
            raise CatalogError(f"Unknown pipeline {pipeline_id}@{version}")
        definition = load_yaml(path)
        self._validate_pipeline(definition, path)
        stages: list[dict[str, Any]] = []
        seen: set[str] = set()
        for reference in definition["stages"]:
            stage_id = reference.get("id")
            stage_version = str(reference.get("version", ""))
            key = f"{stage_id}@{stage_version}"
            if key in seen:
                raise CatalogError(f"Duplicate stage reference {key} in {path}")
            seen.add(key)
            stage_path = self.root / "stages" / str(stage_id) / f"{stage_version}.yaml"
            if not stage_path.is_file():
                raise CatalogError(f"Missing stage {key} referenced by {path}")
            stage = load_yaml(stage_path)
            if stage.get("id") != stage_id or str(stage.get("version")) != stage_version:
                raise CatalogError(f"Stage identity does not match path: {stage_path}")
            stages.append(stage)
        self._validate_stage_order(stages)
        return ResolvedPipeline(definition=definition, stages=tuple(stages))

    def validate_all(self) -> list[str]:
        errors: list[str] = []
        records = self.list_pipelines()
        if not records:
            return ["Catalog contains no pipelines"]
        for record in records:
            try:
                self.resolve(record["id"], record["version"])
            except (CatalogError, ValueError) as error:
                errors.append(str(error))
        return errors

    @staticmethod
    def _validate_pipeline(value: dict[str, Any], path: Path) -> None:
        required = {"id", "version", "family", "status", "stages", "project_contract"}
        missing = sorted(required - value.keys())
        if missing:
            raise CatalogError(f"{path} misses fields: {', '.join(missing)}")
        if not isinstance(value["stages"], list) or not value["stages"]:
            raise CatalogError(f"{path} must contain at least one stage")
        family_path = path.parents[3] / "families" / f"{value['family']}.yaml"
        if not family_path.is_file():
            raise CatalogError(f"Unknown family {value['family']} in {path}")
        analysis = value.get("execution", {}).get("analysis", {})
        required_analysis = {"kind", "conn_name", "conn_type", "first_level_artifact", "second_level_artifact"}
        if not required_analysis.issubset(analysis):
            missing_analysis = sorted(required_analysis - set(analysis))
            raise CatalogError(f"{path} execution.analysis misses fields: {', '.join(missing_analysis)}")

    @staticmethod
    def _validate_stage_order(stages: list[dict[str, Any]]) -> None:
        available: set[str] = {"project"}
        for stage in stages:
            stage_id = str(stage["id"])
            for field in ("kind", "category", "status", "requires", "provides", "project_inputs"):
                if field not in stage:
                    raise CatalogError(f"Stage {stage_id} is missing {field}")
            missing = [item for item in stage.get("requires", []) if item not in available]
            if missing:
                raise CatalogError(f"Stage {stage_id} has unresolved requirements: {', '.join(missing)}")
            available.update(str(item) for item in stage.get("provides", []))
