from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import Counter
from typing import Any

from .catalog import ResolvedPipeline
from .io import nested_get
from .literature import LiteratureEvidenceService
from .project import parameter_value_errors


RESOLVER_SCHEMA = "conn_pilot_parameter_resolver_v1"
ASSESSMENT_SCHEMA = "conn_pilot_parameter_assessment_v1"
RESOLVER_REVISION = "context-and-strict-normalization-v2"


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
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 through 100")
        context = self._experiment_context(project, pipeline)
        observations = self._observations(guidance, explicit_only=False)
        assessed = [self._assess(record, guidance, spec, parameter_path, context)
                    for record in observations]
        grouped: dict[str, dict[str, Any]] = {}
        for observation, assessment in zip(observations, assessed):
            if not assessment["executable_candidate"]:
                continue
            normalized = assessment["normalized_value"]
            key = _canonical(normalized)
            option = grouped.setdefault(
                key,
                {
                    "value": normalized,
                    "observation_count": 0,
                    "paper_pmids": set(),
                    "evidence_ids": [],
                    "reported_forms": set(),
                    "context_alignment_summary": {"primary_family": Counter(), "modality_or_task": Counter()},
                },
            )
            option["observation_count"] += 1
            option["paper_pmids"].add(observation["paper"]["pmid"])
            option["evidence_ids"].append(observation["evidence_id"])
            option["reported_forms"].add(_canonical(observation["value"]))
            for field, alignment in assessment["context_alignment"].items():
                option["context_alignment_summary"][field][alignment["status"]] += 1
        options = []
        for option in grouped.values():
            options.append(
                {
                    **option,
                    "paper_pmids": sorted(option["paper_pmids"]),
                    "evidence_ids": sorted(option["evidence_ids"]),
                    "paper_count": len(option["paper_pmids"]),
                    "context_alignment_summary": {field: dict(sorted(counts.items()))
                        for field, counts in option["context_alignment_summary"].items()},
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
            "resolver_revision": RESOLVER_REVISION,
            "experiment_context": context,
            "contract": {
                key: value
                for key, value in spec.items()
                if key in {"type", "minimum", "maximum", "values", "implemented_values", "maps_to"}
            },
            "options": options[:limit],
            "option_count": len(options),
            "options_truncated": len(options) > limit,
            "option_order": "descriptive_observation_frequency_then_value",
            "reporting_summary": dict(sorted(Counter(
                item["evidence_status"] for item in observations).items())),
            "unparsed_explicit_observation_count": sum(
                item["evidence_status"] == "explicit" and item["normalized_value"] is None
                for item in assessed),
            "incompatible_explicit_observation_count": sum(
                item["evidence_status"] == "explicit" and bool(item["compatibility_errors"])
                for item in assessed),
            "evidence_assessments": assessed,
            "policy": {
                "automatic_default": False,
                "frequency_is_not_a_recommendation": True,
                "requires_investigator_confirmation": True,
                "scientific_appraisal_status": "pending",
                "context_alignment_is_not_scientific_applicability": True,
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
        if (not isinstance(evidence_ids, list) or not evidence_ids
                or any(not isinstance(item, str) or not item for item in evidence_ids)):
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
        for evidence_id in sorted(set(evidence_ids)):
            record = self.literature._records_by_id.get(evidence_id)
            if record is None:
                unknown.append(evidence_id)
                continue
            cited.append(copy.deepcopy(record))
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
        decision_guidance = self.guidance(project, pipeline, parameter_path, limit=100)
        assessments = {item["evidence_id"]: item for item in decision_guidance["evidence_assessments"]}
        for record in cited:
            record["resolver_assessment"] = assessments[record["evidence_id"]]
        audit = {
            "schema_version": ASSESSMENT_SCHEMA,
            "resolver_revision": RESOLVER_REVISION,
            "parameter_path": parameter_path,
            "selected_value": normalized_choice,
            "corpus_version": self.literature.corpus_version,
            "corpus_sha256": self.literature.corpus_sha256,
            "experiment_context": decision_guidance["experiment_context"],
            "pipeline_contract_sha256": _digest(pipeline.definition["project_contract"]),
            "evidence_snapshot_sha256": _digest(cited),
            "exact_evidence_ids": sorted({item["evidence_id"] for item in exact}),
            "alternative_cited_evidence_ids": [item["evidence_id"] for item in cited
                if item["evidence_status"] == "explicit"
                and item["resolver_assessment"]["normalized_value"] is not None
                and _canonical(item["resolver_assessment"]["normalized_value"]) != _canonical(normalized_choice)],
            "guidance_snapshot": {key: decision_guidance[key] for key in (
                "options", "option_count", "option_order", "reporting_summary", "evidence_assessments")},
            "scientific_validity_determined": False,
            "limitations": [
                "Different reported values are alternatives, not evidence of scientific conflict.",
                "Matching analysis metadata does not establish acquisition or population applicability.",
                "Source roles and parameter-level risk of bias are not curated.",
                "The snapshot is reconstructed at decision time; it does not prove which response the client viewed.",
            ],
        }
        audit["audit_sha256"] = _digest(audit)
        return {
            "schema_version": RESOLVER_SCHEMA,
            "parameter_path": parameter_path,
            "selected_value": normalized_choice,
            "topic": guidance["topic"],
            "literature_component_ids": sorted({item["component_id"] for item in exact}),
            "literature_parameter_names": sorted({item["parameter_name"] for item in exact}),
            "exact_evidence_ids": [item["evidence_id"] for item in exact],
            "evidence_snapshot": cited,
            "selection_audit": audit,
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

    def audit_context_matches(self, audit: dict[str, Any], project: dict[str, Any],
                              pipeline: ResolvedPipeline) -> bool:
        return (audit.get("experiment_context") == self._experiment_context(project, pipeline)
                and audit.get("pipeline_contract_sha256") == _digest(pipeline.definition["project_contract"]))

    def _observations(self, guidance: dict[str, Any], *, explicit_only: bool = True) -> list[dict[str, Any]]:
        allowed = {
            (str(source["component_id"]), str(name))
            for source in guidance["sources"]
            for name in source["parameter_names"]
        }
        return [
            record
            for record in self.literature.records
            if (not explicit_only or record["evidence_status"] == "explicit")
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
            "design_sha256": _digest(project_spec.get("design", {})),
            "seed_sources": [seed.get("conn_source") for seed in project_spec.get("seeds", [])
                             if isinstance(seed, dict)],
            "tr_seconds": self._tr_seconds(project),
            "scope": pipeline.definition.get("scope", {}),
            "literature_primary_family": pipeline.id,
            "modality_or_task": "resting_state_fmri_plus_anatomical_mri"
                if pipeline.id in {"rsfmri_seed_to_voxel", "rsfmri_roi_to_roi"} else None,
            "dataset_fingerprint": project.get("dataset_fingerprint"),
            "research_question": nested_get(project_spec, "project.research_question"),
        }

    @staticmethod
    def _assess(record: dict[str, Any], guidance: dict[str, Any], spec: dict[str, Any],
                path: str, context: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_observed_value(guidance["normalizer"], record["value"])
        errors = parameter_value_errors(path, normalized, spec, tr_seconds=context["tr_seconds"]) \
            if normalized is not None else []
        status = record["evidence_status"]
        reason = ("not_explicit" if status != "explicit" else
                  "unparsed_or_ambiguous" if normalized is None else
                  "incompatible_with_execution" if errors else None)
        classification = record.get("classification", {})
        alignments = {}
        for field, project_key in (("primary_family", "literature_primary_family"),
                                   ("modality_or_task", "modality_or_task")):
            observed, requested = classification.get(field), context.get(project_key)
            alignments[field] = {
                "paper_value": observed, "project_value": requested,
                "status": "unknown" if not observed or not requested else
                          "matching" if observed == requested else "different",
            }
        return {
            "evidence_id": record["evidence_id"],
            "paper": record["paper"],
            "evidence_status": status,
            "reported_value": record["value"],
            "normalized_value": normalized,
            "executable_candidate": reason is None,
            "exclusion_reason": reason,
            "compatibility_errors": errors,
            "context_alignment": alignments,
            "study_design": {"paper_value": classification.get("study_design"),
                             "project_value": context["design_type"],
                             "status": "not_assessed", "reason": "Different classification vocabularies; no inferred design equivalence."},
            "unassessed_dimensions": ["population", "acquisition_tr", "voxel_resolution",
                                      "motion_metric_definition", "source_role", "risk_of_bias"],
            "source_path": record.get("source_path"),
            "unresolved": record.get("unresolved", []),
            "scientific_applicability": "requires_review",
        }


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def selection_audit_integrity(audit: dict[str, Any], evidence_snapshot: list[dict[str, Any]]) -> bool:
    """Check frozen audit and citation contents without consulting a newer corpus."""
    if not isinstance(audit, dict) or audit.get("schema_version") != ASSESSMENT_SCHEMA:
        return False
    payload = {key: value for key, value in audit.items() if key != "audit_sha256"}
    return (audit.get("audit_sha256") == _digest(payload)
            and audit.get("evidence_snapshot_sha256") == _digest(evidence_snapshot))


def normalize_observed_value(normalizer: str, value: Any) -> Any | None:
    if normalizer == "boolean":
        return value if isinstance(value, bool) else None
    if normalizer == "integer_scalar":
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    if normalizer in {"millimeters", "standard_deviations"}:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value) if math.isfinite(value) else None
        if not isinstance(value, str):
            return None
        number = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))"
        if normalizer == "millimeters":
            pattern = (r"(?:(?:framewise displacement|displacement|translation)\s*)?"
                       r"(?:>=?|\u2265)?\s*" + number + r"\s*mm(?:\s+(?:translation|fwhm))?")
        else:
            pattern = (r"(?:(?:bold change|z)\s*)?(?:greater than\s+|>=?|\u2265|\u00b1)?\s*"
                       + number + r"\s*(?:standard deviations?|sd)?")
        match = re.fullmatch(pattern, value.strip(), flags=re.IGNORECASE)
        return float(match[1]) if match else None
    if normalizer == "frequency_pair_hz":
        if (
            isinstance(value, list)
            and len(value) == 2
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
        ):
            return [float(value[0]), float(value[1])] if all(math.isfinite(item) for item in value) else None
        if not isinstance(value, str) or "inconsistent" in value.lower() or "not used" in value.lower():
            return None
        number = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))"
        match = re.fullmatch(number + r"\s*[-\u2013\u2014]\s*" + number + r"\s*(?:hz)?",
                             value.strip(), flags=re.IGNORECASE)
        return [float(match[1]), float(match[2])] if match else None
    raise ValueError(f"Unknown literature value normalizer: {normalizer}")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
