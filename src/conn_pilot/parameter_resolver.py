from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from .catalog import ResolvedPipeline
from .io import nested_get
from .literature import LiteratureEvidenceService
from .project import parameter_value_errors


RESOLVER_SCHEMA = "conn_pilot_parameter_resolver_v1"


class ParameterResolver:
    """Map reviewed literature observations onto executable pipeline parameters."""

    def __init__(self, literature: LiteratureEvidenceService) -> None:
        self.literature = literature

    def guidance(
        self,
        project: dict[str, Any],
        pipeline: ResolvedPipeline,
        parameter_path: str,
        *,
        limit: int = 50,
    ) -> dict[str, Any]:
        spec, guidance = self._guidance_spec(pipeline, parameter_path)
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 through 100")
        observations = self._observations(guidance)
        grouped: dict[str, dict[str, Any]] = {}
        for observation in observations:
            normalized = normalize_observed_value(
                guidance["normalizer"], observation["value"]
            )
            if normalized is None:
                continue
            errors = parameter_value_errors(
                parameter_path,
                normalized,
                spec,
                tr_seconds=self._tr_seconds(project),
            )
            if errors:
                continue
            key = _canonical(normalized)
            option = grouped.setdefault(
                key,
                {
                    "value": normalized,
                    "observation_count": 0,
                    "paper_pmids": set(),
                    "evidence_ids": [],
                    "reported_forms": set(),
                },
            )
            option["observation_count"] += 1
            option["paper_pmids"].add(observation["paper"]["pmid"])
            option["evidence_ids"].append(observation["evidence_id"])
            option["reported_forms"].add(_canonical(observation["value"]))
        options = []
        for option in grouped.values():
            options.append(
                {
                    **option,
                    "paper_pmids": sorted(option["paper_pmids"]),
                    "evidence_ids": sorted(option["evidence_ids"]),
                    "reported_forms": [
                        json.loads(value) for value in sorted(option["reported_forms"])
                    ],
                }
            )
        options.sort(key=lambda item: (-item["observation_count"], _canonical(item["value"])))
        current = nested_get(project.get("spec", project), f"parameters.{parameter_path}")
        return {
            "schema_version": RESOLVER_SCHEMA,
            "corpus_version": self.literature.corpus_version,
            "corpus_sha256": self.literature.corpus_sha256,
            "parameter_path": parameter_path,
            "topic": guidance["topic"],
            "current_record": current,
            "experiment_context": self._experiment_context(project, pipeline),
            "contract": {
                key: value
                for key, value in spec.items()
                if key in {"type", "minimum", "maximum", "values", "implemented_values", "maps_to"}
            },
            "options": options[:limit],
            "option_count": len(options),
            "unparsed_explicit_observation_count": len(observations)
            - sum(item["observation_count"] for item in options),
            "policy": {
                "automatic_default": False,
                "frequency_is_not_a_recommendation": True,
                "requires_investigator_confirmation": True,
                "scientific_appraisal_status": "pending",
            },
        }

    def validate_choice(
        self,
        project: dict[str, Any],
        pipeline: ResolvedPipeline,
        parameter_path: str,
        selected_value: Any,
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        spec, guidance = self._guidance_spec(pipeline, parameter_path)
        errors = parameter_value_errors(
            parameter_path,
            selected_value,
            spec,
            tr_seconds=self._tr_seconds(project),
        )
        if errors:
            raise ValueError("; ".join(errors))
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise ValueError("At least one evidence identifier is required")
        if len(evidence_ids) > 50:
            raise ValueError("At most 50 evidence identifiers may be cited")
        normalized_choice = normalize_observed_value(
            guidance["normalizer"], selected_value
        )
        if normalized_choice is None:
            raise ValueError("The selected value cannot be normalized for this parameter")
        source_pairs = {
            (str(source["component_id"]), str(parameter_name))
            for source in guidance["sources"]
            for parameter_name in source["parameter_names"]
        }
        cited = []
        unknown = []
        incompatible = []
        exact = []
        for evidence_id in evidence_ids:
            record = self.literature._records_by_id.get(evidence_id)
            if record is None:
                unknown.append(evidence_id)
                continue
            cited.append(record)
            if (record["component_id"], record["parameter_name"]) not in source_pairs:
                incompatible.append(evidence_id)
                continue
            normalized = normalize_observed_value(guidance["normalizer"], record["value"])
            if (
                record["evidence_status"] == "explicit"
                and normalized is not None
                and _canonical(normalized) == _canonical(normalized_choice)
            ):
                exact.append(record)
        if unknown:
            raise ValueError(f"Unknown evidence identifiers: {', '.join(sorted(unknown))}")
        if incompatible:
            raise ValueError(
                "Evidence does not belong to this executable parameter: "
                + ", ".join(sorted(incompatible))
            )
        if not exact:
            raise ValueError(
                "The selected value has no exact normalized match in the cited explicit evidence"
            )
        return {
            "schema_version": RESOLVER_SCHEMA,
            "parameter_path": parameter_path,
            "selected_value": normalized_choice,
            "topic": guidance["topic"],
            "literature_component_ids": sorted({item["component_id"] for item in exact}),
            "literature_parameter_names": sorted({item["parameter_name"] for item in exact}),
            "exact_evidence_ids": [item["evidence_id"] for item in exact],
            "evidence_snapshot": cited,
            "corpus_version": self.literature.corpus_version,
            "corpus_sha256": self.literature.corpus_sha256,
            "scientific_validity_determined": False,
            "requires_investigator_confirmation": True,
        }

    def unresolved_paths(
        self, project: dict[str, Any], pipeline: ResolvedPipeline
    ) -> list[dict[str, Any]]:
        project_spec = project.get("spec", project)
        result = []
        specs = pipeline.definition["project_contract"].get("parameters", {})
        for path, spec in specs.items():
            guidance = spec.get("literature_guidance")
            if not guidance or not guidance.get("required_remote"):
                continue
            record = nested_get(project_spec, f"parameters.{path}")
            resolved = bool(
                isinstance(record, dict)
                and record.get("confirmed_by_investigator")
                and record.get("method_decision_id")
                and record.get("evidence_ids")
                and record.get("corpus_version")
            )
            result.append(
                {
                    "parameter_path": path,
                    "topic": guidance["topic"],
                    "resolved": resolved,
                    "current_value": record.get("value") if isinstance(record, dict) else None,
                    "method_decision_id": record.get("method_decision_id") if isinstance(record, dict) else None,
                }
            )
        return result

    def _observations(self, guidance: dict[str, Any]) -> list[dict[str, Any]]:
        allowed = {
            (str(source["component_id"]), str(name))
            for source in guidance["sources"]
            for name in source["parameter_names"]
        }
        return [
            record
            for record in self.literature.records
            if record["evidence_status"] == "explicit"
            and (record["component_id"], record["parameter_name"]) in allowed
        ]

    @staticmethod
    def _guidance_spec(
        pipeline: ResolvedPipeline, parameter_path: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        specs = pipeline.definition["project_contract"].get("parameters", {})
        spec = specs.get(parameter_path)
        if not spec:
            raise ValueError(f"Unknown executable parameter: {parameter_path}")
        guidance = spec.get("literature_guidance")
        if not guidance:
            raise ValueError(f"Parameter has no literature guidance mapping: {parameter_path}")
        return spec, guidance

    @staticmethod
    def _tr_seconds(project: dict[str, Any]) -> Any:
        if "spec" in project:
            return project.get("dataset_metadata", {}).get("tr_seconds")
        return nested_get(project, "dataset.tr_seconds")

    def _experiment_context(
        self, project: dict[str, Any], pipeline: ResolvedPipeline
    ) -> dict[str, Any]:
        project_spec = project.get("spec", project)
        return {
            "pipeline_id": pipeline.id,
            "pipeline_version": pipeline.version,
            "family": pipeline.definition.get("family"),
            "design_type": nested_get(project_spec, "design.type"),
            "tr_seconds": self._tr_seconds(project),
            "scope": pipeline.definition.get("scope", {}),
        }


def normalize_observed_value(normalizer: str, value: Any) -> Any | None:
    if normalizer == "boolean":
        return value if isinstance(value, bool) else None
    if normalizer == "integer_scalar":
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    if normalizer in {"millimeters", "standard_deviations"}:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if not isinstance(value, str):
            return None
        numbers = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", value)
        return float(numbers[0]) if numbers else None
    if normalizer == "frequency_pair_hz":
        if (
            isinstance(value, list)
            and len(value) == 2
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
        ):
            return [float(value[0]), float(value[1])]
        if not isinstance(value, str) or "inconsistent" in value.lower() or "not used" in value.lower():
            return None
        numbers = re.findall(r"\d*\.\d+", value)
        if len(numbers) != 2:
            return None
        return [float(numbers[0]), float(numbers[1])]
    raise ValueError(f"Unknown literature value normalizer: {normalizer}")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
