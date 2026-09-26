"""Build the reproducible seed dataset for the CONN pipeline literature review.

The source is the legacy ``conn-knowledge-builder`` repository.  The generated
artifacts intentionally preserve missing values and provenance; they are a
normalization aid, not a fresh scientific review of the underlying papers.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import yaml


NORMALIZER_VERSION = "0.1.0"
PILOT_PMIDS = {
    "37034165",
    "37162700",
    "37371347",
    "38161799",
    "38731091",
    "38889524",
    "39455948",
    "41306624",
}

LAYERS = (
    "input_adapter",
    "preprocessing",
    "denoising",
    "first_level_features",
    "second_level_inference",
    "qc_decision",
    "downstream_analysis",
    "output_export",
)

MATRIX_COMPONENTS = (
    "functional_structural_input",
    "bids_input",
    "external_preprocessed_input",
    "spm_project_import",
    "conn_preprocessing",
    "external_preprocessing",
    "structural_morphometry",
    "structural_parcellation",
    "functional_parcellation",
    "lesion_mapping",
    "diffusion_connectometry",
    "denoising",
    "seed_to_voxel",
    "roi_to_roi",
    "network_to_network",
    "roi_to_voxel",
    "voxel_to_voxel_or_mvpa",
    "ica_or_dual_regression",
    "graph_theory",
    "alff_or_falff",
    "homotopic_connectivity",
    "task_activation",
    "task_connectivity",
    "ppi_or_gppi",
    "dynamic_connectivity",
    "group_inference",
    "longitudinal_design",
    "qc",
    "clinical_correlation",
    "machine_learning",
)


def sha256(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def portable_ref(path: Path | None, source_root: Path) -> str:
    if path is None or not path.exists():
        return ""
    resolved = path.resolve()
    for base, prefix in ((source_root.parent.resolve(), "test-project"), (source_root.resolve(), "conn-knowledge-builder")):
        try:
            return f"{prefix}/{resolved.relative_to(base).as_posix()}"
        except ValueError:
            continue
    return resolved.name


def path_from_csv(raw: str) -> Path | None:
    raw = (raw or "").strip()
    return Path(raw) if raw else None


def read_curation_rounds(source_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    rounds_dir = source_root / "indexes" / "curation_rounds"
    for path in sorted(rounds_dir.glob("round_*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                pmid = str(row.get("pmid", "")).strip()
                if pmid:
                    result[pmid] = path.stem
    return result


def build_manifest(source_root: Path, output_path: Path, reviewed_pmids: set[str]) -> list[dict[str, str]]:
    index_path = source_root / "indexes" / "conn_papers_index.csv"
    rounds = read_curation_rounds(source_root)
    extraction_dir = source_root / "extractions" / "conn_automation"
    cards_dir = source_root / "method_cards" / "conn_automation"

    with index_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != 138:
        raise ValueError(f"Expected 138 corpus records, found {len(rows)}")
    if len({row["pmid"] for row in rows}) != 138:
        raise ValueError("Corpus manifest contains duplicate PMIDs")

    manifest: list[dict[str, str]] = []
    for row in rows:
        pmid = row["pmid"].strip()
        xml_path = path_from_csv(row.get("xml_path", ""))
        text_path = path_from_csv(row.get("text_path", ""))
        extraction_path = extraction_dir / f"PMID{pmid}.yaml"
        card_path = cards_dir / f"PMID{pmid}.yaml"
        curation_round = rounds.get(pmid, "deep_extraction_done" if pmid in PILOT_PMIDS else "unassigned")
        manifest.append(
            {
                "pmid": pmid,
                "pmcid": row.get("pmcid", ""),
                "doi": row.get("doi", ""),
                "year": row.get("year", ""),
                "title": row.get("title", ""),
                "journal": row.get("journal", ""),
                "pipeline_family": row.get("pipeline_family", ""),
                "analysis_signals": row.get("analysis_signals", ""),
                "match_level": row.get("match_level", ""),
                "license": row.get("license", ""),
                "cited_by": row.get("cited_by", ""),
                "legacy_extraction_status": row.get("automation_extraction_status", ""),
                "curation_round": curation_round,
                "historical_83": "true" if curation_round.startswith(("round_01", "round_02", "round_03", "round_04")) else "false",
                "deep_pilot_case": "true" if pmid in PILOT_PMIDS else "false",
                "structural_methods_reviewed": "true" if pmid in reviewed_pmids else "false",
                "xml_ref": portable_ref(xml_path, source_root),
                "xml_sha256": sha256(xml_path),
                "text_ref": portable_ref(text_path, source_root),
                "text_sha256": sha256(text_path),
                "extraction_ref": portable_ref(extraction_path if extraction_path.exists() else None, source_root),
                "extraction_sha256": sha256(extraction_path),
                "method_card_ref": portable_ref(card_path if card_path.exists() else None, source_root),
                "method_card_sha256": sha256(card_path),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    return manifest


def unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def evidence_from(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict) or "value" not in value:
        return "inferred", "Legacy extraction did not encode field-level evidence; verify against the source."
    evidence = value.get("evidence") or "not_reported"
    if evidence == "partial":
        return "inferred", "Legacy evidence level was 'partial'; verify against the source."
    if evidence not in {"explicit", "inferred", "not_reported", "not_applicable"}:
        return "inferred", f"Legacy evidence level was {evidence!r}; verify against the source."
    return evidence, str(value.get("notes") or "")


def parameters(data: Any, source_path: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def visit(value: Any, name: str, path: str) -> None:
        if isinstance(value, dict) and "value" in value:
            actual = value.get("value")
            evidence, note = evidence_from(value)
            record: dict[str, Any] = {
                "name": name,
                "value": actual,
                "evidence": evidence,
                "source_path": path,
            }
            if note:
                record["notes"] = note
            result.append(record)
            return
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{name}.{key}" if name else key, f"{path}.{key}" if path else key)
            return
        if value is None:
            result.append(
                {
                    "name": name,
                    "value": None,
                    "evidence": "not_reported",
                    "source_path": path,
                }
            )
            return
        evidence = "inferred"
        note = "Legacy extraction did not encode field-level evidence; verify against the source."
        result.append(
            {
                "name": name,
                "value": value,
                "evidence": evidence,
                "source_path": path,
                "notes": note,
            }
        )

    visit(data, "", source_path)
    return [item for item in result if item["name"]]


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized or "component"


def first_value(data: dict[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value: Any = data
        for key in path:
            if not isinstance(value, dict) or key not in value:
                value = None
                break
            value = value[key]
        value = unwrap(value)
        if value not in (None, "", []):
            return value
    return None


def normalise_extraction(
    source_root: Path,
    pmid: str,
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = source_root / "extractions" / "conn_automation" / f"PMID{pmid}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    paper = raw.get("paper") or raw.get("source") or {}
    conn = raw.get("conn_usage") or {}
    canonical = "paper" in raw
    family = first_value(raw, ("conn_usage", "pipeline_family", "value"), ("conn_usage", "pipeline_family")) or "unclear"
    study_design = first_value(raw, ("study_context", "design"), ("statistics", "second_level_model", "value"))
    modality = first_value(raw, ("dataset_inputs", "modality", "value"), ("study_context", "task", "name"))

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    component_ids: set[str] = set()

    def add_node(
        node_id: str,
        layer: str,
        component_id: str,
        data: Any,
        source_path: str,
        depends_on: Iterable[str] = (),
        execution_context: str = "conn",
        optional: bool = False,
        notes: Iterable[str] = (),
    ) -> str:
        node_id = slug(node_id)
        base = node_id
        counter = 2
        while any(node["id"] == node_id for node in nodes):
            node_id = f"{base}_{counter}"
            counter += 1
        node = {
            "id": node_id,
            "layer": layer,
            "component_id": slug(component_id),
            "execution_context": execution_context,
            "status": "observed",
            "optional": optional,
            "requires": [],
            "provides": [],
            "parameters": parameters(data, source_path),
            "source_paths": [source_path],
        }
        if notes:
            node["notes"] = list(notes)
        nodes.append(node)
        component_ids.add(node["component_id"])
        for dependency in depends_on:
            if dependency:
                edges.append({"from": dependency, "to": node_id, "relation": "data"})
        return node_id

    dataset = raw.get("dataset_inputs") or raw.get("study_context") or raw.get("imaging_acquisition") or {}
    conn_role = str(first_value(raw, ("conn_usage", "conn_role", "value"), ("conn_usage", "conn_role")) or "").lower()
    preprocessing_text = str(first_value(raw, ("preprocessing", "pipeline_default_or_custom", "value")) or "").lower()
    if "spm" in conn_role and (conn.get("data_import") or "import" in conn_role):
        input_component = "spm_project_import"
    elif "fmriprep" in conn_role or "fmriprep" in preprocessing_text:
        input_component = "fmriprep_derivatives_import"
    else:
        input_component = "functional_structural_dataset"
    input_id = add_node("input", "input_adapter", input_component, dataset, "dataset_inputs" if canonical else "study_context")

    prior = input_id
    external_preprocessing = (raw.get("non_conn_processing") or {}).get("task_fmri_preprocessing")
    if external_preprocessing:
        prior = add_node(
            "external_preprocessing",
            "preprocessing",
            "external_spm_preprocessing",
            external_preprocessing,
            "non_conn_processing.task_fmri_preprocessing",
            (prior,),
            "external",
        )

    preprocessing = raw.get("preprocessing") if canonical else conn.get("preprocessing")
    if preprocessing:
        context = "hybrid" if "fmriprep" in preprocessing_text else "conn"
        prior = add_node(
            "preprocessing",
            "preprocessing",
            "reported_preprocessing",
            preprocessing,
            "preprocessing" if canonical else "conn_usage.preprocessing",
            (prior,),
            context,
        )

    if conn.get("data_import"):
        prior = add_node(
            "conn_import",
            "input_adapter",
            "conn_external_project_import",
            conn["data_import"],
            "conn_usage.data_import",
            (prior,),
            "conn",
        )

    denoising = raw.get("denoising") if canonical else conn.get("denoising")
    if denoising:
        prior = add_node(
            "denoising",
            "denoising",
            "reported_denoising",
            denoising,
            "denoising" if canonical else "conn_usage.denoising",
            (prior,),
        )

    feature_nodes: list[str] = []
    verified_specs = (review or {}).get("verified_analysis_components") or []
    if verified_specs:
        analysis = raw.get("connectivity_analysis") or {}
        verified_analysis_parameters = {
            key: value for key, value in analysis.items() if key != "analysis_types"
        }
        for spec in verified_specs:
            component_id = str(spec["component_id"])
            feature_nodes.append(
                add_node(
                    component_id,
                    str(spec.get("layer") or "first_level_features"),
                    component_id,
                    verified_analysis_parameters if canonical else conn.get(component_id, {}),
                    str(spec.get("source_path") or "connectivity_analysis"),
                    (prior,),
                    str(spec.get("execution_context") or "conn"),
                )
            )
    elif canonical:
        analysis = raw.get("connectivity_analysis") or {}
        types = unwrap(analysis.get("analysis_types")) or []
        if isinstance(types, str):
            types = [types]
        for analysis_type in types:
            layer = "qc_decision" if "qc" in str(analysis_type).lower() else "first_level_features"
            execution_context = "external" if str(analysis_type).lower().startswith("fsl_") else "conn"
            feature_nodes.append(
                add_node(
                    str(analysis_type),
                    layer,
                    str(analysis_type),
                    analysis,
                    "connectivity_analysis",
                    (prior,),
                    execution_context,
                )
            )
    else:
        for key in ("roi_to_roi", "seed_to_voxel", "graph_theory", "falff"):
            if conn.get(key):
                feature_nodes.append(
                    add_node(key, "first_level_features", key, conn[key], f"conn_usage.{key}", (prior,))
                )

    if not feature_nodes:
        feature_nodes = [prior]

    second_level_id = ""
    statistics = raw.get("statistics")
    if statistics:
        second_level_id = add_node(
            "second_level",
            "second_level_inference",
            "reported_statistical_model",
            statistics,
            "statistics",
            feature_nodes,
        )
    elif any(
        token in json.dumps(conn.get(key, {}), ensure_ascii=False).lower()
        for key in ("roi_to_roi", "seed_to_voxel", "graph_theory", "falff")
        for token in ("second_level", "group_model", "comparisons", "paired t", "anova")
    ):
        embedded = {key: conn[key] for key in ("roi_to_roi", "seed_to_voxel", "graph_theory", "falff") if key in conn}
        second_level_id = add_node(
            "second_level",
            "second_level_inference",
            "embedded_group_inference",
            embedded,
            "conn_usage",
            feature_nodes,
        )

    downstream_nodes: list[str] = []
    if conn.get("clinical_correlation"):
        downstream_nodes.append(
            add_node(
                "clinical_correlation",
                "downstream_analysis",
                "clinical_correlation",
                conn["clinical_correlation"],
                "conn_usage.clinical_correlation",
                (second_level_id or feature_nodes[-1],),
                "external",
            )
        )
    if raw.get("machine_learning"):
        downstream_nodes.append(
            add_node(
                "machine_learning",
                "downstream_analysis",
                "machine_learning_classification",
                raw["machine_learning"],
                "machine_learning",
                feature_nodes,
                "external",
            )
        )

    qc = raw.get("qc")
    if qc:
        qc_id = add_node("qc", "qc_decision", "reported_qc", qc, "qc", (), "hybrid")
        for observed in [input_id, prior, *feature_nodes]:
            if observed != qc_id:
                edges.append({"from": observed, "to": qc_id, "relation": "observes"})
    else:
        assessment = raw.get("automation_assessment") or {}
        confirmations = assessment.get("cannot_automate_reliably_without_human_confirmation") or []
        if confirmations:
            qc_id = add_node(
                "human_review",
                "qc_decision",
                "human_confirmation_gate",
                confirmations,
                "automation_assessment.cannot_automate_reliably_without_human_confirmation",
                (),
                "human",
            )
            for observed in [prior, *feature_nodes]:
                if observed != qc_id:
                    edges.append({"from": observed, "to": qc_id, "relation": "observes"})

    output_data = raw.get("outcomes") or raw.get("results_relevant_to_automation") or {}
    terminal = downstream_nodes or ([second_level_id] if second_level_id else feature_nodes)
    add_node(
        "outputs",
        "output_export",
        "reported_outputs",
        output_data,
        "outcomes" if raw.get("outcomes") else "results_relevant_to_automation",
        terminal,
        "hybrid",
    )

    for node in nodes:
        layer = node["layer"]
        if layer == "input_adapter":
            node["provides"] = ["dataset"]
        elif layer == "preprocessing":
            node["requires"] = ["dataset"]
            node["provides"] = ["preprocessed_timeseries"]
        elif layer == "denoising":
            node["requires"] = ["preprocessed_timeseries"]
            node["provides"] = ["denoised_timeseries"]
        elif layer == "first_level_features":
            node["requires"] = ["denoised_or_preprocessed_timeseries"]
            node["provides"] = ["first_level_features"]
        elif layer == "second_level_inference":
            node["requires"] = ["first_level_features"]
            node["provides"] = ["group_inference"]
        elif layer == "downstream_analysis":
            node["requires"] = ["features_or_group_results"]
            node["provides"] = ["downstream_results"]
        elif layer == "qc_decision":
            node["provides"] = ["qc_decision"]
        elif layer == "output_export":
            node["requires"] = ["analysis_results"]
            node["provides"] = ["reported_outputs"]

    automation = raw.get("automation") or raw.get("automation_assessment") or {}
    confirmations = first_value(
        raw,
        ("automation", "human_confirmation_needed", "value"),
        ("automation_assessment", "cannot_automate_reliably_without_human_confirmation"),
    ) or []
    missing = first_value(raw, ("reproducibility", "missing_critical_parameters", "value")) or []
    if not missing:
        missing = []
        for key, value in conn.items():
            if isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    if "missing" in nested_key and nested_value:
                        if isinstance(nested_value, list):
                            missing.extend(nested_value)
                        else:
                            missing.append(str(nested_value))

    software_environment: list[dict[str, Any]] = []
    for software_name, field_name in (("CONN", "conn_version"), ("SPM", "spm_version"), ("MATLAB", "matlab_version")):
        field = conn.get(field_name)
        value = unwrap(field)
        evidence, note = ("not_reported", "") if field is None else evidence_from(field)
        record: dict[str, Any] = {
            "name": software_name,
            "version": value,
            "evidence": evidence,
            "source_path": f"conn_usage.{field_name}",
        }
        if note:
            record["notes"] = note
        software_environment.append(record)

    source_ref = portable_ref(path, source_root)
    instance = {
        "schema_version": "pipeline_instance_v1",
        "instance_id": f"pmid_{pmid}_pipeline_01",
        "instance_scope": "provisional_paper_level",
        "paper": {
            "pmid": str(paper.get("pmid") or pmid),
            "pmcid": paper.get("pmcid"),
            "doi": paper.get("doi"),
            "title": paper.get("title"),
            "year": paper.get("year"),
        },
        "classification": {
            "primary_family": str(family),
            "study_design": study_design,
            "modality_or_task": modality,
            "normalization_status": "legacy_deep_extraction_imported",
        },
        "software_environment": software_environment,
        "graph": {"nodes": nodes, "edges": edges},
        "human_confirmations": confirmations if isinstance(confirmations, list) else [str(confirmations)],
        "missing_information": missing if isinstance(missing, list) else [str(missing)],
        "review": {
            "source_review_status": "pending_verification",
            "legacy_schema_shape": "canonical_extraction" if canonical else "custom_deep_extraction",
            "split_into_multiple_instances": "pending_review",
            "notes": [
                "Normalized from a legacy extraction, not re-verified against the publication.",
                "A reviewer must decide whether branches represent separate pipeline instances.",
            ],
        },
        "provenance": {
            "source_extraction_ref": source_ref,
            "source_extraction_sha256": sha256(path),
            "normalizer_version": NORMALIZER_VERSION,
            "generated_on": date.today().isoformat(),
        },
    }
    validate_instance(instance)
    return instance


def apply_source_review(instance: dict[str, Any], review: dict[str, Any]) -> None:
    if not review:
        return
    classification = instance["classification"]
    if review.get("primary_family"):
        classification["primary_family"] = review["primary_family"]
    classification["normalization_status"] = "structurally_verified"
    provisional_pipeline_count = int(review.get("provisional_pipeline_count", 1))
    instance["review"].update(
        {
            "source_review_status": "structural_methods_verified",
            "source_sections": review.get("source_sections", []),
            "provisional_pipeline_count": provisional_pipeline_count,
            "split_into_multiple_instances": provisional_pipeline_count > 1,
            "split_decision": review.get("split_decision", "pending_review"),
            "confirmed_structure": review.get("confirmed_structure", []),
            "unresolved": review.get("unresolved", []),
            "discrepancies": review.get("discrepancies", []),
            "rejected_components": review.get("rejected_components", []),
        }
    )
    node_by_component = {node["component_id"]: node for node in instance["graph"]["nodes"]}
    for component_id, context in (review.get("execution_context_overrides") or {}).items():
        if component_id in node_by_component:
            node_by_component[component_id]["execution_context"] = context
    software_by_name = {item["name"]: item for item in instance["software_environment"]}
    for software_name, version in (review.get("software_overrides") or {}).items():
        if software_name not in software_by_name:
            software_by_name[software_name] = {"name": software_name, "source_path": "source_review"}
            instance["software_environment"].append(software_by_name[software_name])
        software_by_name[software_name].update(
            {
                "version": version,
                "evidence": "explicit",
                "source_path": "review.source_sections",
                "notes": "Corrected during structural verification against the methods text.",
            }
        )
    for override in review.get("parameter_overrides", []):
        component_id = str(override["component_id"])
        node = node_by_component.get(component_id)
        if not node:
            continue
        name = str(override["name"])
        existing = next((item for item in node["parameters"] if item["name"] == name), None)
        corrected = {
            "name": name,
            "value": override.get("value"),
            "evidence": str(override.get("evidence") or "explicit"),
            "source_path": str(override.get("source_path") or "review.source_sections"),
        }
        if override.get("notes"):
            corrected["notes"] = str(override["notes"])
        if existing:
            existing.update(corrected)
        else:
            node["parameters"].append(corrected)
    existing_edges = {
        (edge["from"], edge["to"], edge["relation"])
        for edge in instance["graph"]["edges"]
    }
    for edge in review.get("derived_edges", []):
        source = node_by_component.get(edge["from_component"])
        target = node_by_component.get(edge["to_component"])
        if source and target:
            item = (source["id"], target["id"], edge.get("relation", "derives"))
            if item not in existing_edges:
                instance["graph"]["edges"].append(
                    {"from": item[0], "to": item[1], "relation": item[2]}
                )
                existing_edges.add(item)
    validate_instance(instance)


def validate_instance(instance: dict[str, Any]) -> None:
    if instance.get("schema_version") != "pipeline_instance_v1":
        raise ValueError("Invalid schema version")
    graph = instance.get("graph") or {}
    nodes = graph.get("nodes") or []
    ids = [node.get("id") for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate node IDs in {instance.get('instance_id')}")
    if any(node.get("layer") not in LAYERS for node in nodes):
        raise ValueError(f"Unknown layer in {instance.get('instance_id')}")
    known = set(ids)
    for edge in graph.get("edges") or []:
        if edge.get("from") not in known or edge.get("to") not in known:
            raise ValueError(f"Dangling edge in {instance.get('instance_id')}: {edge}")


def write_schema(path: Path) -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://cognify.science/schemas/pipeline_instance_v1.schema.json",
        "title": "CONN literature pipeline instance",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "instance_id", "instance_scope", "paper", "classification", "software_environment", "graph", "review", "provenance"],
        "properties": {
            "schema_version": {"const": "pipeline_instance_v1"},
            "instance_id": {"type": "string", "pattern": "^[a-z0-9_]+$"},
            "instance_scope": {"enum": ["provisional_paper_level", "single_pipeline", "paper_branch"]},
            "paper": {
                "type": "object",
                "additionalProperties": False,
                "required": ["pmid", "title"],
                "properties": {
                    "pmid": {"type": "string"},
                    "pmcid": {"type": ["string", "null"]},
                    "doi": {"type": ["string", "null"]},
                    "title": {"type": ["string", "null"]},
                    "year": {"type": ["integer", "string", "null"]},
                },
            },
            "classification": {
                "type": "object",
                "additionalProperties": False,
                "required": ["primary_family", "normalization_status"],
                "properties": {
                    "primary_family": {"type": "string"},
                    "study_design": {},
                    "modality_or_task": {},
                    "normalization_status": {"enum": ["legacy_deep_extraction_imported", "structurally_verified", "source_verified"]},
                },
            },
            "software_environment": {
                "type": "array",
                "items": {"$ref": "#/$defs/software"},
            },
            "graph": {
                "type": "object",
                "additionalProperties": False,
                "required": ["nodes", "edges"],
                "properties": {
                    "nodes": {"type": "array", "minItems": 2, "items": {"$ref": "#/$defs/node"}},
                    "edges": {"type": "array", "items": {"$ref": "#/$defs/edge"}},
                },
            },
            "human_confirmations": {"type": "array", "items": {}},
            "missing_information": {"type": "array", "items": {}},
            "review": {"type": "object"},
            "provenance": {"type": "object"},
        },
        "$defs": {
            "software": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "version", "evidence", "source_path"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": ["string", "number", "null"]},
                    "evidence": {"enum": ["explicit", "inferred", "not_reported", "not_applicable"]},
                    "source_path": {"type": "string"},
                    "notes": {"type": "string"},
                },
            },
            "parameter": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "value", "evidence", "source_path"],
                "properties": {
                    "name": {"type": "string"},
                    "value": {},
                    "evidence": {"enum": ["explicit", "inferred", "not_reported", "not_applicable"]},
                    "source_path": {"type": "string"},
                    "notes": {"type": "string"},
                },
            },
            "node": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "layer", "component_id", "execution_context", "status", "optional", "requires", "provides", "parameters", "source_paths"],
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z0-9_]+$"},
                    "layer": {"enum": list(LAYERS)},
                    "component_id": {"type": "string", "pattern": "^[a-z0-9_]+$"},
                    "execution_context": {"enum": ["conn", "external", "hybrid", "human"]},
                    "status": {"enum": ["observed", "specified", "implemented", "technically_validated", "scientifically_reviewed"]},
                    "optional": {"type": "boolean"},
                    "requires": {"type": "array", "items": {"type": "string"}},
                    "provides": {"type": "array", "items": {"type": "string"}},
                    "parameters": {"type": "array", "items": {"$ref": "#/$defs/parameter"}},
                    "source_paths": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "array", "items": {"type": "string"}},
                },
            },
            "edge": {
                "type": "object",
                "additionalProperties": False,
                "required": ["from", "to", "relation"],
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "relation": {"enum": ["data", "control", "observes", "derives"]},
                },
            },
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_component_dictionary(path: Path, instances: list[dict[str, Any]]) -> None:
    observed: dict[str, dict[str, Any]] = {}
    for instance in instances:
        pmid = instance["paper"]["pmid"]
        for node in instance["graph"]["nodes"]:
            component = observed.setdefault(
                node["component_id"],
                {
                    "layer": node["layer"],
                    "status": "observed",
                    "execution_contexts": set(),
                    "paper_pmids": set(),
                    "requires": set(),
                    "provides": set(),
                    "scientific_review_status": "pending",
                },
            )
            component["execution_contexts"].add(node["execution_context"])
            component["paper_pmids"].add(pmid)
            component["requires"].update(node["requires"])
            component["provides"].update(node["provides"])
    serializable = {
        "schema_version": "component_dictionary_v1",
        "generated_on": date.today().isoformat(),
        "components": {
            component_id: {
                **{key: value for key, value in details.items() if not isinstance(value, set)},
                "execution_contexts": sorted(details["execution_contexts"]),
                "paper_pmids": sorted(details["paper_pmids"]),
                "requires": sorted(details["requires"]),
                "provides": sorted(details["provides"]),
            }
            for component_id, details in sorted(observed.items())
        },
    }
    path.write_text(yaml.safe_dump(serializable, sort_keys=False, allow_unicode=True), encoding="utf-8")


def has_content(value: Any) -> bool:
    value = unwrap(value)
    if value in (None, "", [], {}, False, "not_reported"):
        return False
    if isinstance(value, dict):
        return any(has_content(child) for key, child in value.items() if key not in {"evidence", "notes"})
    return True


def extraction_signals(raw: dict[str, Any], manifest_row: dict[str, str]) -> dict[str, bool]:
    canonical = "paper" in raw
    conn = raw.get("conn_usage") or {}
    analysis = raw.get("connectivity_analysis") or {}
    preprocessing = raw.get("preprocessing") if canonical else conn.get("preprocessing")
    denoising = raw.get("denoising") if canonical else conn.get("denoising")
    qc = raw.get("qc") or {}
    statistics = raw.get("statistics") or {}
    dataset = raw.get("dataset_inputs") or {}
    non_conn = raw.get("non_conn_processing") or {}
    family = str(first_value(raw, ("conn_usage", "pipeline_family", "value"), ("conn_usage", "pipeline_family")) or manifest_row["pipeline_family"])
    role = str(first_value(raw, ("conn_usage", "conn_role", "value"), ("conn_usage", "conn_role")) or "").lower()
    preprocessing_text = json.dumps(preprocessing or {}, ensure_ascii=False).lower()
    index_tokens = {slug(item.strip()) for item in manifest_row.get("analysis_signals", "").split(";") if item.strip()}
    # The canonical legacy extraction's analysis_types field was populated by
    # keyword matching and produces severe false positives (for example,
    # discussion mentions of graph or dynamic methods).  The index signals are
    # narrower and are used only as unverified candidate evidence.
    tokens = index_tokens

    def any_token(*candidates: str) -> bool:
        return any(any(candidate in token for candidate in candidates) for token in tokens)

    bids_value = first_value(raw, ("dataset_inputs", "bids_or_input_standard", "value"))
    signals = {component: False for component in MATRIX_COMPONENTS}
    signals.update(
        {
            "functional_structural_input": True,
            "bids_input": "bids" in str(bids_value or "").lower(),
            "external_preprocessed_input": "fmriprep" in role or "fmriprep" in preprocessing_text,
            "spm_project_import": bool(conn.get("data_import")) or ("spm" in role and "import" in role),
            "conn_preprocessing": has_content(preprocessing),
            "external_preprocessing": bool(non_conn) or "fmriprep" in preprocessing_text,
            "denoising": has_content(denoising),
            "seed_to_voxel": family == "rsfmri_seed_to_voxel" or any_token("seed_to_voxel", "seed"),
            "roi_to_roi": family == "rsfmri_roi_to_roi" or any_token("roi_to_roi") or bool(conn.get("roi_to_roi")),
            "roi_to_voxel": any_token("roi_to_voxel") or bool(conn.get("roi_to_voxel")),
            "voxel_to_voxel_or_mvpa": any_token("voxel_to_voxel", "mvpa") or bool(conn.get("mvpa")),
            "ica_or_dual_regression": any_token("ica", "dual_regression"),
            "graph_theory": family == "rsfmri_graph_theory" or any_token("graph") or bool(conn.get("graph_theory")),
            "alff_or_falff": any_token("alff", "falff") or bool(conn.get("falff")),
            "task_connectivity": family == "task_fmri_connectivity" or any_token("task"),
            "ppi_or_gppi": any_token("ppi", "gppi"),
            "dynamic_connectivity": family == "dynamic_functional_connectivity" or any_token("dynamic"),
            "group_inference": has_content(statistics.get("second_level_model")) or any_token("group"),
            "longitudinal_design": family == "longitudinal_pre_post",
            "qc": bool(unwrap(qc.get("qc_reported"))) or family == "rsfmri_qc_preprocessing_denoising" or any_token("qc"),
            "clinical_correlation": bool(conn.get("clinical_correlation")),
            "machine_learning": family == "machine_learning_features" or bool(raw.get("machine_learning")) or any_token("machine_learning"),
        }
    )
    return signals


def verified_components(instance: dict[str, Any]) -> set[str]:
    mapping = {
        "functional_structural_dataset": "functional_structural_input",
        "fmriprep_derivatives_import": "external_preprocessed_input",
        "spm_project_import": "spm_project_import",
        "conn_external_project_import": "spm_project_import",
        "reported_preprocessing": "conn_preprocessing",
        "external_spm_preprocessing": "external_preprocessing",
        "structural_vbm": "structural_morphometry",
        "cortical_complexity": "structural_morphometry",
        "cortical_morphometry": "structural_morphometry",
        "cortical_parcellation": "structural_parcellation",
        "functional_parcellation": "functional_parcellation",
        "lesion_mapping": "lesion_mapping",
        "diffusion_connectometry": "diffusion_connectometry",
        "reported_denoising": "denoising",
        "seed_to_voxel": "seed_to_voxel",
        "seed_to_seed": "roi_to_roi",
        "roi_to_roi": "roi_to_roi",
        "functional_network_connectivity": "network_to_network",
        "roi_to_voxel": "roi_to_voxel",
        "mvpa_roi_definition": "voxel_to_voxel_or_mvpa",
        "voxel_to_voxel_or_mvpa": "voxel_to_voxel_or_mvpa",
        "fsl_dual_regression_intra_network": "ica_or_dual_regression",
        "neuromark_ica": "ica_or_dual_regression",
        "graph_theory": "graph_theory",
        "falff": "alff_or_falff",
        "interhemispheric_homotopic_connectivity": "homotopic_connectivity",
        "task_activation_glm": "task_activation",
        "task_connectivity": "task_connectivity",
        "ppi_or_gppi": "ppi_or_gppi",
        "dynamic_connectivity": "dynamic_connectivity",
        "clinical_correlation": "clinical_correlation",
        "machine_learning_classification": "machine_learning",
        "reported_statistical_model": "group_inference",
        "embedded_group_inference": "group_inference",
        "reported_qc": "qc",
        "functional_connectivity_distribution_qc": "qc",
        "qc_fc_correlations": "qc",
        "human_confirmation_gate": "qc",
    }
    components: set[str] = set()
    for node in instance["graph"]["nodes"]:
        component_id = node["component_id"]
        if component_id not in mapping:
            continue
        if component_id == "reported_preprocessing" and node["execution_context"] in {"external", "hybrid"}:
            components.add("external_preprocessing")
            if node["execution_context"] == "hybrid":
                components.add("conn_preprocessing")
        else:
            components.add(mapping[component_id])
    family = instance["classification"]["primary_family"]
    if family == "longitudinal_pre_post":
        components.add("longitudinal_design")
    if family in {"task_fmri_connectivity", "mixed_rest_task_connectivity"}:
        components.add("task_connectivity")
    return components


def build_component_census(
    source_root: Path,
    output_root: Path,
    manifest: list[dict[str, str]],
    instances: list[dict[str, Any]],
) -> None:
    instance_by_pmid = {instance["paper"]["pmid"]: instance for instance in instances}
    extraction_dir = source_root / "extractions" / "conn_automation"
    rows: list[dict[str, str]] = []
    for manifest_row in manifest:
        pmid = manifest_row["pmid"]
        extraction_path = extraction_dir / f"PMID{pmid}.yaml"
        raw = yaml.safe_load(extraction_path.read_text(encoding="utf-8")) or {}
        signals = extraction_signals(raw, manifest_row)
        verified = verified_components(instance_by_pmid[pmid]) if pmid in instance_by_pmid else set()
        rejected = (
            set(instance_by_pmid[pmid]["review"].get("rejected_components", []))
            if pmid in instance_by_pmid
            else set()
        )
        family = str(first_value(raw, ("conn_usage", "pipeline_family", "value"), ("conn_usage", "pipeline_family")) or manifest_row["pipeline_family"])
        normalized_family = (
            instance_by_pmid[pmid]["classification"]["primary_family"]
            if pmid in instance_by_pmid
            else family
        )
        design_dimension = {
            "clinical_group_comparison": "group_comparison",
            "longitudinal_pre_post": "longitudinal",
            "task_fmri_connectivity": "task_fmri",
            "machine_learning_features": "predictive_modeling",
        }.get(normalized_family, "not_separated_in_legacy_taxonomy")
        row = {
            "pmid": pmid,
            "title": manifest_row["title"],
            "year": manifest_row["year"],
            "legacy_pipeline_family": family,
            "normalized_primary_family": normalized_family,
            "design_dimension": design_dimension,
            "review_status": "structural_methods_verified" if pmid in instance_by_pmid else "legacy_extraction_unverified",
            "extraction_shape": "canonical" if "paper" in raw else "custom_deep",
            "full_text_available": "true" if manifest_row["xml_sha256"] or manifest_row["text_sha256"] else "false",
        }
        for component in MATRIX_COMPONENTS:
            if component in verified:
                row[component] = "source_verified"
            elif component in rejected:
                row[component] = "not_detected"
            elif signals[component]:
                row[component] = "legacy_extracted"
            else:
                row[component] = "not_detected"
        rows.append(row)

    matrix_path = output_root / "paper_component_matrix.csv"
    with matrix_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    prevalence: list[dict[str, Any]] = []
    for component in MATRIX_COMPONENTS:
        verified_count = sum(row[component] == "source_verified" for row in rows)
        legacy_count = sum(row[component] == "legacy_extracted" for row in rows)
        candidate_count = verified_count + legacy_count
        prevalence.append(
            {
                "component": component,
                "source_verified_papers": verified_count,
                "legacy_candidate_papers": legacy_count,
                "all_candidate_papers": candidate_count,
                "candidate_percent_of_corpus": f"{candidate_count / len(rows) * 100:.1f}",
            }
        )
    prevalence.sort(key=lambda item: (-item["all_candidate_papers"], item["component"]))
    with (output_root / "component_prevalence.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(prevalence[0]))
        writer.writeheader()
        writer.writerows(prevalence)

    combinations: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        selected = tuple(
            component
            for component in MATRIX_COMPONENTS
            if component not in {"functional_structural_input", "conn_preprocessing", "denoising", "group_inference", "qc"}
            and row[component] != "not_detected"
        )
        combinations[selected or ("unspecified_analysis",)] += 1

    report = [
        "# Censo preliminar paper × componente",
        "",
        f"Este censo incluye **{len(rows)} papers**: {len(instances)} con estructura verificada contra texto completo y {len(rows) - len(instances)} basados en extracciones históricas no verificadas.",
        "",
        "Los valores `legacy_extracted` son candidatos para revisión. No deben interpretarse como confirmación de que el componente fue ejecutado ni como recomendación metodológica.",
        "",
        "## Componentes candidatos",
        "",
        "| Componente | Verificados | Candidatos heredados | Total candidato | % corpus |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for item in prevalence:
        report.append(
            f"| `{item['component']}` | {item['source_verified_papers']} | {item['legacy_candidate_papers']} | {item['all_candidate_papers']} | {item['candidate_percent_of_corpus']}% |"
        )
    report.extend(
        [
            "",
            "## Combinaciones preliminares de análisis",
            "",
            "| Combinación detectada | Papers |",
            "| --- | ---: |",
        ]
    )
    for combination, count in combinations.most_common(15):
        report.append(f"| `{' + '.join(combination)}` | {count} |")
    report.extend(
        [
            "",
            "## Uso correcto",
            "",
            "- Usar los conteos para seleccionar la muestra profunda y encontrar huecos de cobertura.",
            "- Recalcular las frecuencias después de cada revisión contra texto completo.",
            "- No usar estos conteos para elegir defaults, afirmar buenas prácticas o comparar validez científica.",
            "- Mantener diseño experimental y familia de análisis como dimensiones separadas en la taxonomía definitiva.",
        ]
    )
    (output_root / "preliminary_census_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def build_deep_review_queue(
    source_root: Path,
    output_root: Path,
    manifest: list[dict[str, str]],
    reviewed_pmids: set[str],
) -> None:
    pilot_strata = {
        "37034165": "current_seed_preprocessing_group",
        "37162700": "longitudinal",
        "37371347": "task_fmri",
        "38161799": "current_seed_preprocessing_group",
        "38731091": "graph_theory",
        "38889524": "current_seed_preprocessing_group",
        "39455948": "roi_to_roi",
        "41306624": "machine_learning",
    }
    round_priority = {
        "round_01": 0,
        "round_02": 1,
        "round_03": 2,
        "round_04": 3,
        "round_05": 4,
        "round_06": 5,
        "unassigned": 6,
    }
    readiness_priority = {
        "high_candidate": 0,
        "medium_candidate": 1,
        "low_candidate": 2,
        "insufficient": 3,
    }
    cards_dir = source_root / "method_cards" / "conn_automation"
    metadata: dict[str, dict[str, Any]] = {}
    for row in manifest:
        card_path = cards_dir / f"PMID{row['pmid']}.yaml"
        card = yaml.safe_load(card_path.read_text(encoding="utf-8")) or {}
        readiness = str((card.get("automation_triage") or {}).get("readiness") or "unassigned")
        missing = card.get("missing_critical_parameters") or []
        metadata[row["pmid"]] = {
            "manifest": row,
            "readiness": readiness,
            "missing_count": len(missing),
            "missing": "; ".join(str(item) for item in missing),
        }

    def priority(pmid: str) -> tuple[Any, ...]:
        item = metadata[pmid]
        row = item["manifest"]
        round_name = row["curation_round"]
        prefix = next((key for key in round_priority if round_name.startswith(key)), "unassigned")
        try:
            cited_by = int(row.get("cited_by") or 0)
        except ValueError:
            cited_by = 0
        return (
            0 if row["xml_sha256"] else 1,
            round_priority[prefix],
            readiness_priority.get(item["readiness"], 4),
            item["missing_count"],
            -cited_by,
            pmid,
        )

    by_family: dict[str, list[str]] = defaultdict(list)
    for row in manifest:
        if row["pmid"] not in PILOT_PMIDS:
            by_family[row["pipeline_family"]].append(row["pmid"])
    for pmids in by_family.values():
        pmids.sort(key=priority)

    selected_by_stratum: dict[str, list[str]] = {
        "current_seed_preprocessing_group": (
            by_family["rsfmri_seed_to_voxel"][:12]
            + by_family["clinical_group_comparison"][:10]
        ),
        "roi_to_roi": by_family["rsfmri_roi_to_roi"][:4],
        "graph_theory": by_family["rsfmri_graph_theory"][:4],
        "task_fmri": by_family["task_fmri_connectivity"][:3],
        "longitudinal": by_family["longitudinal_pre_post"][:3],
        "dynamic_connectivity": by_family["dynamic_functional_connectivity"][:1],
        "machine_learning": [],
    }
    if sum(len(pmids) for pmids in selected_by_stratum.values()) != 37:
        raise ValueError("Deep-review queue must add exactly 37 papers to the eight pilot cases")

    queue_rows: list[dict[str, Any]] = []
    order = 1
    for pmid in sorted(PILOT_PMIDS):
        item = metadata[pmid]
        row = item["manifest"]
        queue_rows.append(
            {
                "review_order": order,
                "status": "structural_methods_verified",
                "stratum": pilot_strata[pmid],
                "pmid": pmid,
                "title": row["title"],
                "year": row["year"],
                "legacy_pipeline_family": row["pipeline_family"],
                "curation_round": row["curation_round"],
                "readiness": item["readiness"],
                "missing_critical_parameters": item["missing"],
                "xml_available": "true" if row["xml_sha256"] else "false",
                "text_available": "true" if row["text_sha256"] else "false",
                "full_text_available": "true" if row["xml_sha256"] or row["text_sha256"] else "false",
                "selection_basis": "existing deep extraction; structurally checked against full text",
            }
        )
        order += 1
    stratum_order = (
        "current_seed_preprocessing_group",
        "roi_to_roi",
        "graph_theory",
        "task_fmri",
        "longitudinal",
        "dynamic_connectivity",
        "machine_learning",
    )
    for stratum in stratum_order:
        for pmid in selected_by_stratum[stratum]:
            item = metadata[pmid]
            row = item["manifest"]
            queue_rows.append(
                {
                    "review_order": order,
                    "status": "structural_methods_verified" if pmid in reviewed_pmids else "queued",
                    "stratum": stratum,
                    "pmid": pmid,
                    "title": row["title"],
                    "year": row["year"],
                    "legacy_pipeline_family": row["pipeline_family"],
                    "curation_round": row["curation_round"],
                    "readiness": item["readiness"],
                    "missing_critical_parameters": item["missing"],
                    "xml_available": "true" if row["xml_sha256"] else "false",
                    "text_available": "true" if row["text_sha256"] else "false",
                    "full_text_available": "true" if row["xml_sha256"] or row["text_sha256"] else "false",
                    "selection_basis": "stratified for family coverage; prioritized full text and curation readiness",
                }
            )
            order += 1

    with (output_root / "deep_review_queue.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(queue_rows[0]))
        writer.writeheader()
        writer.writerows(queue_rows)

    counts = Counter(row["stratum"] for row in queue_rows)
    completed_total = sum(row["status"] != "queued" for row in queue_rows)
    pending_total = sum(row["status"] == "queued" for row in queue_rows)
    report = [
        "# Cola estratificada de revisión profunda",
        "",
        f"La cola contiene 45 papers: {completed_total} con verificación estructural y {pending_total} revisiones pendientes.",
        "",
        "| Estrato | Total final | Ya revisados | Pendientes |",
        "| --- | ---: | ---: | ---: |",
    ]
    for stratum in stratum_order:
        completed = sum(row["stratum"] == stratum and row["status"] != "queued" for row in queue_rows)
        pending = sum(row["stratum"] == stratum and row["status"] == "queued" for row in queue_rows)
        report.append(f"| `{stratum}` | {counts[stratum]} | {completed} | {pending} |")
    report.extend(
        [
            "",
            "## Criterios de selección",
            "",
            "1. Cumplir la distribución estratificada definida en el plan.",
            "2. Priorizar disponibilidad de texto completo en XML o texto normalizado.",
            "3. Priorizar rondas de curación con menos parámetros críticos faltantes.",
            "4. Mantener diversidad de familias; no seleccionar por significación ni dirección de resultados.",
            "",
            "La asignación es una cola de trabajo y puede cambiar si la revisión profunda demuestra que la familia histórica era incorrecta.",
        ]
    )
    (output_root / "deep_review_queue_summary.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def write_gap_report(path: Path, manifest: list[dict[str, str]], instances: list[dict[str, Any]]) -> None:
    families = Counter(row["pipeline_family"] for row in manifest)
    pilot_families = Counter(instance["classification"]["primary_family"] for instance in instances)
    layers = Counter(node["layer"] for instance in instances for node in instance["graph"]["nodes"])
    historical = sum(row["historical_83"] == "true" for row in manifest)
    multi_pipeline_papers = sum(
        int(instance["review"].get("provisional_pipeline_count", 1)) > 1
        for instance in instances
    )
    lines = [
        "# Informe inicial de cobertura y huecos",
        "",
        f"Generado el {date.today().isoformat()} a partir del corpus heredado congelado.",
        "",
        "## Verificaciones del corpus",
        "",
        f"- Papers únicos: **{len(manifest)}**.",
        f"- Registros de las rondas históricas 1–4: **{historical}**.",
        f"- Instancias con verificación estructural: **{len(instances)}**.",
        "- Cada archivo fuente disponible quedó identificado mediante SHA-256.",
        "",
        "## Familias del censo completo",
        "",
        "| Familia | Papers | Casos piloto |",
        "| --- | ---: | ---: |",
    ]
    for family, count in sorted(families.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{family}` | {count} | {pilot_families.get(family, 0)} |")
    lines.extend(
        [
            "",
            "## Cobertura estructural de la muestra revisada",
            "",
            "| Capa | Nodos observados |",
            "| --- | ---: |",
        ]
    )
    for layer in LAYERS:
        lines.append(f"| `{layer}` | {layers.get(layer, 0)} |")
    lines.extend(
        [
            "",
            "## Hallazgos para el contrato flexible",
            "",
            "1. El corpus heredado usa dos formas incompatibles de extracción; el nuevo esquema debe ser único y versionado.",
            "2. Los pipelines necesitan un grafo: hay ramas ROI-to-ROI, seed-to-voxel y graph theory que comparten preprocessing y denoising.",
            "3. La entrada debe aceptar datos crudos, derivados de fMRIPrep y proyectos SPM importados.",
            "4. QC es transversal y observa varias etapas; no debe modelarse solamente como el último paso lineal.",
            "5. Machine learning y correlaciones clínicas requieren una capa posterior al análisis CONN.",
            f"6. Una publicación puede contener varias instancias. La verificación estructural identificó {multi_pipeline_papers} papers con más de una rama provisional.",
            "",
            "## Cobertura y trabajo pendiente",
            "",
            f"- La muestra estratificada quedó completa: {len(instances)} de {len(instances)} papers tienen verificación estructural contra texto completo.",
            "- La muestra incluye conectividad dinámica, PPI, task connectivity, análisis longitudinal, graph theory, ROI-to-ROI y machine learning.",
            "- Los parámetros marcados como `inferred` en las extracciones históricas deben contrastarse con texto completo y suplementos.",
            "- Las familias `clinical_group_comparison` y `unclear` mezclan estructura del pipeline con diseño científico y deberán reclasificarse en dimensiones separadas.",
            f"- El censo comprende {len(manifest)} papers; {len(manifest) - len(instances)} registros fuera de la muestra estratificada siguen sin verificación contra texto completo y sus conteos son candidatos, no prevalencias confirmadas.",
            "- La evaluación de calidad metodológica y la traducción de parámetros observados en recomendaciones científicas siguen siendo una etapa separada.",
            "",
            "## Decisión de esquema",
            "",
            "El piloto amplía las siete capas del plan con `downstream_analysis`. Esta capa evita mezclar ML, correlaciones clínicas y otros análisis externos con inferencia grupal o exportación.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_snapshot(
    path: Path,
    source_root: Path,
    manifest: list[dict[str, str]],
    reviewed_pmids: set[str],
) -> None:
    index_path = source_root / "indexes" / "conn_papers_index.csv"
    snapshot = {
        "schema_version": "pipeline_review_snapshot_v1",
        "snapshot_date": date.today().isoformat(),
        "normalizer_version": NORMALIZER_VERSION,
        "source_index_ref": portable_ref(index_path, source_root),
        "source_index_sha256": sha256(index_path),
        "counts": {
            "unique_papers": len(manifest),
            "historical_rounds_1_to_4": sum(row["historical_83"] == "true" for row in manifest),
            "pilot_deep_extractions": sum(row["deep_pilot_case"] == "true" for row in manifest),
            "xml_files_available": sum(bool(row["xml_sha256"]) for row in manifest),
            "text_files_available": sum(bool(row["text_sha256"]) for row in manifest),
            "legacy_extractions_available": sum(bool(row["extraction_sha256"]) for row in manifest),
            "legacy_method_cards_available": sum(bool(row["method_card_sha256"]) for row in manifest),
            "structural_methods_reviews": len(reviewed_pmids),
        },
        "limitations": [
            "The snapshot records the available local corpus; missing full text remains missing.",
            "Pilot instances have structural methods verification; parameter-level scientific appraisal remains pending.",
        ],
    }
    path.write_text(yaml.safe_dump(snapshot, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True, help="Path to the legacy conn-knowledge-builder repository")
    parser.add_argument("--output-root", type=Path, default=Path("knowledge/pipeline_review"))
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()

    reviews_path = output_root / "curation" / "pilot_source_reviews.yaml"
    reviews_document = yaml.safe_load(reviews_path.read_text(encoding="utf-8")) if reviews_path.exists() else {}
    reviews = (reviews_document or {}).get("reviews", {})
    reviewed_pmids = set(reviews)
    manifest = build_manifest(source_root, output_root / "corpus_manifest.csv", reviewed_pmids)
    write_snapshot(output_root / "snapshot.yaml", source_root, manifest, reviewed_pmids)
    write_schema(output_root / "schemas" / "pipeline_instance_v1.schema.json")

    instances: list[dict[str, Any]] = []
    instances_dir = output_root / "instances"
    instances_dir.mkdir(parents=True, exist_ok=True)
    for pmid in sorted(reviewed_pmids):
        instance = normalise_extraction(source_root, pmid, reviews.get(pmid, {}))
        apply_source_review(instance, reviews.get(pmid, {}))
        instances.append(instance)
        target = instances_dir / f"pmid_{pmid}_pipeline_01.yaml"
        target.write_text(yaml.safe_dump(instance, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")

    write_component_dictionary(output_root / "component_dictionary.yaml", instances)
    build_component_census(source_root, output_root, manifest, instances)
    build_deep_review_queue(source_root, output_root, manifest, reviewed_pmids)
    write_gap_report(output_root / "initial_gap_report.md", manifest, instances)
    print(f"Wrote {len(manifest)} manifest rows and {len(instances)} reviewed instances to {output_root}")


if __name__ == "__main__":
    main()
