from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PREFLIGHT_SCHEMA = "conn_pilot_execution_preflight_v1"


def load_bids_metadata(image: Path, dataset_root: Path) -> tuple[dict[str, Any], list[str]]:
    """Resolve JSON metadata using the BIDS inheritance principle."""
    image = image.resolve()
    root = dataset_root.resolve()
    try:
        image.relative_to(root)
    except ValueError:
        root = image.parent

    stem = _nifti_stem(image)
    tokens = stem.split("_")
    suffix = tokens[-1]
    target_entities = set(tokens[:-1])
    directories = list(reversed([image.parent, *image.parent.parents]))
    directories = [directory for directory in directories if directory == root or root in directory.parents]
    candidates: list[tuple[int, int, Path]] = []
    for directory in directories:
        depth = len(directory.relative_to(root).parts)
        for sidecar in directory.glob(f"*_{suffix}.json"):
            sidecar_tokens = sidecar.stem.split("_")
            entities = set(sidecar_tokens[:-1])
            if entities <= target_entities:
                candidates.append((depth, len(entities), sidecar))
        bare = directory / f"{suffix}.json"
        if bare.is_file():
            candidates.append((depth, 0, bare))

    metadata: dict[str, Any] = {}
    sources: list[str] = []
    seen: set[Path] = set()
    for _, _, sidecar in sorted(candidates, key=lambda item: (item[0], item[1], str(item[2]))):
        if sidecar in seen:
            continue
        seen.add(sidecar)
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read BIDS sidecar {sidecar}: {error}") from error
        if not isinstance(payload, dict):
            raise ValueError(f"BIDS sidecar must contain a JSON object: {sidecar}")
        metadata.update(payload)
        sources.append(str(sidecar))
    return metadata, sources


def build_execution_preflight(
    project: dict[str, Any], execution: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Resolve execution-time requirements before MATLAB can prompt interactively."""
    execution = execution or {}
    root = Path(str(project.get("dataset", {}).get("root", "")))
    records: list[dict[str, Any]] = []
    missing_subjects: list[str] = []
    for subject in project.get("subjects", []):
        subject_id = str(subject.get("id", ""))
        for session_index, raw_path in enumerate(subject.get("functional", []), start=1):
            image = Path(str(raw_path))
            metadata, sources = load_bids_metadata(image, root)
            slice_timing = metadata.get("SliceTiming")
            available = bool(isinstance(slice_timing, list) and slice_timing)
            if not available:
                missing_subjects.append(subject_id)
            records.append(
                {
                    "subject_id": subject_id,
                    "session": session_index,
                    "slice_timing_available": available,
                    "slice_timing_count": len(slice_timing) if available else 0,
                    "metadata_sources": sources,
                }
            )

    preprocessing = project.get("parameters", {}).get("preprocessing", {})
    pipeline_record = preprocessing.get("pipeline", {})
    pipeline = pipeline_record.get("value") if isinstance(pipeline_record, dict) else pipeline_record
    requires_slice_timing = str(pipeline) == "default_mni"
    missing_subjects = sorted(set(missing_subjects))
    policy = str(execution.get("missing_slice_timing_policy", "block")).strip().lower()
    authorized = bool(execution.get("missing_slice_timing_authorized", False))

    if not requires_slice_timing:
        decision = {
            "status": "not_applicable",
            "action": "pipeline_does_not_require_slice_timing",
            "requires_investigator_confirmation": False,
        }
    elif not missing_subjects:
        decision = {
            "status": "resolved",
            "action": "apply_bids_slice_timing",
            "source_type": "bids_metadata",
            "confidence": "exact",
            "requires_investigator_confirmation": False,
        }
    elif policy == "omit" and authorized:
        decision = {
            "status": "resolved_with_omission",
            "action": "omit_slice_timing_correction",
            "source_type": "investigator_authorized_execution_policy",
            "source_key": "execution.missing_slice_timing_policy",
            "confidence": "exact_for_omission",
            "rationale": (
                "BIDS SliceTiming metadata is unavailable for one or more subjects; "
                "the acquisition order will not be guessed."
            ),
            "scientific_consequence": (
                "No temporal alignment correction is applied between slices."
            ),
            "requires_investigator_confirmation": False,
        }
    else:
        decision = {
            "status": "unresolved",
            "action": None,
            "source_type": None,
            "confidence": None,
            "requires_investigator_confirmation": True,
            "reason": "BIDS SliceTiming metadata is unavailable for one or more subjects.",
            "available_options": [
                "provide_exact_slice_timing",
                "retrieve_exact_acquisition_order_from_dataset_documentation_or_literature",
                "omit_slice_timing_correction",
            ],
        }

    ready = decision["status"] != "unresolved"
    return {
        "schema_version": PREFLIGHT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ready": ready,
        "checks": {
            "slice_timing": {
                "required_by_pipeline": requires_slice_timing,
                "functional_count": len(records),
                "available_count": sum(1 for record in records if record["slice_timing_available"]),
                "missing_subject_ids": missing_subjects,
                "records": records,
                "decision": decision,
            }
        },
        "policy": {
            "interactive_prompts_allowed": False,
            "unresolved_requirements_block_execution": True,
        },
    }


def _nifti_stem(path: Path) -> str:
    name = path.name
    return name[:-7] if name.lower().endswith(".nii.gz") else path.stem
