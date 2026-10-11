from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis_contract import analysis_contract
from .project import execution_identifier, safe_identifier


def generate_conn_batch(
    project: dict[str, Any],
    project_path: Path,
    run_dir: Path,
    execution: dict[str, Any] | None = None,
) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    project_name = execution_identifier(project["project"]["name"])
    batch_path = run_dir / f"{project_name}_conn_batch.m"
    batch_path.write_text(
        _render_batch(project, project_path, run_dir, execution), encoding="utf-8"
    )
    return batch_path


def _render_batch(
    project: dict[str, Any],
    project_path: Path,
    run_dir: Path,
    execution: dict[str, Any] | None = None,
) -> str:
    parameters = project["parameters"]
    preprocessing = parameters["preprocessing"]
    denoising = parameters["denoising"]
    subjects = project["subjects"]
    design = project["design"]
    seeds = project["seeds"]
    analysis = analysis_contract(project)
    project_name = execution_identifier(project["project"]["name"])
    execution = execution or {}
    parallel_jobs = int(execution.get("parallel_jobs", 0) or 0)
    if parallel_jobs < 0:
        raise ValueError("execution.parallel_jobs must be zero or greater")
    parallel_profile = str(
        execution.get("parallel_profile", "Background process (Windows)")
    )
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
    if parallel_jobs:
        lines.extend(
            [
                "% Parallel subject-level execution configured by the worker.",
                f"batch.parallel.N = {parallel_jobs};",
                f"batch.parallel.profile = '{_matlab_string(parallel_profile)}';",
                "batch.parallel.immediatereturn = 0;",
                "",
            ]
        )
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
    preflight = project.get("execution_preflight", {})
    slice_timing = preflight.get("checks", {}).get("slice_timing", {})
    slice_action = slice_timing.get("decision", {}).get("action")
    preprocessing_lines = _render_preprocessing_steps(preprocessing, slice_action)
    lines.extend(
        [
            "",
            *preprocessing_lines,
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
            f"batch.Analysis.name = '{_matlab_string(analysis['conn_name'])}';",
            f"batch.Analysis.type = {_number(analysis['conn_type'])};",
            "batch.Analysis.measure = 1;",
            f"batch.Analysis.sources = {_cell([seed['conn_source'] for seed in seeds])};",
            "batch.Analysis.done = 1;",
            "batch.Analysis.overwrite = 0;",
            "",
            "conn_batch(batch);",
            "",
        ]
    )
    lines.extend(_render_extended_qc(run_dir))
    lines.extend(_render_qc_metrics(subjects, preprocessing, run_dir))
    lines.extend(_render_results(design["contrasts"], seeds, analysis["conn_name"]))
    lines.append("")
    return "\n".join(lines)


def _render_preprocessing_steps(
    preprocessing: dict[str, Any], slice_timing_action: str | None
) -> list[str]:
    pipeline = str(_value(preprocessing, "pipeline"))
    if slice_timing_action == "omit_slice_timing_correction":
        if pipeline != "default_mni":
            raise ValueError(
                "Slice-timing omission is only implemented for the default_mni pipeline"
            )
        steps = [
            "functional_label_as_original",
            "structural_label_as_original",
            "functional_centerruns",
            "structural_center",
            "functional_realign&unwarp",
            "functional_label_as_realigned",
            "functional_art",
            "functional_label_as_minprep",
            "functional_coregister_affine_reslice",
            "functional_label_as_subjectspace",
            "structural_label_as_subjectspace",
            "functional_load_from_minprep",
            "functional_segment&normalize_direct",
            "functional_label_as_mnispace",
            "structural_segment&normalize",
            "structural_label_as_mnispace",
            "functional_smooth",
            "functional_label_as_smoothed",
        ]
        return [
            "% Preflight decision: slice-timing correction omitted because exact BIDS metadata is unavailable.",
            f"batch.Setup.preprocessing.steps = {_cell(steps)};",
        ]
    if slice_timing_action not in {None, "apply_bids_slice_timing"}:
        raise ValueError(f"Unsupported slice-timing preflight action: {slice_timing_action}")
    return [
        f"batch.Setup.preprocessing.steps = '{_matlab_string(pipeline)}';",
        "batch.Setup.preprocessing.sliceorder = 'BIDS';",
    ]


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


def _render_extended_qc(run_dir: Path) -> list[str]:
    folder = _matlab_string((run_dir / "qc_extended").as_posix())
    return [
        "% Native CONN visual QA report",
        "clear qa_batch;",
        "qa_batch.filename = batch.filename;",
        f"qa_batch.QA.foldername = '{folder}';",
        "qa_batch.QA.plots = [1 2 3 10 9 11 12];",
        "qa_batch.QA.sets = 1;",
        "qa_batch.QA.conditions = {'rest'};",
        "conn_batch(qa_batch);",
        "",
    ]


def _render_qc_metrics(
    subjects: list[dict[str, Any]], preprocessing: dict[str, Any], run_dir: Path
) -> list[str]:
    """Export the ART values needed for auditable subject review as JSON."""
    lines = [
        "% Subject-level ART metrics",
        "clear qc_metrics qc_subjects;",
        "qc_metrics.schema_version = 'conn_pilot_subject_qc_v2';",
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
                "if numel(art_outlier_files) == 1",
                "    art_data = load(fullfile(art_outlier_files(1).folder, art_outlier_files(1).name), 'R');",
                f"    qc_subjects({index}).volume_count = size(art_data.R, 1);",
                f"    qc_subjects({index}).outlier_count = sum(any(abs(art_data.R) > eps, 2));",
                f"    qc_subjects({index}).outlier_percent = 100 * qc_subjects({index}).outlier_count / max(1, qc_subjects({index}).volume_count);",
                f"    qc_subjects({index}).retained_volume_count = qc_subjects({index}).volume_count - qc_subjects({index}).outlier_count;",
                "    art_flags = any(abs(art_data.R) > eps, 2)'; % acquired-volume order",
                "    art_edges = diff([false art_flags false]);",
                "    art_starts = find(art_edges == 1); art_ends = find(art_edges == -1) - 1;",
                f"    qc_subjects({index}).longest_outlier_streak = max([0 art_ends - art_starts + 1]);",
                "else",
                f"    qc_subjects({index}).volume_count = NaN;",
                f"    qc_subjects({index}).outlier_count = NaN;",
                f"    qc_subjects({index}).outlier_percent = NaN;",
                f"    qc_subjects({index}).retained_volume_count = NaN;",
                f"    qc_subjects({index}).longest_outlier_streak = NaN;",
                "end",
                "if numel(art_timeseries_files) == 1",
                "    art_series = load(fullfile(art_timeseries_files(1).folder, art_timeseries_files(1).name), 'R');",
                f"    qc_subjects({index}).global_signal_z_max = max(abs(art_series.R(:, 1)));",
                f"    qc_subjects({index}).motion_max_mm = max(abs(art_series.R(:, 2)));",
                f"    qc_subjects({index}).motion_mean_mm = mean(abs(art_series.R(:, 2)));",
                "else",
                f"    qc_subjects({index}).global_signal_z_max = NaN;",
                f"    qc_subjects({index}).motion_max_mm = NaN;",
                f"    qc_subjects({index}).motion_mean_mm = NaN;",
                "end",
                f"preprocessed_files = dir(fullfile('{_matlab_string(functional_dir)}', 'swa*.nii'));",
                "if numel(preprocessed_files) == 1",
                "    qc_volumes = spm_vol(fullfile(preprocessed_files(1).folder, preprocessed_files(1).name));",
                "    qc_first = spm_read_vols(qc_volumes(1));",
                "    qc_mask = isfinite(qc_first) & abs(qc_first) > eps;",
                "    qc_image_valid = numel(qc_volumes) > 1 && any(qc_mask(:));",
                "    qc_sum = zeros(size(qc_first)); qc_sumsq = zeros(size(qc_first));",
                "    qc_dvars = zeros(max(0, numel(qc_volumes)-1), 1); qc_previous = [];",
                "    for qc_index = 1:numel(qc_volumes)",
                "        qc_image = spm_read_vols(qc_volumes(qc_index));",
                "        qc_image_valid = qc_image_valid && all(isfinite(qc_image(qc_mask)));",
                "        qc_image(~isfinite(qc_image)) = 0;",
                "        qc_sum = qc_sum + qc_image; qc_sumsq = qc_sumsq + qc_image.^2;",
                "        if ~isempty(qc_previous), qc_delta = qc_image(qc_mask)-qc_previous(qc_mask); qc_dvars(qc_index-1)=sqrt(mean(qc_delta.^2)); end",
                "        qc_previous = qc_image;",
                "    end",
                "    qc_mean = qc_sum / max(1,numel(qc_volumes));",
                "    qc_variance = max(0,(qc_sumsq - numel(qc_volumes)*qc_mean.^2) / max(1,numel(qc_volumes)-1));",
                "    qc_tsnr = qc_mean(qc_mask) ./ sqrt(qc_variance(qc_mask)); qc_tsnr = qc_tsnr(isfinite(qc_tsnr));",
                f"    qc_subjects({index}).tsnr_median = median(qc_tsnr);",
                f"    qc_subjects({index}).dvars_mean = mean(qc_dvars);",
                f"    qc_subjects({index}).dvars_max = max(qc_dvars);",
                f"    if ~qc_image_valid, qc_subjects({index}).tsnr_median = NaN; qc_subjects({index}).dvars_mean = NaN; qc_subjects({index}).dvars_max = NaN; end",
                "else",
                f"    qc_subjects({index}).tsnr_median = NaN;",
                f"    qc_subjects({index}).dvars_mean = NaN;",
                f"    qc_subjects({index}).dvars_max = NaN;",
                "end",
            ]
        )
        for metric in (
            "volume_count", "outlier_count", "outlier_percent", "retained_volume_count",
            "longest_outlier_streak", "global_signal_z_max", "motion_max_mm",
            "motion_mean_mm", "tsnr_median", "dvars_mean", "dvars_max",
        ):
            lines.append(f"qc_subjects({index}).metric_availability.{metric} = isscalar(qc_subjects({index}).{metric}) && isfinite(qc_subjects({index}).{metric});")
        for metric in ("tsnr_median", "dvars_mean", "dvars_max"):
            lines.append(f"qc_subjects({index}).measurement_stage.{metric} = 'preprocessed_before_denoising';")
    metrics_path = _matlab_string((run_dir / "qc_metrics.json").as_posix())
    lines.extend(
        [
            "qc_metrics.subjects = qc_subjects;",
            f"qc_metrics_file = fopen('{metrics_path}', 'w');",
            "if qc_metrics_file < 0, error('CONN Pilot could not create qc_metrics.json'); end",
            "fprintf(qc_metrics_file, '%s', jsonencode(qc_metrics));",
            "fclose(qc_metrics_file);",
            "clear art_data art_series art_outlier_files art_timeseries_files art_image_files art_flags art_edges art_starts art_ends preprocessed_files qc_volumes qc_first qc_mask qc_sum qc_sumsq qc_dvars qc_previous qc_image qc_delta qc_mean qc_variance qc_tsnr qc_index qc_metrics_file qc_image_valid;",
            "",
        ]
    )
    return lines


def _render_results(
    contrasts: list[dict[str, Any]], seeds: list[dict[str, Any]], analysis_name: str
) -> list[str]:
    lines = ["% Second-level models"]
    sources = [seed["conn_source"] for seed in seeds]
    for index, contrast in enumerate(contrasts, start=1):
        variable = f"results_batch_{index}"
        lines.extend(
            [
                f"% Contrast: {_comment(contrast['name'])}",
                f"clear {variable};",
                f"{variable}.filename = batch.filename;",
                f"{variable}.Results.name = '{_matlab_string(analysis_name)}';",
                f"{variable}.Results.saveas = '{_matlab_string(safe_identifier(contrast['name']))}';",
                f"{variable}.Results.foldername = '{_matlab_string(analysis_name)}/{_matlab_string(safe_identifier(contrast['name']))}';",
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
