from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .analysis_contract import analysis_contract
from .project import execution_identifier


SUBJECT_INDEX = re.compile(r"Subject(?P<index>\d{3})", re.IGNORECASE)


def build_job_progress(
    job: dict[str, Any], project: dict[str, Any], *, phase: str
) -> dict[str, Any]:
    """Infer path-free CONN progress from durable output milestones.

    The percentage is deliberately approximate.  CONN does not publish a stable
    machine-readable percentage, so the monitor counts completed per-subject
    preprocessing, denoising and first-level milestones plus second-level models.
    """
    run_dir = Path(str(job["run_dir"]))
    subject_ids = [str(item["id"]) for item in project.get("subjects", [])]
    analysis = analysis_contract(project)
    project_dir = run_dir / execution_identifier(str(project["project"]["name"]))
    preprocessing_dir = project_dir / "results" / "preprocessing"
    data_dir = project_dir / "data"
    first_level_dir = project_dir / "results" / "firstlevel" / str(analysis["conn_name"])
    second_level_dir = project_dir / "results" / "secondlevel" / str(analysis["conn_name"])

    preprocessing = _subject_indexes(data_dir.glob("ROI_Subject*_Session*.mat"))
    denoising = _subject_indexes(preprocessing_dir.glob("vvPCeig_Subject*_Condition*.mat"))
    if analysis["kind"] == "seed_to_voxel":
        expected_per_subject = max(1, len(project.get("seeds", [])))
        first_level = _complete_subject_indexes(
            first_level_dir.glob("BETA_Subject*_Condition*_Source*.nii"),
            expected_per_subject,
        )
        second_level_count = len(list(second_level_dir.glob("**/SPM.mat")))
    else:
        first_level = _subject_indexes(
            first_level_dir.glob("resultsROI_Subject*_Condition*.mat")
        )
        second_level_count = len(list(second_level_dir.glob("**/ROI.mat")))

    # A later durable milestone implies completion of the earlier milestones.
    denoising |= first_level
    preprocessing |= denoising

    expected_subjects = len(subject_ids)
    expected_models = max(1, len(project.get("design", {}).get("contrasts", [])))
    stages = [
        _stage("preprocessing", len(preprocessing), expected_subjects),
        _stage("denoising", len(denoising), expected_subjects),
        _stage("first_level", len(first_level), expected_subjects),
        _stage("second_level", min(second_level_count, expected_models), expected_models),
    ]
    completed_units = sum(item["completed"] for item in stages)
    total_units = sum(item["total"] for item in stages)
    state = str(job.get("state", "unknown"))
    percent = 100 if state == "succeeded" else round(100 * completed_units / total_units) if total_units else 0

    now = datetime.now(timezone.utc)
    activity = _activity(run_dir, project_dir, subject_ids, now)
    subject_progress = []
    for index, subject_id in enumerate(subject_ids, start=1):
        completed = [
            name
            for name, indexes in (
                ("preprocessing", preprocessing),
                ("denoising", denoising),
                ("first_level", first_level),
            )
            if index in indexes
        ]
        subject_progress.append(
            {
                "subject_id": subject_id,
                "completed_stages": completed,
                "highest_completed_stage": completed[-1] if completed else None,
            }
        )

    return {
        "schema_version": "conn_pilot_job_progress_v1",
        "job_id": str(job["id"]),
        "state": state,
        "phase": phase,
        "terminal": state in {"succeeded", "failed", "cancelled"},
        "approximate_percent": max(0, min(100, percent)),
        "progress_basis": {
            "method": "durable_artifact_milestones_equal_weight",
            "approximate": True,
            "completed_units": completed_units,
            "total_units": total_units,
            "eta_seconds": None,
            "eta_reason": "No calibrated runtime model is available for this worker and dataset.",
        },
        "stages": stages,
        "subjects": {
            "total": expected_subjects,
            "active_subject_ids": activity.pop("active_subject_ids"),
            "items": subject_progress,
        },
        "activity": activity,
        "reported_at": now.isoformat(),
        "scientific_interpretation": {
            "automatic_decision": None,
            "reason": "Execution progress does not imply QC or scientific acceptance.",
        },
    }


def _stage(name: str, completed: int, total: int) -> dict[str, Any]:
    bounded = min(max(completed, 0), max(total, 0))
    if total and bounded >= total:
        status = "complete"
    elif bounded:
        status = "in_progress"
    else:
        status = "pending"
    return {"name": name, "completed": bounded, "total": total, "status": status}


def _subject_indexes(paths: Iterable[Path]) -> set[int]:
    result: set[int] = set()
    for path in paths:
        match = SUBJECT_INDEX.search(path.name)
        if match:
            result.add(int(match.group("index")))
    return result


def _complete_subject_indexes(paths: Iterable[Path], expected_count: int) -> set[int]:
    counts: dict[int, int] = {}
    for path in paths:
        match = SUBJECT_INDEX.search(path.name)
        if match:
            index = int(match.group("index"))
            counts[index] = counts.get(index, 0) + 1
    return {index for index, count in counts.items() if count >= expected_count}


def _activity(
    run_dir: Path, project_dir: Path, subject_ids: list[str], now: datetime
) -> dict[str, Any]:
    latest: float | None = None
    latest_by_subject: dict[str, float] = {}
    candidates = [run_dir / "matlab_stdout.log", run_dir / "matlab_stderr.log"]
    roots = [project_dir / "data", project_dir / "results", run_dir / "inputs"]
    for root in roots:
        if root.is_dir():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    for path in candidates:
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        latest = modified if latest is None else max(latest, modified)
        subject_id = _path_subject(path, subject_ids)
        if subject_id:
            latest_by_subject[subject_id] = max(latest_by_subject.get(subject_id, 0.0), modified)
    if latest is None:
        return {
            "state": "unknown",
            "last_activity_at": None,
            "seconds_since_activity": None,
            "active_subject_ids": [],
        }
    age = max(0, round(now.timestamp() - latest))
    state = "active" if age <= 300 else "quiet" if age <= 1800 else "stale"
    active_subjects = [
        subject_id
        for subject_id in subject_ids
        if latest_by_subject.get(subject_id, 0.0) >= latest - 300
        and now.timestamp() - latest_by_subject[subject_id] <= 300
    ]
    return {
        "state": state,
        "last_activity_at": datetime.fromtimestamp(latest, timezone.utc).isoformat(),
        "seconds_since_activity": age,
        "active_subject_ids": active_subjects,
    }


def _path_subject(path: Path, subject_ids: list[str]) -> str | None:
    match = SUBJECT_INDEX.search(path.name)
    if match:
        index = int(match.group("index"))
        if 1 <= index <= len(subject_ids):
            return subject_ids[index - 1]
    lower_parts = {part.lower(): part for part in path.parts}
    for subject_id in subject_ids:
        if subject_id.lower() in lower_parts:
            return subject_id
    return None
