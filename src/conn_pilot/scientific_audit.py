"""Read-only audits of saved CONN models. No numerical CONN processing is rerun."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import scipy
from scipy.io import loadmat
from scipy.io.matlab import MatReadError
from scipy.stats import t as student_t

from .analysis_contract import analysis_contract
from .io import write_json
from .project import execution_identifier, safe_identifier


AUDIT_SCHEMA = "conn_pilot_scientific_audit_v1"


def sample_identity(subject_ids: list[str]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(sorted(subject_ids), separators=(",", ":")).encode()
    ).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bh_adjust(p: Any) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values for one explicitly bounded family."""
    values = np.asarray(p, dtype=float).reshape(-1)
    if not len(values) or not np.all(np.isfinite(values)) or np.any((values < 0) | (values > 1)):
        raise ValueError("The complete testing family must contain valid p-values")
    order = np.argsort(values, kind="stable")
    adjusted = np.minimum.accumulate((values[order] * len(values) / np.arange(1, len(values)+1))[::-1])[::-1]
    result = np.empty_like(values)
    result[order] = np.clip(adjusted, 0, 1)
    return result


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, (list, tuple, np.ndarray)):
        return [item for item in np.asarray(value, dtype=object).reshape(-1) if isinstance(item, dict)]
    return []


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if value is None:
        return []
    return [str(item) for item in np.asarray(value).reshape(-1)]


def _effects(project: dict[str, Any], selected: list[str]) -> dict[str, list[float]]:
    design = project["design"]
    result = {"AllSubjects": [1.0] * len(selected)}
    for name, members in design.get("groups", {}).items():
        result[name] = [float(sid in members) for sid in selected]
    for name, values in design.get("covariates", {}).items():
        result[name] = [float(values[sid]) for sid in selected]
    return result


def inspect_model(
    project: dict[str, Any], model: dict[str, Any], contrast: dict[str, Any],
    included_subject_ids: list[str], *, kind: str, aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compare saved model identity, matrix and contrast to the frozen design."""
    issues: list[str] = []
    all_ids = [str(item["id"]) for item in project["subjects"]]
    xx = model.get("xX") or {}
    source_indices: list[int] = []
    selection = np.asarray(xx.get("SelectedSubjects", []), dtype=float).reshape(-1)
    valid_selection = (len(selection) == len(all_ids) and np.all(np.isin(selection, [0, 1])))
    actual_ids = [sid for sid, flag in zip(all_ids, selection) if flag] if valid_selection else []
    if not valid_selection:
        issues.append("subject_identity_unavailable")
    if actual_ids != [sid for sid in all_ids if sid in set(included_subject_ids)]:
        issues.append("executed_sample_mismatch")
    if len(set(included_subject_ids)) != len(included_subject_ids) or not set(included_subject_ids).issubset(all_ids):
        issues.append("invalid_expected_sample_identity")
    if _strings(xx.get("SelectedConditions")) != ["rest"]:
        issues.append("executed_condition_mismatch_or_unavailable")
    within = np.asarray(xx.get("SelectedConditionsContrast", []), dtype=float).reshape(-1)
    if within.size != 1 or not np.allclose(within, [1]):
        issues.append("executed_condition_contrast_mismatch_or_unavailable")
    if kind == "seed_to_voxel":
        inputs = _records((model.get("xY") or {}).get("VY"))
        indices = []
        for volume in inputs:
            match = re.search(r"BETA_Subject(\d+)_Condition(\d+)_Source(\d+)", str(volume.get("fname", "")))
            if match and int(match[2]) == 1:
                indices.append(int(match[1]))
                source_indices.append(int(match[3]))
        expected_indices = [all_ids.index(sid)+1 for sid in actual_ids]
        if indices != expected_indices:
            issues.append("saved_input_subject_order_mismatch_or_unavailable")
        if len(set(source_indices)) != 1:
            issues.append("saved_single_source_identity_unavailable")
    matrix = np.asarray(xx.get("X", []), dtype=float)
    if matrix.ndim == 1 and len(actual_ids) == len(matrix):
        matrix = matrix.reshape(-1, 1)
    if matrix.ndim != 2 or not matrix.size or not np.all(np.isfinite(matrix)):
        return {"status": "unverified", "issues": [*issues, "design_matrix_unavailable_or_nonfinite"]}
    rank = int(np.linalg.matrix_rank(matrix))
    residual_df = int(matrix.shape[0] - rank)
    if matrix.shape[0] != len(actual_ids):
        issues.append("model_rows_do_not_match_subject_identity")
    if rank != matrix.shape[1]:
        issues.append("rank_deficient_design")
    if residual_df <= 0:
        issues.append("nonpositive_residual_degrees_of_freedom")
    raw_names = _strings(xx.get("SelectedSubjecteffects", xx.get("name")))
    reverse_aliases = {value: key for key, value in (aliases or {}).items()}
    names = [reverse_aliases.get(name, name) for name in raw_names]
    expected_names = list(contrast["effects"])
    if len(names) != matrix.shape[1] or len(set(names)) != len(names) or set(names) != set(expected_names):
        issues.append("executed_effects_mismatch_or_unavailable")
    else:
        vectors = _effects(project, actual_ids)
        expected_matrix = np.asarray([vectors[name] for name in names], dtype=float).T
        if expected_matrix.shape != matrix.shape or not np.allclose(matrix, expected_matrix, atol=1e-8, rtol=1e-8):
            issues.append("executed_design_values_mismatch")
        weights = dict(zip(expected_names, contrast["weights"]))
        expected_c = np.asarray([weights[name] for name in names], dtype=float)
        actual_c = np.asarray(xx.get("SelectedSubjecteffectsContrast", model.get("c", [])), dtype=float).reshape(-1)
        if actual_c.shape != expected_c.shape or not np.allclose(actual_c, expected_c):
            issues.append("executed_contrast_mismatch_or_unavailable")
        if kind == "seed_to_voxel":
            cons = _records(model.get("xCon"))
            spm_c = np.asarray(cons[0].get("c", []) if cons else [], dtype=float).reshape(-1)
            if spm_c.shape != expected_c.shape or not np.allclose(spm_c, expected_c):
                issues.append("spm_test_contrast_mismatch_or_unavailable")
        else:
            roi_c = np.asarray(model.get("c", []), dtype=float).reshape(-1)
            if roi_c.shape != expected_c.shape or not np.allclose(roi_c, expected_c):
                issues.append("roi_test_contrast_mismatch_or_unavailable")
    if kind == "seed_to_voxel":
        df_values = np.asarray(xx.get("erdf", []), dtype=float).reshape(-1)
    else:
        df_values = np.asarray(model.get("dof", []), dtype=float).reshape(-1)
    actual_df = float(df_values[-1]) if len(df_values) and np.isfinite(df_values[-1]) else None
    if actual_df is None or not np.isclose(actual_df, residual_df):
        issues.append("saved_residual_degrees_of_freedom_mismatch_or_unavailable")
    return {
        "status": "passed" if not issues else "failed", "issues": issues,
        "included_subject_ids": actual_ids, "row_count": int(matrix.shape[0]),
        "column_count": int(matrix.shape[1]), "rank": rank,
        "residual_degrees_of_freedom": residual_df, "saved_residual_degrees_of_freedom": actual_df,
        "effect_names": names, "contrast_name": contrast["name"],
        "input_source_indices": sorted(set(source_indices)),
        "design_matrix_sha256": hashlib.sha256(matrix.astype("<f8").tobytes()).hexdigest(),
    }


def _resolve_file(folder: Path, value: Any) -> Path:
    # SPM saves absolute worker paths. Use only the filename in the current model
    # directory; do not follow stale or unrelated absolute paths.
    filename = str(value).replace("\\", "/").rsplit("/", 1)[-1].split(",", 1)[0]
    if not filename or filename in {".", ".."}:
        raise ValueError("Saved image filename is unavailable")
    path = folder / filename
    if not path.is_file():
        raise ValueError("Saved model image is unavailable")
    return path


def _family_summary(p: np.ndarray, effect: np.ndarray, *, family: str) -> dict[str, Any]:
    adjusted = bh_adjust(p)
    return {
        "status": "available", "test": "T", "tails": "two_sided",
        "multiplicity": {"method": "FDR_BH", "family": family, "family_size": int(len(p)),
                         "scope": "within_this_model_only", "computed_by": "CONN Pilot audit"},
        "minimum_p_value": float(np.min(p)), "minimum_adjusted_p_value": float(np.min(adjusted)),
        "count_q_le_0_05": int(np.count_nonzero(adjusted <= 0.05)),
        "positive_count_q_le_0_05": int(np.count_nonzero((adjusted <= 0.05) & (effect > 0))),
        "negative_count_q_le_0_05": int(np.count_nonzero((adjusted <= 0.05) & (effect < 0))),
        "hypothesis_support": None,
        "limitations": ["Exploratory extraction; not a registered hypothesis endpoint.",
                        "Correction does not pool multiple models, seeds or project contrasts."],
    }


def extract_statistics(model: dict[str, Any], folder: Path, *, kind: str, residual_df: int, source_name: str | None = None) -> dict[str, Any]:
    """Conservative univariate T extraction. Other models remain explicitly unsupported."""
    if kind == "seed_to_voxel":
        tests = _records(model.get("xCon"))
        if not tests or tests[0].get("STAT") != "T":
            raise ValueError("Only univariate saved T contrasts are supported")
        test = tests[0]
        paths = {
            "statistic": _resolve_file(folder, (test.get("Vspm") or {}).get("fname")),
            "effect": _resolve_file(folder, (test.get("Vcon") or {}).get("fname")),
            "mask": _resolve_file(folder, (model.get("VM") or {}).get("fname")),
        }
        images = {key: nib.load(str(path)) for key, path in paths.items()}
        ref = images["statistic"]
        if any(img.shape != ref.shape or not np.allclose(img.affine, ref.affine) for img in images.values()):
            raise ValueError("Statistic, effect and mask image geometry disagree")
        mask_data = images["mask"].get_fdata()
        if not np.all(np.isfinite(mask_data)):
            raise ValueError("Saved testing mask contains nonfinite values")
        mask = mask_data > 0
        values = ref.get_fdata()[mask]
        effect = images["effect"].get_fdata()[mask]
        if not len(values) or not np.all(np.isfinite(values)) or not np.all(np.isfinite(effect)):
            raise ValueError("The saved testing family is empty or contains nonfinite values")
        if np.any(np.sign(values) != np.sign(effect)):
            raise ValueError("Saved T statistics and effects have inconsistent signs")
        p = 2 * student_t.sf(np.abs(values), residual_df)
        summary = _family_summary(p, effect, family="all_voxels_in_saved_model_mask")
        # A selected peak is descriptive; its naive CI would have selection bias.
        best = int(np.argmin(p))
        index = np.argwhere(mask)[best]
        summary["descriptive_peak"] = {
            "voxel_index": index.tolist(), "world_coordinate": nib.affines.apply_affine(ref.affine, index).tolist(),
            "effect_estimate": float(effect[best]), "statistic": float(values[best]),
            "p_value": float(p[best]), "adjusted_p_value": float(bh_adjust(p)[best]),
            "confidence_interval": None, "selection": "minimum_two_sided_p_within_mask",
            "warning": "Selected peak; not an unbiased effect estimate or a predefined endpoint.",
        }
        summary["artifact_sha256"] = {key: sha256_file(path) for key, path in paths.items()}
        summary["residual_degrees_of_freedom"] = residual_df
        return summary

    if str(model.get("statsname")) != "T":
        raise ValueError("Only univariate saved ROI T contrasts are supported")
    sources = _strings(model.get("orig_sources")) or ([source_name] if source_name else [])
    targets = _strings(model.get("names2"))
    effect = np.asarray(model.get("h", []), dtype=float).reshape(-1)
    statistic = np.asarray(model.get("F", []), dtype=float).reshape(-1)
    data = np.asarray(model.get("y", []), dtype=float)
    within = np.asarray(model.get("c2", []), dtype=float).reshape(-1)
    if len(sources) != 1 or len(within) != 1 or within[0] != 1 or data.ndim != 2:
        raise ValueError("Multisource or multicondition ROI tests require a dedicated extractor")
    if len(targets) != len(effect) or len(effect) != len(statistic) or data.shape[1] != len(targets):
        raise ValueError("ROI labels, effects and statistics do not align")
    # Self correlations are not connection tests. Keep all other saved targets;
    # do not silently narrow the family to a favorable subset of connections.
    eligible = np.asarray([target != sources[0] for target in targets])
    values, effects = statistic[eligible], effect[eligible]
    if not len(values) or not np.all(np.isfinite(values)) or not np.all(np.isfinite(effects)):
        raise ValueError("The complete ROI testing family is unavailable or nonfinite")
    p = 2 * student_t.sf(np.abs(values), residual_df)
    adjusted = bh_adjust(p)
    summary = _family_summary(p, effects, family="all_saved_targets_except_self_for_one_source")
    # Compute SE independently from saved y, X and c so zero effects/T=0 retain
    # a defined interval and never require dividing an effect by a T statistic.
    matrix = np.asarray(model["xX"]["X"], dtype=float).reshape(data.shape[0], -1)
    weights = np.asarray(model["c"], dtype=float).reshape(-1)
    beta = np.linalg.lstsq(matrix, data, rcond=None)[0]
    predicted_effect = weights @ beta
    residuals = data - matrix @ beta
    variance = np.sum(residuals**2, axis=0) / residual_df
    se = np.sqrt(variance * float(weights @ np.linalg.inv(matrix.T @ matrix) @ weights))
    predicted_t = np.divide(predicted_effect, se, out=np.full_like(se, np.nan), where=se > 0)
    if not np.allclose(predicted_effect[eligible], effects, rtol=1e-5, atol=1e-7) or not np.allclose(predicted_t[eligible], values, rtol=1e-5, atol=1e-7):
        raise ValueError("Saved ROI estimates disagree with the inspected univariate model")
    critical = float(student_t.ppf(0.975, residual_df))
    summary["connections"] = [
        {"source": sources[0], "target": targets[int(index)], "effect_estimate": float(effects[j]),
         "statistic": float(values[j]), "p_value": float(p[j]), "adjusted_p_value": float(adjusted[j]),
         "confidence_interval": {"level": 0.95, "low": float(effects[j]-critical*se[index]),
                                 "high": float(effects[j]+critical*se[index]), "simultaneous": False},
         "effect_scale": "contrast_of_first_level_Fisher_z_connectivity"}
        for j, index in enumerate(np.flatnonzero(eligible))
    ]
    summary["residual_degrees_of_freedom"] = residual_df
    return summary


def audit_run(
    project: dict[str, Any], run_dir: Path, *, output_dir: Path | None = None,
    included_subject_ids: list[str] | None = None, aliases: dict[str, str] | None = None,
    destination: Path | None = None,
) -> dict[str, Any]:
    analysis = analysis_contract(project)
    included = included_subject_ids if included_subject_ids is not None else [str(item["id"]) for item in project["subjects"]]
    output_dir = output_dir or run_dir / execution_identifier(project["project"]["name"]) / "results" / "secondlevel" / analysis["conn_name"]
    filename = "SPM.mat" if analysis["kind"] == "seed_to_voxel" else "ROI.mat"
    models: list[dict[str, Any]] = []
    contrasts = project["design"]["contrasts"]
    for path in sorted(output_dir.glob(f"**/{filename}")):
        relative = path.relative_to(output_dir).as_posix()
        candidates = [contrast for contrast in contrasts if safe_identifier(contrast["name"]) in path.relative_to(output_dir).parts]
        contrast = candidates[0] if len(candidates) == 1 else (contrasts[0] if len(contrasts) == 1 else None)
        try:
            if contrast is None:
                raise ValueError("Cannot bind the saved model to one frozen project contrast")
            payload = loadmat(path, simplify_cells=True)
            records = _records(payload.get("SPM" if analysis["kind"] == "seed_to_voxel" else "ROI"))
            if not records:
                raise ValueError("Saved model structure is missing")
            for index, model in enumerate(records):
                inspected = inspect_model(project, model, contrast, included, kind=analysis["kind"], aliases=aliases)
                result = {"relative_path": relative, "record_index": index, "sha256": sha256_file(path),
                          "contrast_name": contrast["name"], "design": inspected}
                if inspected["status"] == "passed":
                    try:
                        # CONN results_roi saves a record for every source, with
                        # the complete ordered source list in each record.names.
                        # Only use this alignment when all records agree.
                        names = _strings(model.get("names"))
                        explicit_sources = _strings(model.get("orig_sources"))
                        source = explicit_sources[0] if len(explicit_sources) == 1 else None
                        if (analysis["kind"] == "roi_to_roi" and len(records) == len(names)
                                and len(set(names)) == len(names)
                                and all(_strings(record.get("names")) == names for record in records)):
                            source = names[index]
                        result["source_identity"] = source
                        result["statistics"] = extract_statistics(model, path.parent, kind=analysis["kind"], residual_df=inspected["residual_degrees_of_freedom"], source_name=source)
                    except (ValueError, OSError, KeyError, TypeError, np.linalg.LinAlgError):
                        result["statistics"] = {"status": "unavailable", "reason": "unsupported_or_inconsistent_inferential_artifacts"}
                else:
                    result["statistics"] = {"status": "blocked", "reason": "model_integrity_not_verified"}
                models.append(result)
        except (ValueError, OSError, KeyError, TypeError, NotImplementedError, IndexError, MatReadError):
            models.append({"relative_path": relative, "sha256": sha256_file(path), "contrast_name": contrast["name"] if contrast else None,
                           "design": {"status": "unverified", "issues": ["saved_model_unreadable_or_contrast_unbound"]},
                           "statistics": {"status": "unavailable", "reason": "saved_model_not_verified"}})
    covered = {item["contrast_name"] for item in models if item["design"]["status"] == "passed"}
    missing = [item["name"] for item in contrasts if item["name"] not in covered]
    incomplete_source_coverage = []
    for contrast in contrasts:
        group = [item for item in models if item["contrast_name"] == contrast["name"]]
        if analysis["kind"] == "seed_to_voxel":
            source_keys = [tuple(item["design"].get("input_source_indices", [])) for item in group]
            if len(source_keys) != len(project["seeds"]) or len(set(source_keys)) != len(source_keys):
                incomplete_source_coverage.append(contrast["name"])
        else:
            actual_sources = {item.get("source_identity") for item in group}
            if not {seed["conn_source"] for seed in project["seeds"]}.issubset(actual_sources):
                incomplete_source_coverage.append(contrast["name"])
    passed = bool(models) and not missing and not incomplete_source_coverage and all(item["design"]["status"] == "passed" for item in models)
    audit = {
        "schema_version": AUDIT_SCHEMA, "created_at": datetime.now(timezone.utc).isoformat(),
        "auditor_sha256": sha256_file(Path(__file__)),
        "numerical_runtime": {"numpy": np.__version__, "scipy": scipy.__version__, "nibabel": nib.__version__},
        "sample_version": sample_identity(included), "included_subject_ids": sorted(included),
        "project_spec_sha256": hashlib.sha256(json.dumps(project, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "analysis_kind": analysis["kind"], "model_integrity": {"status": "passed" if passed else "unverified_or_failed", "missing_verified_contrasts": missing, "incomplete_source_coverage": incomplete_source_coverage},
        "structured_inference": {"status": "available" if passed and all(item["statistics"]["status"] == "available" for item in models) else "incomplete"},
        "models": models, "automatic_scientific_acceptance": None,
        "limitations": ["No automatic subject exclusions or scientific acceptance.",
                        "Exploratory two-sided univariate T extraction with within-model FDR_BH only.",
                        "SBC source coverage verifies saved source indices; atlas labels require the first-level source registry.",
                        "MAT v7.3 and multivariate/F/cluster/permutation inference remain explicitly unavailable."],
    }
    write_json(destination or run_dir / "scientific_audit.json", audit)
    return audit


def model_integrity_gate(audit: dict[str, Any], sample_version: str, included: list[str]) -> bool:
    """The container's immutable result/output version binds this audit to artifacts."""
    return bool(
        audit.get("schema_version") == AUDIT_SCHEMA
        and audit.get("sample_version") == sample_version
        and sorted(audit.get("included_subject_ids", [])) == sorted(included)
        and (audit.get("model_integrity") or {}).get("status") == "passed"
        and audit.get("models")
        and all((item.get("design") or {}).get("status") == "passed" for item in audit["models"])
    )
