from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


GUIDANCE_SCHEMA = "conn_pilot_literature_guidance_v1"
ALLOWED_CONTEXT_FIELDS = {
    "primary_family",
    "study_design",
    "modality_or_task",
    "year_from",
    "year_to",
}
VISIBLE_EVIDENCE = {"explicit", "inferred"}


class LiteratureEvidenceService:
    """Read-only, deterministic access to the versioned literature review corpus."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.snapshot = self._read_yaml("snapshot.yaml")
        self.curation = self._read_yaml("curation/pilot_source_reviews.yaml")
        self.instances = self._load_instances()
        self.corpus_sha256 = self._corpus_digest()
        self.corpus_version = (
            f"pipeline-review-{self.snapshot.get('snapshot_date', 'unknown')}-"
            f"{self.snapshot.get('normalizer_version', 'unknown')}-{self.corpus_sha256[:12]}"
        )
        self.records = self._build_parameter_records()
        self._records_by_id = {record["evidence_id"]: record for record in self.records}

    def list_guidance_topics(self) -> dict[str, Any]:
        topics: dict[str, dict[str, Any]] = {}
        for instance in self.instances:
            pmid = str(instance["paper"]["pmid"])
            for node in instance["graph"]["nodes"]:
                component_id = str(node["component_id"])
                topic = topics.setdefault(
                    component_id,
                    {
                        "component_id": component_id,
                        "layer": node["layer"],
                        "execution_contexts": set(),
                        "paper_pmids": set(),
                        "parameter_names": set(),
                    },
                )
                topic["execution_contexts"].add(str(node["execution_context"]))
                topic["paper_pmids"].add(pmid)
                topic["parameter_names"].update(
                    str(parameter["name"]) for parameter in node.get("parameters", [])
                )
        serialized = []
        for topic in topics.values():
            serialized.append(
                {
                    "component_id": topic["component_id"],
                    "layer": topic["layer"],
                    "execution_contexts": sorted(topic["execution_contexts"]),
                    "reviewed_paper_count": len(topic["paper_pmids"]),
                    "parameter_names": sorted(topic["parameter_names"]),
                }
            )
        serialized.sort(key=lambda item: (item["layer"], item["component_id"]))
        return self._envelope(
            "list_guidance_topics",
            {"topics": serialized, "count": len(serialized)},
        )

    def get_parameter_guidance(
        self,
        component_id: str,
        parameter_name: str | None = None,
        *,
        context: dict[str, Any] | None = None,
        include_inferred: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        context = self._validate_context(context)
        limit = self._validate_limit(limit)
        matching = [
            record
            for record in self.records
            if record["component_id"] == component_id
            and (parameter_name is None or record["parameter_name"] == parameter_name)
            and self._matches_context(record, context)
        ]
        status_counts = Counter(record["evidence_status"] for record in matching)
        allowed = VISIBLE_EVIDENCE if include_inferred else {"explicit"}
        observations = [record for record in matching if record["evidence_status"] in allowed]
        observations.sort(
            key=lambda record: (
                0 if record["evidence_status"] == "explicit" else 1,
                -(int(record["paper"].get("year") or 0)),
                record["paper"]["pmid"],
                record["evidence_id"],
            )
        )
        available_parameters = sorted(
            {
                record["parameter_name"]
                for record in self.records
                if record["component_id"] == component_id
            }
        )
        return self._envelope(
            "get_parameter_guidance",
            {
                "component_id": component_id,
                "parameter_name": parameter_name,
                "context": context,
                "observations": observations[:limit],
                "returned_count": min(len(observations), limit),
                "total_matching_observations": len(observations),
                "reporting_summary": dict(sorted(status_counts.items())),
                "available_parameters": available_parameters,
                "interpretation_policy": {
                    "recommendation_provided": False,
                    "frequency_is_not_a_recommendation": True,
                    "scientific_appraisal_status": "pending",
                    "client_model_task": (
                        "Compare the observations, applicability and unresolved limitations; "
                        "present alternatives and do not invent an executable default."
                    ),
                },
            },
        )

    def compare_method_options(
        self,
        component_id: str,
        parameter_name: str,
        *,
        context: dict[str, Any] | None = None,
        include_inferred: bool = False,
    ) -> dict[str, Any]:
        guidance = self.get_parameter_guidance(
            component_id,
            parameter_name,
            context=context,
            include_inferred=include_inferred,
            limit=50,
        )
        grouped: dict[str, dict[str, Any]] = {}
        for record in guidance["data"]["observations"]:
            if record["value"] is None:
                continue
            key = _canonical_json(record["value"])
            option = grouped.setdefault(
                key,
                {
                    "value": record["value"],
                    "observation_count": 0,
                    "paper_pmids": set(),
                    "evidence_ids": [],
                    "evidence_statuses": set(),
                },
            )
            option["observation_count"] += 1
            option["paper_pmids"].add(record["paper"]["pmid"])
            option["evidence_ids"].append(record["evidence_id"])
            option["evidence_statuses"].add(record["evidence_status"])
        options = [
            {
                **option,
                "paper_pmids": sorted(option["paper_pmids"]),
                "evidence_ids": sorted(option["evidence_ids"]),
                "evidence_statuses": sorted(option["evidence_statuses"]),
            }
            for option in grouped.values()
        ]
        options.sort(key=lambda item: (-item["observation_count"], _canonical_json(item["value"])))
        return self._envelope(
            "compare_method_options",
            {
                "component_id": component_id,
                "parameter_name": parameter_name,
                "context": guidance["data"]["context"],
                "options": options,
                "option_count": len(options),
                "interpretation_policy": guidance["data"]["interpretation_policy"],
            },
        )

    def get_evidence_record(self, pmid: str) -> dict[str, Any]:
        instance = next(
            (item for item in self.instances if str(item["paper"]["pmid"]) == str(pmid)),
            None,
        )
        if not instance:
            raise ValueError(f"PMID is not in the structurally reviewed corpus: {pmid}")
        records = [
            record for record in self.records if record["paper"]["pmid"] == str(pmid)
        ]
        return self._envelope(
            "get_evidence_record",
            {
                "paper": instance["paper"],
                "classification": instance["classification"],
                "software_environment": instance["software_environment"],
                "source_sections": instance["review"].get("source_sections", []),
                "confirmed_structure": instance["review"].get("confirmed_structure", []),
                "unresolved": instance["review"].get("unresolved", []),
                "discrepancies": instance["review"].get("discrepancies", []),
                "parameter_observations": records,
            },
        )

    def validate_parameter_choice(
        self,
        component_id: str,
        parameter_name: str,
        selected_value: Any,
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        if not isinstance(evidence_ids, list) or len(evidence_ids) > 50:
            raise ValueError("evidence_ids must be an array with at most 50 identifiers")
        missing = sorted(set(evidence_ids) - set(self._records_by_id))
        if missing:
            raise ValueError(f"Unknown evidence identifiers: {', '.join(missing)}")
        cited = [self._records_by_id[evidence_id] for evidence_id in evidence_ids]
        incompatible = [
            record["evidence_id"]
            for record in cited
            if record["component_id"] != component_id
            or record["parameter_name"] != parameter_name
        ]
        if incompatible:
            raise ValueError(
                "Evidence does not belong to the selected component and parameter: "
                + ", ".join(incompatible)
            )
        exact = [
            record
            for record in cited
            if record["evidence_status"] == "explicit"
            and _canonical_json(record["value"]) == _canonical_json(selected_value)
        ]
        if exact:
            alignment = "exact_explicit_observation"
        elif cited:
            alignment = "cited_without_exact_explicit_match"
        else:
            alignment = "no_cited_evidence"
        warnings = [
            "A reported value is not proof that the value is scientifically appropriate for this experiment.",
            "Parameter-level methodological appraisal remains pending.",
        ]
        if alignment != "exact_explicit_observation":
            warnings.insert(0, "The selected value has no exact explicit match in the cited evidence.")
        return self._envelope(
            "validate_parameter_choice",
            {
                "component_id": component_id,
                "parameter_name": parameter_name,
                "selected_value": selected_value,
                "evidence_alignment": alignment,
                "exact_explicit_evidence_ids": [record["evidence_id"] for record in exact],
                "scientific_validity_determined": False,
                "requires_investigator_confirmation": True,
                "evidence_snapshot": cited,
            },
            warnings=warnings,
        )

    def _read_yaml(self, relative_path: str) -> dict[str, Any]:
        path = self.root / relative_path
        if not path.is_file():
            raise ValueError(f"Literature corpus file is missing: {path}")
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"Literature corpus file must contain an object: {path}")
        return value

    def _load_instances(self) -> list[dict[str, Any]]:
        instance_root = self.root / "instances"
        instances = [
            yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in sorted(instance_root.glob("*.yaml"))
        ]
        if not instances:
            raise ValueError(f"No reviewed literature instances found in {instance_root}")
        return instances

    def _build_parameter_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for instance in self.instances:
            paper = instance["paper"]
            classification = instance["classification"]
            for node in instance["graph"]["nodes"]:
                component_id = str(node["component_id"])
                for index, parameter in enumerate(node.get("parameters", []), start=1):
                    name = str(parameter["name"])
                    evidence_id = ":".join(
                        [
                            "pmid",
                            str(paper["pmid"]),
                            "node",
                            _slug(str(node["id"])),
                            "parameter",
                            _slug(name),
                            str(index),
                        ]
                    )
                    record = {
                        "evidence_id": evidence_id,
                        "paper": {
                            "pmid": str(paper["pmid"]),
                            "doi": paper.get("doi"),
                            "title": paper.get("title"),
                            "year": paper.get("year"),
                        },
                        "classification": classification,
                        "component_id": component_id,
                        "node_id": node["id"],
                        "layer": node["layer"],
                        "execution_context": node["execution_context"],
                        "parameter_name": name,
                        "value": _normalize_text_encoding(parameter.get("value")),
                        "evidence_status": parameter.get("evidence", "not_reported"),
                        "source_path": parameter.get("source_path"),
                        "notes": parameter.get("notes"),
                        "source_sections": instance["review"].get("source_sections", []),
                        "unresolved": instance["review"].get("unresolved", []),
                    }
                    records.append(record)
        return records

    def _corpus_digest(self) -> str:
        digest = hashlib.sha256()
        paths = [
            self.root / "snapshot.yaml",
            self.root / "curation" / "pilot_source_reviews.yaml",
            *sorted((self.root / "instances").glob("*.yaml")),
        ]
        for path in paths:
            digest.update(path.relative_to(self.root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def _validate_context(self, context: dict[str, Any] | None) -> dict[str, Any]:
        if context is None:
            return {}
        if not isinstance(context, dict):
            raise ValueError("context must be an object")
        unknown = sorted(set(context) - ALLOWED_CONTEXT_FIELDS)
        if unknown:
            raise ValueError(f"Unknown literature context fields: {', '.join(unknown)}")
        return context

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError("limit must be an integer from 1 through 50")
        return limit

    @staticmethod
    def _matches_context(record: dict[str, Any], context: dict[str, Any]) -> bool:
        classification = record["classification"]
        if "primary_family" in context and classification.get("primary_family") != context["primary_family"]:
            return False
        if "modality_or_task" in context and classification.get("modality_or_task") != context["modality_or_task"]:
            return False
        if "study_design" in context:
            observed = classification.get("study_design", [])
            observed_values = set(observed if isinstance(observed, list) else [observed])
            requested = context["study_design"]
            requested_values = set(requested if isinstance(requested, list) else [requested])
            if not requested_values.intersection(observed_values):
                return False
        year = int(record["paper"].get("year") or 0)
        if "year_from" in context and year < int(context["year_from"]):
            return False
        if "year_to" in context and year > int(context["year_to"]):
            return False
        return True

    def _envelope(
        self,
        operation: str,
        data: dict[str, Any],
        *,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": GUIDANCE_SCHEMA,
            "operation": operation,
            "corpus_version": self.corpus_version,
            "corpus_sha256": self.corpus_sha256,
            "data": data,
            "warnings": warnings or [],
        }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-") or "value"


def _normalize_text_encoding(value: Any) -> Any:
    """Repair the known replacement character introduced by the legacy range extractor."""
    if isinstance(value, str):
        return value.replace("\ufffd", "–")
    if isinstance(value, list):
        return [_normalize_text_encoding(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_text_encoding(item) for key, item in value.items()}
    return value
