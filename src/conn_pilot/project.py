from __future__ import annotations

import math
import re
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog import ResolvedPipeline
from .io import nested_get
from .pipeline_graph import validate_composition


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


REQUIRED_TOP_LEVEL_FIELDS = {"schema_version", "pipeline", "project", "dataset", "subjects", "design", "seeds", "parameters"}
OPTIONAL_TOP_LEVEL_FIELDS = {"composition", "hypothesis"}
TOP_LEVEL_FIELDS = REQUIRED_TOP_LEVEL_FIELDS | OPTIONAL_TOP_LEVEL_FIELDS
PIPELINE_FIELDS = {"id", "version"}
PROJECT_FIELDS = {"name", "research_question"}
DATASET_FIELDS = {"layout", "root", "tr_seconds"}
PARAMETER_RECORD_REQUIRED_FIELDS = {"value", "source", "rationale", "confirmed_by_investigator"}
PARAMETER_RECORD_OPTIONAL_FIELDS = {"method_decision_id", "evidence_ids", "corpus_version", "selection_audit"}
PARAMETER_RECORD_FIELDS = PARAMETER_RECORD_REQUIRED_FIELDS | PARAMETER_RECORD_OPTIONAL_FIELDS
SEED_FIELDS = {"name", "conn_source", "rationale", "confirmed_by_investigator"}
SUBJECT_FIELDS = {"id", "functional", "structural"}
DESIGN_FIELDS = {"type", "groups", "covariates", "contrasts"}
HYPOTHESIS_FIELDS = {
    "statement", "target_contrast", "expected_direction", "decision_rule", "sample_adequacy"
}


def validate_project(project: dict[str, Any], pipeline: ResolvedPipeline, *, check_paths: bool) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    unknown_top = sorted(set(project) - TOP_LEVEL_FIELDS)
    if unknown_top:
        errors.append(f"Unknown top-level fields: {', '.join(unknown_top)}")
    for field in sorted(REQUIRED_TOP_LEVEL_FIELDS):
        if field not in project:
            errors.append(f"Missing top-level field: {field}")
    schema_version = project.get("schema_version")
    if schema_version not in {"conn_pilot_project_v1", "conn_pilot_project_v2"}:
        errors.append("schema_version must be conn_pilot_project_v1 or conn_pilot_project_v2")
    if schema_version == "conn_pilot_project_v2" and "composition" not in project:
        errors.append("conn_pilot_project_v2 requires composition")
    if schema_version == "conn_pilot_project_v1" and "composition" in project:
        errors.append("composition requires conn_pilot_project_v2")

    pipeline_ref = project.get("pipeline", {})
    if not isinstance(pipeline_ref, dict):
        errors.append("pipeline must be a mapping")
        pipeline_ref = {}
    else:
        unknown = sorted(set(pipeline_ref) - PIPELINE_FIELDS)
        if unknown:
            errors.append(f"pipeline has unknown fields: {', '.join(unknown)}")
    if pipeline_ref.get("id") != pipeline.id or str(pipeline_ref.get("version")) != pipeline.version:
        errors.append(f"Project must reference {pipeline.id}@{pipeline.version}")

    metadata = project.get("project", {})
    if not isinstance(metadata, dict):
        errors.append("project must be a mapping")
    else:
        unknown = sorted(set(metadata) - PROJECT_FIELDS)
        if unknown:
            errors.append(f"project has unknown fields: {', '.join(unknown)}")
        for field in PROJECT_FIELDS:
            if not metadata.get(field):
                errors.append(f"project.{field} is required")

    _validate_dataset(project.get("dataset", {}), errors, warnings, check_paths)
    subjects = _validate_subjects(project.get("subjects"), errors, check_paths)
    _validate_design(project.get("design", {}), subjects, pipeline, errors, warnings)
    _validate_hypothesis(project.get("hypothesis"), project.get("design", {}), errors)
    _validate_seeds(project.get("seeds"), pipeline, errors)
    _validate_parameters(project, pipeline, errors, warnings)
    errors.extend(validate_composition(project.get("composition"), pipeline))
    return ValidationResult(not errors, tuple(_unique(errors)), tuple(_unique(warnings)))


def _validate_hypothesis(value: Any, design: Any, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append("hypothesis must be a mapping")
        return
    unknown = sorted(set(value) - HYPOTHESIS_FIELDS)
    if unknown:
        errors.append(f"hypothesis has unknown fields: {', '.join(unknown)}")
    for field in ("statement", "target_contrast", "expected_direction", "decision_rule"):
        if not value.get(field):
            errors.append(f"hypothesis.{field} is required")
    if value.get("expected_direction") not in {"positive", "negative", "nonzero"}:
        errors.append("hypothesis.expected_direction must be positive, negative, or nonzero")
    contrasts = design.get("contrasts", []) if isinstance(design, dict) else []
    contrast_names = {
        str(item.get("name")) for item in contrasts if isinstance(item, dict) and item.get("name")
    }
    if value.get("target_contrast") and str(value["target_contrast"]) not in contrast_names:
        errors.append("hypothesis.target_contrast must name a design contrast")
    rule = value.get("decision_rule")
    if rule is not None:
        if not isinstance(rule, dict):
            errors.append("hypothesis.decision_rule must be a mapping")
        else:
            alpha = rule.get("alpha")
            if not _is_number(alpha) or not 0 < float(alpha) <= 1:
                errors.append("hypothesis.decision_rule.alpha must be greater than 0 and at most 1")
            if not rule.get("multiplicity_method"):
                errors.append("hypothesis.decision_rule.multiplicity_method is required")
    adequacy = value.get("sample_adequacy")
    if adequacy is not None and (
        not isinstance(adequacy, dict) or not adequacy.get("basis")
    ):
        errors.append("hypothesis.sample_adequacy must document a basis")


def _validate_dataset(dataset: Any, errors: list[str], warnings: list[str], check_paths: bool) -> None:
    if not isinstance(dataset, dict):
        errors.append("dataset must be a mapping")
        return
    unknown = sorted(set(dataset) - DATASET_FIELDS)
    if unknown:
        errors.append(f"dataset has unknown fields: {', '.join(unknown)}")
    if str(dataset.get("layout", "")).lower() != "bids":
        errors.append("dataset.layout must be bids")
    root = dataset.get("root")
    if not root:
        errors.append("dataset.root is required")
    elif check_paths and not Path(root).is_dir():
        errors.append(f"dataset.root does not exist: {root}")
    tr = dataset.get("tr_seconds")
    if not _is_number(tr) or float(tr) <= 0:
        errors.append("dataset.tr_seconds must be a positive number")
    elif float(tr) > 5:
        warnings.append("dataset.tr_seconds is unusually high; confirm units are seconds")


def _validate_subjects(value: Any, errors: list[str], check_paths: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        errors.append("subjects must contain at least one subject")
        return []
    ids: list[str] = []
    for index, subject in enumerate(value):
        prefix = f"subjects[{index}]"
        if not isinstance(subject, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        unknown = sorted(set(subject) - SUBJECT_FIELDS)
        if unknown:
            errors.append(f"{prefix} has unknown fields: {', '.join(unknown)}")
        subject_id = subject.get("id")
        if not subject_id:
            errors.append(f"{prefix}.id is required")
        else:
            ids.append(str(subject_id))
        for field in ("functional", "structural"):
            paths = subject.get(field)
            if not isinstance(paths, list) or len(paths) != 1 or not isinstance(paths[0], str):
                errors.append(f"{prefix}.{field} must contain exactly one path")
            elif check_paths and not Path(paths[0]).is_file():
                errors.append(f"{prefix}.{field} path does not exist: {paths[0]}")
    if len(ids) != len(set(ids)):
        errors.append("subjects contain duplicate ids")
    return [item for item in value if isinstance(item, dict)]


def _validate_design(
    design: Any,
    subjects: list[dict[str, Any]],
    pipeline: ResolvedPipeline,
    errors: list[str],
    warnings: list[str],
) -> None:
    if not isinstance(design, dict):
        errors.append("design must be a mapping")
        return
    unknown = sorted(set(design) - DESIGN_FIELDS)
    if unknown:
        errors.append(f"design has unknown fields: {', '.join(unknown)}")
    design_type = design.get("type")
    supported = pipeline.definition["project_contract"].get("design_types", [])
    if design_type not in supported:
        errors.append(f"Unsupported design.type: {design_type}")
    subject_ids = {str(item.get("id")) for item in subjects if item.get("id")}
    groups = design.get("groups", {})
    if not isinstance(groups, dict) or not groups:
        errors.append("design.groups must define at least one group")
        groups = {}
    assigned: set[str] = set()
    for name, members in groups.items():
        if not isinstance(members, list) or not members:
            errors.append(f"design.groups.{name} must contain subjects")
            continue
        if len(members) != len(set(map(str, members))):
            errors.append(f"design.groups.{name} contains duplicate subjects")
        unknown_subjects = sorted(set(map(str, members)) - subject_ids)
        if unknown_subjects:
            errors.append(f"design.groups.{name} references unknown subjects: {', '.join(unknown_subjects)}")
        overlap = assigned.intersection(map(str, members))
        if overlap:
            errors.append(f"Subjects assigned to more than one group: {', '.join(sorted(overlap))}")
        assigned.update(map(str, members))
    unassigned = sorted(subject_ids - assigned)
    if unassigned:
        errors.append(f"Subjects without a group: {', '.join(unassigned)}")
    if design_type == "one_sample" and len(groups) != 1:
        errors.append("one_sample design requires exactly one group")
    if design_type == "two_independent_groups" and len(groups) != 2:
        errors.append("two_independent_groups design requires exactly two groups")

    covariates = design.get("covariates", {})
    if not isinstance(covariates, dict):
        errors.append("design.covariates must be a mapping")
        covariates = {}
    for name, values in covariates.items():
        if not isinstance(values, dict):
            errors.append(f"design.covariates.{name} must map subject ids to numbers")
            continue
        if set(values) != subject_ids:
            errors.append(f"design.covariates.{name} must define every subject exactly once")
        if not all(_is_number(item) and math.isfinite(float(item)) for item in values.values()):
            errors.append(f"design.covariates.{name} must contain finite numbers")

    effects = ["AllSubjects", *groups.keys(), *covariates.keys()]
    contrasts = design.get("contrasts")
    if not isinstance(contrasts, list) or not contrasts:
        errors.append("design.contrasts must contain at least one contrast")
        return
    for index, contrast in enumerate(contrasts):
        prefix = f"design.contrasts[{index}]"
        if not isinstance(contrast, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        allowed = {"name", "effects", "weights", "rationale", "confirmed_by_investigator"}
        unknown = sorted(set(contrast) - allowed)
        if unknown:
            errors.append(f"{prefix} has unknown fields: {', '.join(unknown)}")
        for field in ("name", "rationale"):
            if not contrast.get(field):
                errors.append(f"{prefix}.{field} is required")
        names = contrast.get("effects", [])
        weights = contrast.get("weights", [])
        if not names or len(names) != len(weights):
            errors.append(f"{prefix} effects and weights must be non-empty and have equal length")
        if any(name not in effects for name in names):
            errors.append(f"{prefix} references an unknown second-level effect")
        if not all(_is_number(weight) and math.isfinite(float(weight)) for weight in weights):
            errors.append(f"{prefix}.weights must contain finite numbers")
        if weights and all(float(weight) == 0 for weight in weights):
            errors.append(f"{prefix}.weights cannot all be zero")
        if not contrast.get("confirmed_by_investigator"):
            errors.append(f"{prefix} is not confirmed by the investigator")


def _validate_seeds(value: Any, pipeline: ResolvedPipeline, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append("seeds must contain at least one CONN source")
        return
    names: list[str] = []
    for index, seed in enumerate(value):
        prefix = f"seeds[{index}]"
        if not isinstance(seed, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        unknown = sorted(set(seed) - SEED_FIELDS)
        if unknown:
            errors.append(f"{prefix} has unknown fields: {', '.join(unknown)}")
        for field in ("name", "conn_source", "rationale"):
            if not seed.get(field):
                errors.append(f"{prefix}.{field} is required")
        names.append(str(seed.get("name", "")))
        if not seed.get("confirmed_by_investigator"):
            errors.append(f"{prefix} is not confirmed by the investigator")
    if len(names) != len(set(names)):
        errors.append("seeds contain duplicate names")
    minimum = int(
        pipeline.definition.get("project_contract", {})
        .get("region_count", {})
        .get("minimum", 1)
    )
    if len(value) < minimum:
        errors.append(f"Pipeline requires at least {minimum} confirmed regions")


def _validate_parameters(project: dict[str, Any], pipeline: ResolvedPipeline, errors: list[str], warnings: list[str]) -> None:
    parameters = project.get("parameters")
    if not isinstance(parameters, dict):
        errors.append("parameters must be a mapping")
        return
    specs = pipeline.definition["project_contract"].get("parameters", {})
    actual_paths = set(_parameter_paths(parameters))
    expected_paths = set(specs)
    missing = sorted(expected_paths - actual_paths)
    unknown = sorted(actual_paths - expected_paths)
    if missing:
        errors.append(f"Missing parameters: {', '.join(missing)}")
    if unknown:
        errors.append(f"Unknown parameters: {', '.join(unknown)}")
    tr = nested_get(project, "dataset.tr_seconds")
    for path, spec in specs.items():
        record = nested_get(parameters, path)
        if not isinstance(record, dict):
            continue
        fields = set(record)
        unknown_fields = sorted(fields - PARAMETER_RECORD_FIELDS)
        missing_fields = sorted(PARAMETER_RECORD_REQUIRED_FIELDS - fields)
        if unknown_fields:
            errors.append(f"parameters.{path} has unknown fields: {', '.join(unknown_fields)}")
        if missing_fields:
            errors.append(f"parameters.{path} misses fields: {', '.join(missing_fields)}")
        if not record.get("source") or not record.get("rationale"):
            errors.append(f"parameters.{path} requires source and rationale")
        if spec.get("confirmation_required") and not record.get("confirmed_by_investigator"):
            errors.append(f"parameters.{path} is not confirmed by the investigator")
        if "selection_audit" in record and not isinstance(record["selection_audit"], dict):
            errors.append(f"parameters.{path}.selection_audit must be an object")
        if "method_decision_id" in record:
            if not record.get("method_decision_id"):
                errors.append(f"parameters.{path}.method_decision_id cannot be empty")
            if not isinstance(record.get("evidence_ids"), list) or not record.get("evidence_ids"):
                errors.append(f"parameters.{path}.evidence_ids must contain cited evidence")
            if not record.get("corpus_version"):
                errors.append(f"parameters.{path}.corpus_version is required for a method decision")
        _validate_parameter_value(path, record.get("value"), spec, errors)
    bandpass = nested_get(parameters, "denoising.bandpass_filter_hz.value")
    if isinstance(bandpass, list) and len(bandpass) == 2 and _is_number(tr) and float(tr) > 0:
        nyquist = 1 / (2 * float(tr))
        if float(bandpass[1]) >= nyquist:
            errors.append(f"parameters.denoising.bandpass_filter_hz high cutoff must be below Nyquist ({nyquist:.6g} Hz)")


def _validate_parameter_value(path: str, value: Any, spec: dict[str, Any], errors: list[str]) -> None:
    kind = spec.get("type")
    if kind == "number":
        if not _is_number(value):
            errors.append(f"parameters.{path}.value must be numeric")
            return
        number = float(value)
        if "minimum" in spec and number < float(spec["minimum"]):
            errors.append(f"parameters.{path}.value must be >= {spec['minimum']}")
        if "maximum" in spec and number > float(spec["maximum"]):
            errors.append(f"parameters.{path}.value must be <= {spec['maximum']}")
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"parameters.{path}.value must be an integer")
        elif "minimum" in spec and value < int(spec["minimum"]):
            errors.append(f"parameters.{path}.value must be >= {spec['minimum']}")
    elif kind == "boolean":
        if not isinstance(value, bool):
            errors.append(f"parameters.{path}.value must be boolean")
    elif kind == "enum":
        if value not in spec.get("values", []):
            errors.append(f"parameters.{path}.value must be one of {spec.get('values', [])}")
    elif kind == "number_pair":
        if not isinstance(value, list) or len(value) != 2 or not all(_is_number(item) for item in value):
            errors.append(f"parameters.{path}.value must be a two-number list")
        elif not 0 < float(value[0]) < float(value[1]):
            errors.append(f"parameters.{path}.value must satisfy 0 < low < high")
    if "implemented_values" in spec and value not in spec["implemented_values"]:
        errors.append(f"parameters.{path}.value is valid in principle but not implemented by this pipeline version")


def parameter_value_errors(
    path: str,
    value: Any,
    spec: dict[str, Any],
    *,
    tr_seconds: Any | None = None,
) -> list[str]:
    """Validate one executable parameter without requiring a complete project."""
    errors: list[str] = []
    _validate_parameter_value(path, value, spec, errors)
    if (
        path == "denoising.bandpass_filter_hz"
        and isinstance(value, list)
        and len(value) == 2
        and _is_number(tr_seconds)
        and float(tr_seconds) > 0
        and all(_is_number(item) for item in value)
    ):
        nyquist = 1 / (2 * float(tr_seconds))
        if float(value[1]) >= nyquist:
            errors.append(
                f"parameters.{path} high cutoff must be below Nyquist ({nyquist:.6g} Hz)"
            )
    return errors


def _parameter_paths(value: dict[str, Any], prefix: str = "") -> list[str]:
    result: list[str] = []
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict) and "value" in child:
            result.append(path)
        elif isinstance(child, dict):
            result.extend(_parameter_paths(child, path))
        else:
            result.append(path)
    return result


def safe_identifier(value: Any) -> str:
    result = re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_")
    if not result:
        raise ValueError("Identifier must contain at least one alphanumeric character")
    return result


def execution_identifier(value: Any, max_length: int = 24) -> str:
    """Return a short stable identifier for MATLAB/SPM filesystem paths."""
    result = safe_identifier(value)
    if max_length < 10:
        raise ValueError("max_length must be at least 10")
    if len(result) <= max_length:
        return result
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8]
    prefix = result[: max_length - len(digest) - 1].rstrip("_")
    return f"{prefix}_{digest}"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
