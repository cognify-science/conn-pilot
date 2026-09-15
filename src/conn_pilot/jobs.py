from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapter import generate_conn_batch
from .environment import _matlab_environment
from .errors import ExecutionError
from .io import sha256_file, write_json, write_yaml
from .project import safe_identifier
from .results import collect_artifacts
from .staging import stage_project_inputs


FINAL_STATES = {"succeeded", "failed"}


class JobStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    pipeline_id TEXT NOT NULL,
                    pipeline_version TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    run_dir TEXT NOT NULL,
                    batch_path TEXT,
                    return_code INTEGER,
                    error TEXT
                )
                """
            )

    def create(self, project: dict[str, Any], run_dir: Path) -> str:
        job_id = uuid.uuid4().hex
        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute(
                "SELECT id FROM jobs WHERE state IN ('queued', 'preparing', 'running') LIMIT 1"
            ).fetchone()
            if active:
                raise ExecutionError(f"Another CONN job is active: {active['id']}")
            connection.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)",
                (
                    job_id,
                    str(project["project"]["name"]),
                    str(project["pipeline"]["id"]),
                    str(project["pipeline"]["version"]),
                    "queued",
                    now,
                    now,
                    str(run_dir),
                ),
            )
        return job_id

    def update(self, job_id: str, state: str, **fields: Any) -> None:
        allowed = {"batch_path", "return_code", "error"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown job fields: {unknown}")
        assignments = ["state = ?", "updated_at = ?"]
        values: list[Any] = [state, _now()]
        for key, value in fields.items():
            assignments.append(f"{key} = ?")
            values.append(value)
        values.append(job_id)
        with self._connect() as connection:
            connection.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?", values)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]


def run_project(
    project: dict[str, Any],
    project_path: Path,
    environment: dict[str, Any],
    store: JobStore,
    run_root: Path,
) -> dict[str, Any]:
    project_name = safe_identifier(project["project"]["name"])
    provisional = run_root / project_name / "pending"
    job_id = store.create(project, provisional)
    run_dir = run_root / project_name / job_id
    with store._connect() as connection:
        connection.execute("UPDATE jobs SET run_dir = ? WHERE id = ?", (str(run_dir), job_id))
    return_code: int | None = None
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
        store.update(job_id, "preparing")
        request_snapshot = run_dir / "project.request.yaml"
        shutil.copy2(project_path, request_snapshot)
        execution_project, staged_inputs = stage_project_inputs(project, run_dir)
        snapshot = run_dir / "project.execution.yaml"
        write_yaml(snapshot, execution_project)
        batch_path = generate_conn_batch(execution_project, snapshot, run_dir)
        store.update(job_id, "running", batch_path=str(batch_path))
        stdout_path = run_dir / "matlab_stdout.log"
        stderr_path = run_dir / "matlab_stderr.log"
        matlab = environment["matlab"]["executable"]
        spm = Path(environment["spm"]["root"]).as_posix()
        conn = Path(environment["conn"]["root"]).as_posix()
        batch = batch_path.as_posix().replace("'", "''")
        expression = f"addpath('{spm}'); addpath('{conn}'); run('{batch}');"
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            completed = subprocess.run(
                [str(matlab), "-batch", expression],
                stdout=stdout,
                stderr=stderr,
                text=True,
                env=_matlab_environment(environment),
            )
        return_code = completed.returncode
        if return_code != 0:
            raise ExecutionError(f"MATLAB exited with code {return_code}")
        verification = verify_outputs(execution_project, run_dir)
        if not verification["valid"]:
            raise ExecutionError("Expected CONN outputs are missing: " + ", ".join(verification["missing"]))
        artifacts = collect_artifacts(execution_project, run_dir)
        manifest = build_manifest(project, request_snapshot, snapshot, batch_path, environment, verification, staged_inputs)
        manifest["artifacts"] = artifacts["counts"]
        write_json(run_dir / "manifest.json", manifest)
        store.update(job_id, "succeeded", return_code=return_code)
    except Exception as error:
        store.update(job_id, "failed", return_code=return_code, error=str(error))
        raise
    return store.get(job_id) or {}


def verify_outputs(project: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    name = safe_identifier(project["project"]["name"])
    project_dir = run_dir / name
    expected = {
        "conn_project": run_dir / f"{name}.mat",
        "first_level": project_dir / "results" / "firstlevel" / "SBC_01",
        "second_level": project_dir / "results" / "secondlevel" / "SBC_01",
    }
    missing = [key for key, path in expected.items() if not path.exists()]
    return {
        "valid": not missing,
        "missing": missing,
        "paths": {key: str(path) for key, path in expected.items()},
    }


def build_manifest(
    project: dict[str, Any],
    request_snapshot: Path,
    execution_snapshot: Path,
    batch_path: Path,
    environment: dict[str, Any],
    verification: dict[str, Any],
    staged_inputs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "conn_pilot_run_manifest_v0.1",
        "created_at": _now(),
        "project": project["project"],
        "pipeline": project["pipeline"],
        "environment": {
            "matlab": environment["matlab"].get("release"),
            "spm": environment["spm"].get("version"),
            "conn": environment["conn"].get("version"),
        },
        "inputs": {
            "request_project_yaml": {"path": str(request_snapshot), "sha256": sha256_file(request_snapshot)},
            "execution_project_yaml": {"path": str(execution_snapshot), "sha256": sha256_file(execution_snapshot)},
            "batch": {"path": str(batch_path), "sha256": sha256_file(batch_path)},
            "staged_files": staged_inputs,
        },
        "outputs": verification,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
