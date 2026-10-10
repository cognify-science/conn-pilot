from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .catalog import Catalog, ResolvedPipeline
from .environment import check_environment
from .errors import ConnPilotError
from .io import load_yaml, nested_get
from .jobs import JobStore, queue_project
from .project import ValidationResult, validate_project as validate_project_definition
from .pipeline_graph import build_node_execution_plan
from .preflight import build_execution_preflight
from .progress import build_job_progress


REQUEST_SCHEMA = "conn_pilot_operation_request_v1"
RESPONSE_SCHEMA = "conn_pilot_operation_response_v1"
OPERATION_NAMES = (
    "list_pipelines",
    "inspect_dataset",
    "validate_project",
    "generate_execution_plan",
    "submit_job",
    "get_job_status",
    "get_job_progress",
    "get_job_logs",
    "list_results",
    "get_qc_summary",
)


WorkerLauncher = Callable[[str, Path, Path, Path], int | None]


class OperationService:
    """Stable application boundary shared by CLI, future HTTP API, and MCP."""

    def __init__(
        self,
        *,
        catalog_root: str | Path,
        environment_path: str | Path,
        work_root: str | Path,
        worker_launcher: WorkerLauncher | None = None,
    ) -> None:
        self.catalog = Catalog(catalog_root)
        self.environment_path = Path(environment_path).resolve()
        self.work_root = Path(work_root).resolve()
        self.run_root = self.work_root / "runs"
        self.jobs_path = self.work_root / "jobs.sqlite3"
        self.store = JobStore(self.jobs_path)
        self.worker_launcher = worker_launcher or launch_worker

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        operation = str(request.get("operation", ""))
        try:
            if request.get("schema_version") != REQUEST_SCHEMA:
                raise ValueError(f"schema_version must be {REQUEST_SCHEMA}")
            if operation not in OPERATION_NAMES:
                raise ValueError(f"Unsupported operation: {operation}")
            arguments = request.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            handler = getattr(self, operation)
            return handler(**arguments)
        except (ConnPilotError, ValueError, KeyError, OSError, TypeError) as error:
            return _response(operation or "unknown", {}, ok=False, errors=[str(error)])

    def list_pipelines(self) -> dict[str, Any]:
        pipelines = self.catalog.list_pipelines()
        for record in pipelines:
            resolved = self.catalog.resolve(record["id"], record["version"])
            record["description"] = str(resolved.definition.get("description", ""))
            record["stage_count"] = len(resolved.stages)
            record["supported_designs"] = list(
                resolved.definition.get("project_contract", {}).get("design_types", [])
            )
        return _response("list_pipelines", {"pipelines": pipelines, "count": len(pipelines)})

    def inspect_dataset(self, project_path: str) -> dict[str, Any]:
        project_file, project, _ = self._load_project(project_path)
        dataset = project.get("dataset", {})
        root = Path(str(dataset.get("root", "")))
        declared_tr = dataset.get("tr_seconds")
        files: list[dict[str, Any]] = []
        sidecar_trs: list[float] = []
        paths_seen: Counter[str] = Counter()
        errors: list[str] = []
        warnings: list[str] = []
        if not root.is_dir():
            errors.append(f"Dataset root does not exist: {root}")
        for subject in project.get("subjects", []):
            if not isinstance(subject, dict):
                continue
            for modality in ("functional", "structural"):
                value = subject.get(modality, [])
                if not isinstance(value, list):
                    continue
                for raw_path in value:
                    path = Path(str(raw_path))
                    paths_seen[str(path.resolve())] += 1
                    record: dict[str, Any] = {
                        "subject_id": str(subject.get("id", "")),
                        "modality": modality,
                        "path": str(path),
                        "exists": path.is_file(),
                        "bytes": path.stat().st_size if path.is_file() else None,
                    }
                    if root.is_dir() and not path.resolve().is_relative_to(root.resolve()):
                        errors.append(f"Input file is outside dataset.root: {path}")
                    if not path.is_file():
                        errors.append(f"Missing {modality} file: {path}")
                    if modality == "functional":
                        sidecar = _nifti_sidecar(path)
                        record["sidecar"] = str(sidecar)
                        record["sidecar_exists"] = sidecar.is_file()
                        if sidecar.is_file():
                            try:
                                metadata = json.loads(sidecar.read_text(encoding="utf-8"))
                                sidecar_tr = metadata.get("RepetitionTime")
                                record["sidecar_tr_seconds"] = sidecar_tr
                                if isinstance(sidecar_tr, (int, float)) and not isinstance(sidecar_tr, bool):
                                    sidecar_trs.append(float(sidecar_tr))
                            except (json.JSONDecodeError, OSError) as error:
                                warnings.append(f"Could not read sidecar {sidecar}: {error}")
                    files.append(record)
        duplicates = sorted(path for path, count in paths_seen.items() if count > 1)
        if duplicates:
            errors.append("Input paths are assigned more than once")
        inconsistent_trs = sorted({value for value in sidecar_trs if value != float(declared_tr)}) if _number(declared_tr) else []
        if inconsistent_trs:
            errors.append(
                f"Functional sidecar RepetitionTime values {inconsistent_trs} do not match dataset.tr_seconds={declared_tr}"
            )
        missing_sidecars = sum(
            1 for item in files if item["modality"] == "functional" and not item.get("sidecar_exists")
        )
        if missing_sidecars:
            warnings.append(f"{missing_sidecars} functional file(s) have no JSON sidecar")
        data = {
            "project_path": str(project_file),
            "layout": dataset.get("layout"),
            "dataset_root": str(root),
            "dataset_root_exists": root.is_dir(),
            "declared_tr_seconds": declared_tr,
            "sidecar_tr_seconds": sorted(set(sidecar_trs)),
            "subject_count": len(project.get("subjects", [])),
            "file_count": len(files),
            "existing_file_count": sum(1 for item in files if item["exists"]),
            "total_input_bytes": sum(int(item["bytes"] or 0) for item in files),
            "duplicate_paths": duplicates,
            "files": files,
            "ready": not errors,
        }
        return _response("inspect_dataset", data, ok=not errors, errors=errors, warnings=warnings)

    def validate_project(self, project_path: str, check_paths: bool = True) -> dict[str, Any]:
        project_file, project, pipeline = self._load_project(project_path)
        result = validate_project_definition(project, pipeline, check_paths=check_paths)
        data = {
            "project_path": str(project_file),
            "valid": result.valid,
            "pipeline": _pipeline_identity(pipeline),
            "subject_count": len(project.get("subjects", [])),
            "seed_count": len(project.get("seeds", [])),
            "contrast_count": len(project.get("design", {}).get("contrasts", [])),
        }
        return _response(
            "validate_project", data, ok=result.valid, errors=list(result.errors), warnings=list(result.warnings)
        )

    def generate_execution_plan(self, project_path: str) -> dict[str, Any]:
        project_file, project, pipeline = self._load_project(project_path)
        validation = validate_project_definition(project, pipeline, check_paths=True)
        inspection = self.inspect_dataset(str(project_file))
        environment = self._environment_status()
        execution_preflight = build_execution_preflight(
            project, load_yaml(self.environment_path).get("execution", {})
        )
        errors = list(validation.errors) + list(inspection["errors"])
        warnings = list(validation.warnings) + list(inspection["warnings"])
        if not environment["valid"]:
            errors.append("Local MATLAB/SPM/CONN environment is invalid")
        if not execution_preflight["ready"]:
            decision = execution_preflight["checks"]["slice_timing"]["decision"]
            errors.append(
                "Execution preflight requires parameter resolution: "
                + str(decision.get("reason", "unresolved execution requirement"))
            )
        parameters: list[dict[str, Any]] = []
        for path, specification in pipeline.definition["project_contract"].get("parameters", {}).items():
            record = nested_get(project.get("parameters", {}), path, {})
            parameters.append(
                {
                    "path": path,
                    "value": record.get("value") if isinstance(record, dict) else None,
                    "maps_to": specification.get("maps_to"),
                    "confirmed_by_investigator": (
                        record.get("confirmed_by_investigator") if isinstance(record, dict) else False
                    ),
                }
            )
        stages = [
            {
                "order": index,
                "id": str(stage["id"]),
                "version": str(stage["version"]),
                "requires": list(stage.get("requires", [])),
                "provides": list(stage.get("provides", [])),
            }
            for index, stage in enumerate(pipeline.stages, start=1)
        ]
        data = {
            "project_path": str(project_file),
            "project": project.get("project", {}),
            "pipeline": _pipeline_identity(pipeline),
            "execution": {
                "mode": "local_matlab_batch",
                "concurrency": 1,
                "input_policy": "writable_copies_in_run_directory",
                "subject_count": len(project.get("subjects", [])),
                "session_count": len(project.get("subjects", [])),
            },
            "dataset_inspection": {
                key: inspection["data"].get(key)
                for key in (
                    "dataset_root",
                    "dataset_root_exists",
                    "declared_tr_seconds",
                    "sidecar_tr_seconds",
                    "subject_count",
                    "file_count",
                    "existing_file_count",
                    "total_input_bytes",
                    "duplicate_paths",
                    "ready",
                )
            },
            "execution_preflight": execution_preflight,
            "stages": stages,
            "node_execution_plan": build_node_execution_plan(project, pipeline),
            "parameters": parameters,
            "seeds": project.get("seeds", []),
            "design": project.get("design", {}),
            "environment": environment,
            "ready_to_submit": not errors,
        }
        return _response(
            "generate_execution_plan", data, ok=not errors, errors=errors, warnings=warnings
        )

    def submit_job(self, project_path: str) -> dict[str, Any]:
        project_file, project, pipeline = self._load_project(project_path)
        validation = validate_project_definition(project, pipeline, check_paths=True)
        if not validation.valid:
            return _response(
                "submit_job", {}, ok=False, errors=list(validation.errors), warnings=list(validation.warnings)
            )
        inspection = self.inspect_dataset(str(project_file))
        if not inspection["ok"]:
            return _response(
                "submit_job",
                {},
                ok=False,
                errors=list(inspection["errors"]),
                warnings=list(validation.warnings) + list(inspection["warnings"]),
            )
        environment = self._environment_status()
        if not environment["valid"]:
            return _response(
                "submit_job", {}, ok=False, errors=["Local MATLAB/SPM/CONN environment is invalid"]
            )
        execution_preflight = build_execution_preflight(
            project, load_yaml(self.environment_path).get("execution", {})
        )
        if not execution_preflight["ready"]:
            decision = execution_preflight["checks"]["slice_timing"]["decision"]
            return _response(
                "submit_job",
                {"execution_preflight": execution_preflight},
                ok=False,
                errors=[
                    "Execution preflight requires parameter resolution: "
                    + str(decision.get("reason", "unresolved execution requirement"))
                ],
            )
        job = queue_project(project, project_file, self.store, self.run_root)
        try:
            worker_pid = self.worker_launcher(
                str(job["id"]), self.environment_path, self.jobs_path, Path(job["run_dir"])
            )
        except Exception as error:
            self.store.update(str(job["id"]), "failed", error=f"Could not start local worker: {error}")
            return _response("submit_job", {"job": self.store.get(str(job["id"]))}, ok=False, errors=[str(error)])
        job = self.store.get(str(job["id"])) or job
        return _response(
            "submit_job",
            {"job": job, "worker_pid": worker_pid},
            warnings=list(validation.warnings) + list(inspection["warnings"]),
        )

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        job = self._job(job_id)
        data = {"job": job, "phase": _infer_phase(job), "terminal": job["state"] in {"succeeded", "failed"}}
        return _response("get_job_status", data, ok=job["state"] != "failed", errors=[job["error"]] if job["error"] else [])

    def get_job_progress(self, job_id: str) -> dict[str, Any]:
        job = self._job(job_id)
        run_dir = Path(job["run_dir"])
        project_path = run_dir / "project.execution.yaml"
        if not project_path.is_file():
            project_path = run_dir / "project.request.yaml"
        if not project_path.is_file():
            return _response(
                "get_job_progress",
                {
                    "job_id": job_id,
                    "state": job["state"],
                    "phase": _infer_phase(job),
                    "progress": None,
                },
                warnings=["The immutable project snapshot is not available yet"],
            )
        project = load_yaml(project_path)
        progress = build_job_progress(job, project, phase=_infer_phase(job))
        warnings = []
        if progress["activity"]["state"] == "stale" and job["state"] == "running":
            warnings.append(
                "No output activity has been observed for more than 30 minutes; inspect logs before deciding whether the job is stalled."
            )
        return _response("get_job_progress", {"job_id": job_id, "progress": progress}, warnings=warnings)

    def get_job_logs(self, job_id: str, stream: str = "all", tail: int = 200) -> dict[str, Any]:
        if stream not in {"all", "stdout", "stderr", "worker"}:
            raise ValueError("stream must be all, stdout, stderr, or worker")
        if not isinstance(tail, int) or not 1 <= tail <= 2000:
            raise ValueError("tail must be an integer from 1 to 2000")
        job = self._job(job_id)
        run_dir = Path(job["run_dir"])
        selected = {
            "stdout": ["matlab_stdout.log"],
            "stderr": ["matlab_stderr.log"],
            "worker": ["worker_stdout.log", "worker_stderr.log"],
            "all": ["worker_stdout.log", "worker_stderr.log", "matlab_stdout.log", "matlab_stderr.log"],
        }[stream]
        logs: list[dict[str, Any]] = []
        for name in selected:
            path = run_dir / name
            lines = _tail_lines(path, tail) if path.is_file() else []
            logs.append(
                {
                    "name": name,
                    "path": str(path),
                    "exists": path.is_file(),
                    "bytes": path.stat().st_size if path.is_file() else 0,
                    "lines": lines,
                }
            )
        return _response("get_job_logs", {"job_id": job_id, "state": job["state"], "logs": logs})

    def list_results(self, job_id: str) -> dict[str, Any]:
        job = self._job(job_id)
        path = Path(job["run_dir"]) / "artifacts.json"
        warnings: list[str] = []
        if path.is_file():
            artifacts = json.loads(path.read_text(encoding="utf-8"))
        else:
            artifacts = {"groups": {}, "counts": {}}
            warnings.append("Artifact manifest is not available yet")
        return _response(
            "list_results",
            {"job_id": job_id, "state": job["state"], "manifest_path": str(path), "artifacts": artifacts},
            warnings=warnings,
        )

    def get_qc_summary(self, job_id: str) -> dict[str, Any]:
        job = self._job(job_id)
        run_dir = Path(job["run_dir"])
        path = run_dir / "artifacts.json"
        artifacts = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"groups": {}, "counts": {}}
        counts = artifacts.get("counts", {})
        groups = artifacts.get("groups", {})
        metrics_path = run_dir / "qc_metrics.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.is_file() else {}
        metric_subjects = metrics.get("subjects", [])
        if isinstance(metric_subjects, dict):
            metric_subjects = [metric_subjects]
        subject_files: dict[str, dict[str, Any]] = {
            str(item["subject_id"]): {
                "qc_images": 0,
                "preprocessing_qc": 0,
                "metrics": {key: value for key, value in item.items() if key != "subject_id"},
                "art_images": [],
            }
            for item in metric_subjects
            if isinstance(item, dict) and item.get("subject_id")
        }
        for group_name in ("qc_images", "preprocessing_qc"):
            for item in groups.get(group_name, []):
                parts = Path(item.get("relative_path", "")).parts
                subject_id = _subject_from_parts(parts)
                if subject_id:
                    record = subject_files.setdefault(
                        subject_id,
                        {"qc_images": 0, "preprocessing_qc": 0, "metrics": {}, "art_images": []},
                    )
                    record[group_name] += 1
                    if group_name == "qc_images":
                        record["art_images"].append(item)
        warnings: list[str] = []
        if not path.is_file():
            warnings.append("QC artifacts are not available yet")
        if job["state"] == "succeeded" and not counts.get("qc_images", 0):
            warnings.append("The completed job contains no indexed QC images")
        technical_complete = bool(
            job["state"] == "succeeded"
            and counts.get("first_level_maps", 0)
            and counts.get("second_level_maps", 0)
            and counts.get("preprocessing_qc", 0)
        )
        data = {
            "job_id": job_id,
            "job_state": job["state"],
            "technical_completeness": {
                "passed": technical_complete,
                "artifact_counts": counts,
            },
            "art_thresholds": metrics.get("thresholds", {}),
            "subjects": [
                {"subject_id": subject_id, **values} for subject_id, values in sorted(subject_files.items())
            ],
            "qc_images": groups.get("qc_images", []),
            "scientific_qc": {
                "automatic_decision": None,
                "review_required": True,
                "reason": "This version indexes QC evidence but does not approve or exclude subjects automatically.",
            },
        }
        return _response("get_qc_summary", data, warnings=warnings)

    def _load_project(self, project_path: str) -> tuple[Path, dict[str, Any], ResolvedPipeline]:
        path = Path(project_path).resolve()
        project = load_yaml(path)
        reference = project.get("pipeline", {})
        pipeline = self.catalog.resolve(str(reference.get("id", "")), str(reference.get("version", "")))
        return path, project, pipeline

    def _environment_status(self) -> dict[str, Any]:
        return check_environment(load_yaml(self.environment_path), probe_matlab=False)

    def _job(self, job_id: str) -> dict[str, Any]:
        job = self.store.get(job_id)
        if not job:
            raise ValueError(f"Unknown job: {job_id}")
        return job


def launch_worker(job_id: str, environment_path: Path, jobs_path: Path, run_dir: Path) -> int:
    """Launch a detached local worker and return its process id."""
    command = [
        sys.executable,
        "-B",
        "-m",
        "conn_pilot",
        "worker",
        job_id,
        "--environment",
        str(environment_path),
        "--jobs-db",
        str(jobs_path),
    ]
    process_environment = dict(os.environ)
    source_root = Path(__file__).resolve().parents[1]
    current_pythonpath = process_environment.get("PYTHONPATH", "")
    process_environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(source_root), current_pythonpath) if part
    )
    flags = 0
    kwargs: dict[str, Any] = {"cwd": str(source_root.parent), "env": process_environment}
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "worker_stdout.log").open("a", encoding="utf-8") as stdout, (
        run_dir / "worker_stderr.log"
    ).open("a", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, **kwargs)
    return process.pid


def _response(
    operation: str,
    data: dict[str, Any],
    *,
    ok: bool = True,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA,
        "operation": operation,
        "ok": ok,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
        "errors": errors or [],
        "warnings": warnings or [],
    }


def _pipeline_identity(pipeline: ResolvedPipeline) -> dict[str, Any]:
    return {
        "id": pipeline.id,
        "version": pipeline.version,
        "family": pipeline.definition.get("family"),
        "status": pipeline.definition.get("status"),
    }


def _nifti_sidecar(path: Path) -> Path:
    name = path.name
    if name.endswith(".nii.gz"):
        return path.with_name(name[:-7] + ".json")
    return path.with_suffix(".json")


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _tail_lines(path: Path, count: int) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace").replace("\b", "")
    return text.splitlines()[-count:]


def _infer_phase(job: dict[str, Any]) -> str:
    if job["state"] != "running":
        return str(job["state"])
    log_path = Path(job["run_dir"]) / "matlab_stdout.log"
    if not log_path.is_file():
        return "starting_matlab"
    text = log_path.read_text(encoding="utf-8", errors="replace")[-250_000:].lower()
    markers = (
        ("second-level", "second_level"),
        ("running analysis step", "first_level"),
        ("running denoising step", "denoising"),
        ("running setup step", "setup"),
        ("running setup.preprocessing", "preprocessing"),
    )
    for marker, phase in markers:
        if marker in text:
            return phase
    return "matlab_running"


def _subject_from_parts(parts: tuple[str, ...]) -> str | None:
    for part in parts:
        if part.lower().startswith("sub-"):
            return part
    return None
