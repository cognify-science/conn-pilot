"""Availability-aware QC evidence. Flags never make participant decisions."""
from __future__ import annotations

import copy
import math
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from scipy.io.matlab import MatReadError

from .io import write_json, sha256_file


METRICS = (
    "volume_count", "outlier_count", "outlier_percent", "retained_volume_count",
    "longest_outlier_streak", "global_signal_z_max", "motion_max_mm",
    "motion_mean_mm", "tsnr_median", "dvars_mean", "dvars_max",
)
REQUIRED_ART = ("volume_count", "outlier_count", "retained_volume_count", "motion_mean_mm")


def art_metrics(regressors: Any, timeseries: Any) -> dict[str, Any]:
    """Compute contiguous outliers on volume rows, including a valid zero-outlier case."""
    result: dict[str, Any] = {"metric_availability": {name: False for name in METRICS}}
    if hasattr(regressors, "toarray"):
        regressors = regressors.toarray()
    if regressors is not None:
        matrix = np.asarray(regressors, dtype=float)
        if (matrix.ndim == 2 and matrix.shape[0] > 0 and np.all(np.isfinite(matrix))
                and np.all(np.isin(matrix, [0, 1])) and np.all(matrix.sum(axis=0) <= 1)):
            flags = np.any(matrix != 0, axis=1)
            edges = np.diff(np.r_[False, flags, False].astype(int))
            starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
            outliers = int(flags.sum())
            result.update(volume_count=int(matrix.shape[0]), outlier_count=outliers,
                          retained_volume_count=int(matrix.shape[0])-outliers,
                          outlier_percent=100*outliers/matrix.shape[0],
                          longest_outlier_streak=int(max(ends-starts, default=0)))
            for name in METRICS[:5]:
                result["metric_availability"][name] = True
    if timeseries is not None:
        series = np.asarray(timeseries, dtype=float)
        if (series.ndim == 2 and series.shape[0] > 0 and series.shape[1] >= 2
                and np.all(np.isfinite(series[:, :2]))
                and ("volume_count" not in result or series.shape[0] == result["volume_count"])):
            result.update(global_signal_z_max=float(np.max(np.abs(series[:, 0]))),
                          motion_max_mm=float(np.max(np.abs(series[:, 1]))),
                          motion_mean_mm=float(np.mean(np.abs(series[:, 1]))))
            for name in ("global_signal_z_max", "motion_max_mm", "motion_mean_mm"):
                result["metric_availability"][name] = True
    return normalize_metrics(result)


def refresh_art_evidence(project: dict[str, Any], run_dir: Path, *, destination: Path | None = None) -> dict[str, Any]:
    """Re-read actual staged ART files, including for legacy exports; never rerun MATLAB."""
    path = run_dir / "qc_metrics.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    rows = existing.get("subjects", [])
    if isinstance(rows, dict):
        rows = [rows]
    previous = {item["subject_id"]: item for item in rows}
    output = []
    for subject in project["subjects"]:
        directory = Path(subject["functional"][0]).parent
        files = sorted(path for path in directory.glob("art_regression_outliers_*.mat") if "_and_movement_" not in path.name)
        series_files = sorted(directory.glob("art_regression_timeseries_*.mat"))
        loaded = []
        for candidates in (files, series_files):
            try:
                loaded.append(loadmat(candidates[0])["R"] if len(candidates) == 1 else None)
            except (ValueError, OSError, KeyError, NotImplementedError, MatReadError):
                loaded.append(None)
        old = previous.get(subject["id"], {})
        measured = art_metrics(*loaded)
        # Keep modern, availability-marked image measurements. Legacy zero
        # placeholders stay unavailable; they are not retroactively validated.
        image_metrics = normalize_metrics(old)
        for name in ("tsnr_median", "dvars_mean", "dvars_max"):
            measured[name] = image_metrics[name]
            measured["metric_availability"][name] = image_metrics["metric_availability"][name]
        measured["subject_id"] = subject["id"]
        measured["art_image_available"] = bool(list(directory.glob("art_screenshot*.jpg")))
        measured["source_files"] = [file.name for file in (*files, *series_files)]
        measured["source_sha256"] = {file.name: sha256_file(file) for file in (*files, *series_files)}
        output.append(measured)
    result = {"schema_version": "conn_pilot_subject_qc_v2", "subjects": output,
              "thresholds": existing.get("thresholds", {})}
    write_json(destination or path, result)
    return result


def normalize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(metrics)
    availability = result.get("metric_availability") or {}
    result["metric_availability"] = dict(availability)
    for name in METRICS:
        value = result.get(name)
        finite = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        available = availability.get(name) is True and finite
        result["metric_availability"][name] = available
        if not available:
            # Legacy placeholders cannot be distinguished from actual observations.
            result[name] = None
    result.setdefault("measurement_stage", {"tsnr_median": "preprocessed_before_denoising",
                                           "dvars_mean": "preprocessed_before_denoising",
                                           "dvars_max": "preprocessed_before_denoising"})
    return result


def assess_subject_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    metrics = normalize_metrics(metrics)
    available = metrics["metric_availability"]
    missing = [name for name in REQUIRED_ART if not available[name]]
    flags: list[str] = []
    inconsistent: list[str] = []
    if not missing:
        volumes, outliers, retained = (metrics[name] for name in REQUIRED_ART[:3])
        if (volumes <= 0 or any(not float(value).is_integer() for value in (volumes, outliers, retained))
                or not 0 <= outliers <= volumes or retained != volumes-outliers
                or metrics["motion_mean_mm"] < 0):
            inconsistent.append("inconsistent_volume_or_motion_metrics")
        if retained < 2:
            flags.append("fewer_than_two_retained_volumes")
        if available["outlier_percent"] and not math.isclose(metrics["outlier_percent"], 100*outliers/max(1, volumes), rel_tol=1e-6):
            inconsistent.append("outlier_percentage_disagrees_with_counts")
        if available["longest_outlier_streak"] and not 0 <= metrics["longest_outlier_streak"] <= outliers:
            inconsistent.append("invalid_contiguous_outlier_count")
    return {"status": "available" if not missing and not inconsistent else "incomplete_or_inconsistent",
            "missing_required_metrics": missing, "inconsistencies": inconsistent,
            "inspection_flags": flags, "automatic_decision": None,
            "denoising_evidence": "native_CONN_QA_requires_visual_review",
            "limitations": ["Preprocessed tSNR/DVARS do not establish post-denoising quality.",
                            "Availability and internal consistency do not establish acceptable subject quality."]}


def normalize_qc(qc: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(qc)
    subjects = result.get("subjects", [])
    if isinstance(subjects, dict):
        subjects = [subjects]
    for item in subjects:
        item["metrics"] = normalize_metrics(item.get("metrics") or {})
        item["metric_evidence"] = assess_subject_metrics(item["metrics"])
    result["subjects"] = subjects
    return result
