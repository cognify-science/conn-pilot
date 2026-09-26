from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .project import execution_identifier, safe_identifier


def generate_conn_batch(project: dict[str, Any], project_path: Path, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    project_name = execution_identifier(project["project"]["name"])
    batch_path = run_dir / f"{project_name}_conn_batch.m"
    batch_path.write_text(_render_batch(project, project_path, run_dir), encoding="utf-8")
    return batch_path


def _render_batch(project: dict[str, Any], project_path: Path, run_dir: Path) -> str:
    parameters = project["parameters"]
    preprocessing = parameters["preprocessing"]
    denoising = parameters["denoising"]
    subjects = project["subjects"]
    design = project["design"]
    seeds = project["seeds"]
    project_name = execution_identifier(project["project"]["name"])
    lines = [
        "% Generated deterministically by CONN Pilot.",
        f"% Source project: {_comment(project_path.as_posix())}",
        f"% Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        "clear batch;",
        f"batch.filename = fullfile('{_matlab_string(run_dir.as_posix())}', '{project_name}.mat');",
        "batch.Setup.isnew = 1;",
        f"batch.Setup.nsubjects = {len(subjects)};",
        f"batch.Setup.RT = {_number(project['dataset']['tr_seconds'])};",
        "",
    ]
    for index, subject in enumerate(subjects, start=1):
        lines.extend(
            [
                f"% Subject: {_comment(subject['id'])}",
                f"batch.Setup.functionals{{{index}}}{{1}} = '{_matlab_string(subject['functional'][0])}';",
                f"batch.Setup.structurals{{{index}}} = '{_matlab_string(subject['structural'][0])}';",
            ]
        )
    lines.extend(
        [
            "",
            "batch.Setup.conditions.names = {'rest'};",
            "for nsubject = 1:batch.Setup.nsubjects",
            "    batch.Setup.conditions.onsets{1}{nsubject}{1} = 0;",
            "    batch.Setup.conditions.durations{1}{nsubject}{1} = inf;",
            "end",
            "",
        ]
    )
    lines.extend(_render_effects(subjects, design))
    lines.extend(
        [
            "",
            f"batch.Setup.preprocessing.steps = '{_matlab_string(_value(preprocessing, 'pipeline'))}';",
            "batch.Setup.preprocessing.sliceorder = 'BIDS';",
            f"batch.Setup.preprocessing.fwhm = {_number(_value(preprocessing, 'smoothing_fwhm_mm'))};",
            "batch.Setup.preprocessing.art_thresholds = "
            f"[{_number(_value(preprocessing, 'global_signal_z_threshold'))} "
            f"{_number(_value(preprocessing, 'outlier_fd_threshold_mm'))}];",
            "batch.Setup.done = 1;",
            "batch.Setup.overwrite = 0;",
            "",
            f"batch.Denoising.filter = [{_number(_value(denoising, 'bandpass_filter_hz')[0])} "
            f"{_number(_value(denoising, 'bandpass_filter_hz')[1])}];",
            f"batch.Denoising.detrending = {_number(_value(denoising, 'detrending_order'))};",
            f"batch.Denoising.despiking = {_number(_value(denoising, 'despiking'))};",
            "batch.Denoising.confounds.names = {'White Matter', 'CSF', 'realignment', 'scrubbing'};",
            "batch.Denoising.confounds.dimensions = "
            f"{{{_number(_value(denoising, 'wm_components'))}, "
            f"{_number(_value(denoising, 'csf_components'))}, 12, Inf}};",
            "batch.Denoising.confounds.deriv = {0, 0, 1, 0};",
            "batch.Denoising.done = 1;",
            "batch.Denoising.overwrite = 0;",
            "",
            "batch.Analysis.name = 'SBC_01';",
            "batch.Analysis.type = 2;",
            "batch.Analysis.measure = 1;",
            f"batch.Analysis.sources = {_cell([seed['conn_source'] for seed in seeds])};",
            "batch.Analysis.done = 1;",
            "batch.Analysis.overwrite = 0;",
            "",
            "conn_batch(batch);",
            "",
        ]
    )
    lines.extend(_render_qc_metrics(subjects, preprocessing, run_dir))
    lines.extend(_render_results(design["contrasts"], seeds))
    lines.append("")
    return "\n".join(lines)


def _render_effects(subjects: list[dict[str, Any]], design: dict[str, Any]) -> list[str]:
    subject_ids = [str(subject["id"]) for subject in subjects]
    names = ["AllSubjects", *design["groups"].keys(), *design.get("covariates", {}).keys()]
    vectors: list[list[float]] = [[1.0] * len(subjects)]
    for members in design["groups"].values():
        member_set = set(map(str, members))
        vectors.append([1.0 if subject_id in member_set else 0.0 for subject_id in subject_ids])
    for values in design.get("covariates", {}).values():
        vectors.append([float(values[subject_id]) for subject_id in subject_ids])
    lines = [f"batch.Setup.subjects.effect_names = {_cell(names)};"]
    for index, vector in enumerate(vectors, start=1):
        lines.append(f"batch.Setup.subjects.effects{{{index}}} = [{'; '.join(_number(item) for item in vector)}];")
    return lines


def _render_qc_metrics(
    subjects: list[dict[str, Any]], preprocessing: dict[str, Any], run_dir: Path
) -> list[str]:
    """Export the ART values needed for auditable subject review as JSON."""
    lines = [
        "% Subject-level ART metrics",
        "clear qc_metrics qc_subjects;",
        "qc_metrics.schema_version = 'conn_pilot_subject_qc_v1';",
        f"qc_metrics.thresholds.global_signal_z = {_number(_value(preprocessing, 'global_signal_z_threshold'))};",
        f"qc_metrics.thresholds.motion_mm = {_number(_value(preprocessing, 'outlier_fd_threshold_mm'))};",
        "qc_subjects = struct([]);",
    ]
    for index, subject in enumerate(subjects, start=1):
        functional_dir = Path(subject["functional"][0]).parent.as_posix()
        subject_id = _matlab_string(subject["id"])
        lines.extend(
            [
                f"qc_subjects({index}).subject_id = '{subject_id}';",
                f"art_outlier_files = dir(fullfile('{_matlab_string(functional_dir)}', 'art_regression_outliers_*.mat'));",
                "if ~isempty(art_outlier_files), art_outlier_files = art_outlier_files(~contains({art_outlier_files.name}, '_and_movement_')); end",
                f"art_timeseries_files = dir(fullfile('{_matlab_string(functional_dir)}', 'art_regression_timeseries_*.mat'));",
                f"art_image_files = dir(fullfile('{_matlab_string(functional_dir)}', 'art_screenshot*.jpg'));",
                f"qc_subjects({index}).art_image_available = ~isempty(art_image_files);",
                "if ~isempty(art_outlier_files)",
                "    art_data = load(fullfile(art_outlier_files(1).folder, art_outlier_files(1).name), 'R');",
                f"    qc_subjects({index}).volume_count = size(art_data.R, 1);",
                f"    qc_subjects({index}).outlier_count = sum(any(abs(art_data.R) > eps, 1));",
                f"    qc_subjects({index}).outlier_percent = 100 * qc_subjects({index}).outlier_count / max(1, qc_subjects({index}).volume_count);",
                "else",
                f"    qc_subjects({index}).volume_count = 0;",
                f"    qc_subjects({index}).outlier_count = 0;",
                f"    qc_subjects({index}).outlier_percent = 0;",
                "end",
                "if ~isempty(art_timeseries_files)",
                "    art_series = load(fullfile(art_timeseries_files(1).folder, art_timeseries_files(1).name), 'R');",
                f"    qc_subjects({index}).global_signal_z_max = max(abs(art_series.R(:, 1)));",
                f"    qc_subjects({index}).motion_max_mm = max(abs(art_series.R(:, 2)));",
                f"    qc_subjects({index}).motion_mean_mm = mean(abs(art_series.R(:, 2)));",
                "else",
                f"    qc_subjects({index}).global_signal_z_max = 0;",
                f"    qc_subjects({index}).motion_max_mm = 0;",
                f"    qc_subjects({index}).motion_mean_mm = 0;",
                "end",
            ]
        )
    metrics_path = _matlab_string((run_dir / "qc_metrics.json").as_posix())
    lines.extend(
        [
            "qc_metrics.subjects = qc_subjects;",
            f"qc_metrics_file = fopen('{metrics_path}', 'w');",
            "if qc_metrics_file < 0, error('CONN Pilot could not create qc_metrics.json'); end",
            "fprintf(qc_metrics_file, '%s', jsonencode(qc_metrics));",
            "fclose(qc_metrics_file);",
            "clear art_data art_series art_outlier_files art_timeseries_files art_image_files qc_metrics_file;",
            "",
        ]
    )
    return lines


def _render_results(contrasts: list[dict[str, Any]], seeds: list[dict[str, Any]]) -> list[str]:
    lines = ["% Second-level models"]
    sources = [seed["conn_source"] for seed in seeds]
    for index, contrast in enumerate(contrasts, start=1):
        variable = f"results_batch_{index}"
        lines.extend(
            [
                f"% Contrast: {_comment(contrast['name'])}",
                f"clear {variable};",
                f"{variable}.filename = batch.filename;",
                f"{variable}.Results.name = 'SBC_01';",
                f"{variable}.Results.saveas = '{_matlab_string(safe_identifier(contrast['name']))}';",
                f"{variable}.Results.between_subjects.effect_names = {_cell(contrast['effects'])};",
                f"{variable}.Results.between_subjects.contrast = [{_vector(contrast['weights'])}];",
                f"{variable}.Results.between_conditions.effect_names = {{'rest'}};",
                f"{variable}.Results.between_conditions.contrast = 1;",
                f"{variable}.Results.between_sources.effect_names = {_cell(sources)};",
                f"{variable}.Results.between_sources.contrast = eye({len(sources)});",
                f"{variable}.Results.display = 0;",
                f"conn_batch({variable});",
                "",
            ]
        )
    return lines


def _value(section: dict[str, Any], name: str) -> Any:
    return section[name]["value"]


def _matlab_string(value: Any) -> str:
    return str(value).replace("\\", "/").replace("'", "''")


def _comment(value: Any) -> str:
    return str(value).replace("\r", " ").replace("\n", " ").replace("%", "percent")


def _number(value: Any) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else format(number, ".12g")


def _vector(values: list[Any]) -> str:
    return " ".join(_number(value) for value in values)


def _cell(values: list[Any]) -> str:
    return "{" + ", ".join(f"'{_matlab_string(value)}'" for value in values) + "}"
