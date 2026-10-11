from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .control_plane import materialize_remote_project
from .io import load_yaml, sha256_file, write_json, write_yaml
from .mcp_server import build_operation_service
from .preflight import load_bids_metadata
from .second_level import run_second_level_recalculation


class LocalCapacityBusy(RuntimeError):
    """A local CONN execution still owns the single execution slot."""


class SupervisorLock:
    """Cross-process singleton lock for the distributed supervisor."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.handle: Any = None

    def __enter__(self) -> SupervisorLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.handle.write(b"0")
            self.handle.flush()
            os.fsync(self.handle.fileno())
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            self.handle.close()
            self.handle = None
            raise RuntimeError("Another distributed worker supervisor is already running")
        return self

    def __exit__(self, *_args: Any) -> None:
        if not self.handle:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def load_registry(path: str | Path) -> dict[str, dict[str, Any]]:
    value = load_yaml(path)
    if value.get("schema_version") != "conn_pilot_dataset_registry_v1":
        raise ValueError("Dataset registry schema_version must be conn_pilot_dataset_registry_v1")
    datasets = value.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("Dataset registry must contain at least one dataset")
    result: dict[str, dict[str, Any]] = {}
    for item in datasets:
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError("Every registered dataset requires an id")
        dataset_id = str(item["id"])
        if dataset_id in result:
            raise ValueError(f"Duplicate dataset id: {dataset_id}")
        result[dataset_id] = normalize_local_dataset(item)
    return result


def normalize_local_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    root = Path(str(dataset.get("root", ""))).resolve()
    subjects = dataset.get("subjects", [])
    if not root.is_dir():
        raise ValueError(f"Dataset root does not exist: {root}")
    if not isinstance(subjects, list) or not subjects:
        raise ValueError(f"Dataset {dataset.get('id')} has no subjects")
    normalized_subjects: list[dict[str, Any]] = []
    for subject in subjects:
        if not isinstance(subject, dict) or not subject.get("id"):
            raise ValueError("Every dataset subject requires an id")
        normalized: dict[str, Any] = {"id": str(subject["id"])}
        for modality in ("functional", "structural"):
            values = subject.get(modality, [])
            if not isinstance(values, list) or len(values) != 1:
                raise ValueError(f"{subject['id']}.{modality} must contain exactly one path")
            path = Path(str(values[0]))
            if not path.is_absolute():
                path = root / path
            path = path.resolve()
            if not path.is_relative_to(root):
                raise ValueError(f"Dataset file is outside its root: {path}")
            normalized[modality] = [str(path)]
        normalized_subjects.append(normalized)
    normalized_dataset = {
        "id": str(dataset["id"]),
        "label": str(dataset.get("label", dataset["id"])),
        "root": str(root),
        "layout": str(dataset.get("layout", "bids")),
        "tr_seconds": dataset.get("tr_seconds"),
        "subjects": normalized_subjects,
    }
    normalized_dataset["acquisition_metadata"] = inspect_acquisition_metadata(
        normalized_dataset
    )
    return normalized_dataset


def inspect_acquisition_metadata(dataset: dict[str, Any]) -> dict[str, Any]:
    """Create a path-free inventory of acquisition metadata needed by CONN."""
    root = Path(str(dataset["root"]))
    records: list[dict[str, Any]] = []
    for subject in dataset["subjects"]:
        available = True
        unreadable = False
        source_count = 0
        for raw_path in subject["functional"]:
            try:
                metadata, sources = load_bids_metadata(Path(raw_path), root)
                timing = metadata.get("SliceTiming")
                available = available and bool(isinstance(timing, list) and timing)
                source_count += len(sources)
            except ValueError:
                available = False
                unreadable = True
        records.append(
            {
                "subject_id": subject["id"],
                "slice_timing_available": available,
                "metadata_source_count": source_count,
                "metadata_unreadable": unreadable,
            }
        )
    missing = [record["subject_id"] for record in records if not record["slice_timing_available"]]
    unreadable = [record["subject_id"] for record in records if record["metadata_unreadable"]]
    return {
        "schema_version": "conn_pilot_acquisition_metadata_v1",
        "slice_timing": {
            "status": "complete" if not missing else "missing",
            "available_count": len(records) - len(missing),
            "subject_count": len(records),
            "missing_subject_ids": missing,
            "unreadable_subject_ids": unreadable,
            "requires_resolution_for_default_mni": bool(missing),
            "available_options": (
                []
                if not missing
                else [
                    "provide_exact_slice_timing",
                    "retrieve_exact_acquisition_order_from_dataset_documentation_or_literature",
                    "omit_slice_timing_correction",
                ]
            ),
        },
    }


def inventory_record(dataset: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    ready = True
    for subject in dataset["subjects"]:
        digest.update(subject["id"].encode())
        for modality in ("functional", "structural"):
            for raw_path in subject[modality]:
                path = Path(raw_path)
                relative = path.relative_to(Path(dataset["root"]))
                digest.update(relative.as_posix().encode())
                if path.is_file():
                    stat = path.stat()
                    file_count += 1
                    total_bytes += stat.st_size
                    digest.update(str(stat.st_size).encode())
                    digest.update(str(stat.st_mtime_ns).encode())
                else:
                    ready = False
                    digest.update(b"missing")
    return {
        "id": dataset["id"],
        "label": dataset["label"],
        "fingerprint": f"sha256:{digest.hexdigest()}",
        "status": "ready" if ready else "incomplete",
        "metadata": {
            "layout": dataset["layout"],
            "tr_seconds": dataset["tr_seconds"],
            "subjects": [{"id": item["id"]} for item in dataset["subjects"]],
            "subject_count": len(dataset["subjects"]),
            "file_count": file_count,
            "total_bytes": total_bytes,
            "acquisition_metadata": dataset["acquisition_metadata"],
        },
    }


class WorkerClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int = 60,
        *,
        retry_attempts: int | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if len(token) < 32:
            raise ValueError("Worker token must contain at least 32 characters")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.sleeper = sleeper

    def _retry(self, attempt: int, error: Exception) -> None:
        if self.retry_attempts is not None and attempt >= self.retry_attempts:
            raise RuntimeError(f"Control plane is unavailable after {attempt} attempts: {error}") from error
        self.sleeper(min(30.0, float(2 ** min(attempt - 1, 5))))

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        attempt = 0
        while True:
            attempt += 1
            request = urllib.request.Request(
                f"{self.base_url}{path}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    value = json.load(response)
                break
            except urllib.error.HTTPError as error:
                if error.code not in {408, 425, 429} and error.code < 500:
                    body = error.read().decode("utf-8", errors="replace")
                    raise RuntimeError(
                        f"Control plane returned HTTP {error.code}: {body[:500]}"
                    ) from error
                self._retry(attempt, error)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                self._retry(attempt, error)
        if not isinstance(value, dict):
            raise RuntimeError("Control plane returned a non-object response")
        return value

    def upload(self, url: str, path: Path, content_type: str) -> None:
        payload = path.read_bytes()
        attempt = 0
        while True:
            attempt += 1
            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": content_type},
                method="PUT",
            )
            try:
                with urllib.request.urlopen(request, timeout=max(self.timeout, 300)):
                    return
            except urllib.error.HTTPError as error:
                if error.code not in {408, 425, 429} and error.code < 500:
                    body = error.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"Artifact upload returned HTTP {error.code}: {body[:500]}") from error
                self._retry(attempt, error)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                self._retry(attempt, error)


class DistributedWorker:
    def __init__(
        self,
        *,
        client: WorkerClient,
        worker_id: str,
        label: str,
        registry: dict[str, dict[str, Any]],
        work_root: str | Path,
        heartbeat_seconds: int = 30,
        max_artifact_bytes: int = 250 * 1024 * 1024,
    ) -> None:
        self.client = client
        self.worker_id = worker_id
        self.label = label
        self.registry = registry
        self.work_root = Path(work_root).resolve()
        self.heartbeat_seconds = heartbeat_seconds
        self.max_artifact_bytes = max_artifact_bytes

    def heartbeat(self) -> dict[str, Any]:
        environment = build_operation_service()._environment_status()
        return self.client.post(
            "/worker/v1/heartbeat",
            {
                "worker_id": self.worker_id,
                "label": self.label,
                "capabilities": {
                    "matlab": environment.get("versions", {}).get("matlab"),
                    "spm": environment.get("versions", {}).get("spm"),
                    "conn": environment.get("versions", {}).get("conn"),
                    "environment_valid": environment.get("valid", False),
                    "concurrency": 1,
                },
                "datasets": [inventory_record(value) for value in self.registry.values()],
            },
        )

    def claim(self) -> dict[str, Any] | None:
        response = self.client.post(
            "/worker/v1/claim",
            {"worker_id": self.worker_id, "dataset_ids": sorted(self.registry)},
        )
        return response.get("job")

    def claim_second_level(self) -> dict[str, Any] | None:
        response = self.client.post(
            "/worker/v1/second-level/claim",
            {"worker_id": self.worker_id, "dataset_ids": sorted(self.registry)},
        )
        return response.get("second_level_run")

    def run_job(self, remote_job: dict[str, Any]) -> None:
        remote_job_id = str(remote_job["id"])
        dataset_id = str(remote_job["dataset_id"])
        dataset = self.registry.get(dataset_id)
        if not dataset:
            self._complete(remote_job_id, "failed", {}, f"Dataset is not registered locally: {dataset_id}")
            return
        remote_project = dict(remote_job["project"])
        local_dataset = {
            "id": dataset_id,
            "metadata": {
                "root": dataset["root"],
                "layout": dataset["layout"],
                "tr_seconds": dataset["tr_seconds"],
                "subjects": dataset["subjects"],
            },
        }
        project_definition = materialize_remote_project(remote_project, local_dataset, use_placeholders=False)
        remote_dir = self.work_root / "remote" / remote_job_id
        snapshot_path = remote_dir / "remote-job.json"
        recovery_path = remote_dir / "recovery-state.json"
        self._write_json_atomic(snapshot_path, remote_job)
        recovery = self._read_recovery_state(recovery_path, remote_job_id)
        self._write_recovery_state(
            recovery_path,
            remote_job_id,
            "running",
            local_job_id=recovery.get("local_job_id"),
            recovery_count=int(recovery.get("recovery_count", 0) or 0),
            last_error=recovery.get("last_error"),
        )
        project_path = remote_dir / "project.yaml"
        write_yaml(project_path, project_definition)
        service = build_operation_service()
        state_path = remote_dir / "worker-state.json"
        while True:
            local_job_id = self._restored_local_job_id(state_path, service)
            if not local_job_id:
                submitted = service.submit_job(str(project_path))
                if not submitted["ok"]:
                    errors = sanitize_for_remote(
                        submitted["errors"], [dataset["root"], str(self.work_root)]
                    )
                    message = "; ".join(str(item) for item in errors)
                    if "Another CONN job is active" in message:
                        self._reconcile_local_slot(service)
                        self._write_recovery_state(
                            recovery_path,
                            remote_job_id,
                            "running",
                            recovery_count=int(recovery.get("recovery_count", 0) or 0),
                            last_error=message,
                        )
                        self._heartbeat_waiting(remote_job_id, message)
                        raise LocalCapacityBusy(message)
                    self._complete(
                        remote_job_id,
                        "failed",
                        {"submission_errors": errors},
                        message,
                    )
                    self._write_recovery_state(
                        recovery_path,
                        remote_job_id,
                        "permanent_failed",
                        recovery_count=int(recovery.get("recovery_count", 0) or 0),
                        last_error=message,
                    )
                    return
                local_job_id = str(submitted["data"]["job"]["id"])
                self._write_worker_state(state_path, remote_job_id, local_job_id)
                self._write_recovery_state(
                    recovery_path,
                    remote_job_id,
                    "running",
                    local_job_id=local_job_id,
                    recovery_count=int(recovery.get("recovery_count", 0) or 0),
                )
            else:
                # Repair a missing/corrupt link after conservative process-based reassociation.
                self._write_worker_state(state_path, remote_job_id, local_job_id)
                self._write_recovery_state(
                    recovery_path,
                    remote_job_id,
                    "running",
                    local_job_id=local_job_id,
                    recovery_count=int(recovery.get("recovery_count", 0) or 0),
                    last_error=recovery.get("last_error"),
                )

            last_heartbeat = 0.0
            restart_local = False
            while True:
                status = service.get_job_status(local_job_id)
                job = status["data"]["job"]
                now = time.monotonic()
                if now - last_heartbeat >= self.heartbeat_seconds and not status["data"]["terminal"]:
                    if (
                        self._orphan_check_due(job)
                        and _local_job_has_live_process(job) is False
                    ):
                        message = (
                            "Recovered interrupted local execution: persisted state was active "
                            "but no matching CONN worker or MATLAB process was running"
                        )
                        service.store.update(local_job_id, "failed", error=message)
                        recovery["recovery_count"] = int(
                            recovery.get("recovery_count", 0) or 0
                        ) + 1
                        recovery["last_error"] = message
                        self._write_recovery_state(
                            recovery_path,
                            remote_job_id,
                            "running",
                            recovery_count=recovery["recovery_count"],
                            last_error=message,
                        )
                        state_path.unlink(missing_ok=True)
                        restart_local = True
                        break
                    progress = service.get_job_progress(local_job_id)
                    progress_payload = sanitize_for_remote(
                        progress["data"].get("progress"),
                        [dataset["root"], str(self.work_root)],
                    )
                    if not isinstance(progress_payload, dict):
                        progress_payload = {}
                    progress_payload["recovery"] = {
                        "state": "running",
                        "local_job_id": local_job_id,
                        "restart_count": int(recovery.get("recovery_count", 0) or 0),
                        "last_interruption": recovery.get("last_error"),
                    }
                    self.client.post(
                        f"/worker/v1/jobs/{remote_job_id}/heartbeat",
                        {
                            "worker_id": self.worker_id,
                            "phase": status["data"]["phase"],
                            "progress": progress_payload,
                        },
                    )
                    last_heartbeat = now
                if status["data"]["terminal"]:
                    break
                time.sleep(min(5, self.heartbeat_seconds))
            if restart_local:
                continue
            if job["state"] != "succeeded":
                error = str(job.get("error") or "Local CONN execution failed")
                if self._recoverable_local_failure(error):
                    recovery["recovery_count"] = int(
                        recovery.get("recovery_count", 0) or 0
                    ) + 1
                    recovery["last_error"] = error
                    self._write_recovery_state(
                        recovery_path,
                        remote_job_id,
                        "running",
                        recovery_count=recovery["recovery_count"],
                        last_error=error,
                    )
                    state_path.unlink(missing_ok=True)
                    continue
                self._complete(
                    remote_job_id,
                    "failed",
                    {"local_job_id": local_job_id},
                    error,
                )
                self._write_recovery_state(
                    recovery_path,
                    remote_job_id,
                    "permanent_failed",
                    local_job_id=local_job_id,
                    recovery_count=int(recovery.get("recovery_count", 0) or 0),
                    last_error=error,
                )
                return
            break

        self._write_recovery_state(
            recovery_path,
            remote_job_id,
            "publishing",
            local_job_id=local_job_id,
            recovery_count=int(recovery.get("recovery_count", 0) or 0),
        )
        results = service.list_results(local_job_id)
        qc = service.get_qc_summary(local_job_id)
        run_dir = Path(job["run_dir"])
        audit_path = run_dir / "scientific_audit.json"
        scientific_audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.is_file() else {}
        upload_summary = self._upload_selected(remote_job_id, run_dir, results["data"].get("artifacts", {}))
        self._complete(
            remote_job_id,
            "succeeded",
            {
                "local_job_id": local_job_id,
                "qc": sanitize_for_remote(qc["data"], [dataset["root"], str(self.work_root)]),
                "artifact_counts": results["data"].get("artifacts", {}).get("counts", {}),
                "uploads": upload_summary,
                "scientific_audit": scientific_audit,
            },
            None,
        )
        self._write_recovery_state(
            recovery_path,
            remote_job_id,
            "completed",
            local_job_id=local_job_id,
            recovery_count=int(recovery.get("recovery_count", 0) or 0),
        )

    def recover_pending_job(self) -> bool:
        """Resume the durable local intent before contacting the control-plane queue."""
        remote_root = self.work_root / "remote"
        if not remote_root.is_dir():
            return False
        candidates: list[tuple[float, Path, dict[str, Any]]] = []
        for path in remote_root.glob("*/recovery-state.json"):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if state.get("state") not in {"running", "publishing"}:
                continue
            snapshot = path.parent / "remote-job.json"
            if not snapshot.is_file():
                continue
            candidates.append((path.stat().st_mtime, snapshot, state))
        if not candidates:
            return False
        _, snapshot_path, _ = max(candidates, key=lambda item: item[0])
        remote_job = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.run_job(remote_job)
        return True

    def recover_pending_second_level(self) -> bool:
        root = self.work_root / "second-level"
        if not root.is_dir():
            return False
        candidates: list[tuple[float, Path]] = []
        for path in root.glob("*/recovery-state.json"):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if state.get("state") not in {"running", "publishing"}:
                continue
            snapshot = path.parent / "task.json"
            if snapshot.is_file():
                candidates.append((path.stat().st_mtime, snapshot))
        if not candidates:
            return False
        _, snapshot = max(candidates, key=lambda item: item[0])
        task = json.loads(snapshot.read_text(encoding="utf-8"))
        try:
            self.run_second_level(task)
        except Exception as error:
            run_id = str(task["id"])
            self._complete_second_level(
                run_id, "failed", {}, f"Worker error: {error}"
            )
            self._write_recovery_state(
                snapshot.parent / "recovery-state.json",
                run_id,
                "permanent_failed",
                last_error=str(error),
            )
        return True

    @staticmethod
    def _read_recovery_state(path: Path, remote_job_id: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"remote_job_id": remote_job_id, "recovery_count": 0}
        return value if isinstance(value, dict) else {"remote_job_id": remote_job_id}

    @staticmethod
    def _write_json_atomic(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _write_recovery_state(
        cls,
        path: Path,
        remote_job_id: str,
        state: str,
        *,
        local_job_id: str | None = None,
        recovery_count: int = 0,
        last_error: Any = None,
    ) -> None:
        cls._write_json_atomic(
            path,
            {
                "schema_version": "conn_pilot_recovery_state_v1",
                "remote_job_id": remote_job_id,
                "state": state,
                "local_job_id": local_job_id,
                "recovery_count": recovery_count,
                "last_error": last_error,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    @staticmethod
    def _recoverable_local_failure(error: str) -> bool:
        normalized = error.casefold()
        return any(
            marker in normalized
            for marker in (
                "another conn job is active",
                "orphaned local job",
                "interrupted local execution",
                "worker process exited",
                "matlab process disappeared",
                "connection reset",
                "temporary network",
            )
        )

    def _orphan_check_due(self, job: dict[str, Any]) -> bool:
        """Avoid treating process-launch latency as a vanished execution."""
        raw = job.get("updated_at") or job.get("created_at")
        if not raw:
            return True
        try:
            updated = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
        except ValueError:
            return True
        grace = max(60, self.heartbeat_seconds * 2)
        return (datetime.now(timezone.utc) - updated).total_seconds() >= grace

    def _heartbeat_waiting(self, remote_job_id: str, message: str) -> None:
        self.client.post(
            f"/worker/v1/jobs/{remote_job_id}/heartbeat",
            {
                "worker_id": self.worker_id,
                "phase": "waiting_for_local_recovery",
                "progress": {
                    "activity": {"state": "recovering", "message": message},
                    "reported_at": datetime.now(timezone.utc).isoformat(),
                },
            },
        )

    @staticmethod
    def _reconcile_local_slot(service: Any) -> bool:
        blocked = False
        for job in service.store.list():
            if job.get("state") not in {"queued", "preparing", "running"}:
                continue
            alive = _local_job_has_live_process(job)
            if alive is False:
                service.store.update(
                    str(job["id"]),
                    "failed",
                    error=(
                        "Recovered orphaned local execution before queue claim: no matching "
                        "CONN worker or MATLAB process was running"
                    ),
                )
            else:
                blocked = True
        return blocked

    @staticmethod
    def _restored_local_job_id(state_path: Path, service: Any) -> str | None:
        if not state_path.is_file():
            return DistributedWorker._clear_unlinked_orphaned_local_job(service)
        try:
            value = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return DistributedWorker._clear_unlinked_orphaned_local_job(service)
        if value.get("schema_version") != "conn_pilot_worker_state_v1":
            return DistributedWorker._clear_unlinked_orphaned_local_job(service)
        local_job_id = str(value.get("local_job_id", ""))
        job = service.store.get(local_job_id) if local_job_id else None
        if not job or job.get("state") == "failed":
            return None
        if job.get("state") == "succeeded":
            return local_job_id
        process_alive = _local_job_has_live_process(job)
        if process_alive is not False:
            return local_job_id
        service.store.update(
            local_job_id,
            "failed",
            error=(
                "Recovered orphaned local job: the persisted state was active but no matching "
                "CONN worker or MATLAB process was running"
            ),
        )
        return None

    @staticmethod
    def _clear_unlinked_orphaned_local_job(service: Any) -> str | None:
        """Reassociate one live job or clear one proven orphan when its link is unreadable.

        A missing or corrupt worker-state file must never invalidate a potentially live
        MATLAB run. The only active local job is adopted when its process is visible;
        it is cleared only after inspection proves that no process remains.
        """
        active = [
            job
            for job in service.store.list()
            if job.get("state") in {"queued", "preparing", "running"}
        ]
        if len(active) != 1:
            return None
        job = active[0]
        process_alive = _local_job_has_live_process(job)
        if process_alive is True:
            return str(job["id"])
        if process_alive is None:
            return None
        service.store.update(
            str(job["id"]),
            "failed",
            error=(
                "Recovered orphaned unlinked local job: worker state was missing or corrupt "
                "and no matching CONN worker or MATLAB process was running"
            ),
        )
        return None

    @staticmethod
    def _write_worker_state(state_path: Path, remote_job_id: str, local_job_id: str) -> None:
        """Durably replace the remote-to-local job link without exposing a partial file."""
        DistributedWorker._write_json_atomic(
            state_path,
            {
                "schema_version": "conn_pilot_worker_state_v1",
                "remote_job_id": remote_job_id,
                "local_job_id": local_job_id,
            },
        )

    def run_once(self) -> bool:
        try:
            if self.recover_pending_job():
                return True
            if self.recover_pending_second_level():
                return True
        except LocalCapacityBusy:
            return True
        self.heartbeat()
        service = build_operation_service()
        if self._reconcile_local_slot(service):
            return True
        second_level = self.claim_second_level()
        if second_level:
            try:
                self.run_second_level(second_level)
            except Exception as error:
                self._complete_second_level(
                    str(second_level["id"]), "failed", {}, f"Worker error: {error}"
                )
                self._write_recovery_state(
                    self.work_root / "second-level" / str(second_level["id"]) / "recovery-state.json",
                    str(second_level["id"]),
                    "permanent_failed",
                    last_error=str(error),
                )
            return True
        job = self.claim()
        if not job:
            return False
        try:
            self.run_job(job)
        except LocalCapacityBusy:
            return True
        except Exception as error:
            self._complete(str(job["id"]), "failed", {}, f"Worker error: {error}")
        return True

    def run_second_level(self, task: dict[str, Any]) -> None:
        run_id = str(task["id"])
        recovery_dir = self.work_root / "second-level" / run_id
        recovery_path = recovery_dir / "recovery-state.json"
        self._write_json_atomic(recovery_dir / "task.json", task)
        self._write_recovery_state(recovery_path, run_id, "running")
        source = dict(task["source_job"])
        remote_job_id = str(task["job_id"])
        local_job_id = str((source.get("result_summary") or {}).get("local_job_id", ""))
        service = build_operation_service()
        local_job = service.store.get(local_job_id) if local_job_id else None
        if not local_job or local_job.get("state") != "succeeded":
            raise ValueError("The source CONN execution is not available on this worker")
        run_dir = Path(str(local_job["run_dir"]))
        project = load_yaml(run_dir / "project.execution.yaml")
        self.client.post(
            f"/worker/v1/second-level/{run_id}/heartbeat",
            {"worker_id": self.worker_id, "phase": "running_matlab"},
        )
        result = run_second_level_recalculation(
            project, run_dir, run_id, str(task["sample_version"]),
            [str(value) for value in task["included_subject_ids"]],
            load_yaml(service.environment_path),
        )
        self._write_recovery_state(recovery_path, run_id, "publishing")
        uploaded = self._upload_second_level(
            remote_job_id, run_id, result["artifact_paths"], Path(result["output_dir"])
        )
        self._complete_second_level(
            run_id, "succeeded",
            {
                "local_job_id": local_job_id,
                "sample_version": task["sample_version"],
                "included_subject_ids": task["included_subject_ids"],
                "model_count": result["manifest"]["model_count"],
                "scientific_audit": result["manifest"]["scientific_audit"],
                "uploads": uploaded,
            },
            None,
        )
        self._write_recovery_state(recovery_path, run_id, "completed")

    def _complete_second_level(
        self, run_id: str, state: str, summary: dict[str, Any], error: str | None
    ) -> None:
        roots = [str(self.work_root), *(dataset["root"] for dataset in self.registry.values())]
        self.client.post(
            f"/worker/v1/second-level/{run_id}/complete",
            {
                "worker_id": self.worker_id,
                "state": state,
                "summary": sanitize_for_remote(summary, roots),
                "error": sanitize_for_remote(error, roots) if error else None,
            },
        )

    def _upload_second_level(
        self, remote_job_id: str, run_id: str, paths: list[Path], output_dir: Path
    ) -> dict[str, Any]:
        uploaded = skipped = total_bytes = 0
        for path in paths:
            if not path.is_file():
                continue
            size = path.stat().st_size
            if size > self.max_artifact_bytes:
                skipped += 1
                continue
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            digest = sha256_file(path)
            prepared = self.client.post(
                f"/worker/v1/jobs/{remote_job_id}/artifacts/prepare",
                {"worker_id": self.worker_id, "name": f"{run_id}-{path.name}",
                 "content_type": content_type, "sha256": digest},
            )
            self.client.upload(prepared["upload_url"], path, content_type)
            relative_path = (
                path.relative_to(output_dir).as_posix()
                if path.is_relative_to(output_dir) else path.name
            )
            self.client.post(
                f"/worker/v1/jobs/{remote_job_id}/artifacts/complete",
                {
                    "worker_id": self.worker_id,
                    "kind": "second_level_version",
                    "name": path.name,
                    "object_key": prepared["object_key"],
                    "bytes": size,
                    "sha256": digest,
                    "content_type": content_type,
                    "metadata": {"relative_path": relative_path},
                    "second_level_run_id": run_id,
                },
            )
            uploaded += 1
            total_bytes += size
        return {"uploaded": uploaded, "skipped_too_large": skipped, "bytes": total_bytes}

    def _complete(
        self, job_id: str, state: str, summary: dict[str, Any], error: str | None
    ) -> None:
        roots = [str(self.work_root), *(dataset["root"] for dataset in self.registry.values())]
        self.client.post(
            f"/worker/v1/jobs/{job_id}/complete",
            {
                "worker_id": self.worker_id,
                "state": state,
                "summary": sanitize_for_remote(summary, roots),
                "error": sanitize_for_remote(error, roots) if error else None,
            },
        )

    def _upload_selected(
        self, remote_job_id: str, run_dir: Path, manifest: dict[str, Any]
    ) -> dict[str, Any]:
        project = load_yaml(run_dir / "project.execution.yaml")
        subject_ids = [str(item["id"]) for item in project.get("subjects", [])]
        candidates: list[tuple[str, Path, str | None, dict[str, Any]]] = []
        for name in (
            "artifacts.json",
            "qc_metrics.json",
            "scientific_audit.json",
            "project.request.yaml",
            "matlab_stdout.log",
            "matlab_stderr.log",
        ):
            path = run_dir / name
            if path.is_file():
                kind = "qc_metrics" if name == "qc_metrics.json" else "provenance"
                candidates.append((kind, path, None, {}))
        for group in ("qc_images", "second_level_maps"):
            for item in manifest.get("groups", {}).get(group, []):
                path = Path(str(item.get("path", "")))
                if path.is_file():
                    subject_id = (
                        _artifact_subject(item.get("relative_path"), subject_ids)
                        if group == "qc_images" else None
                    )
                    candidates.append(
                        (
                            group,
                            path,
                            subject_id,
                            {
                                "relative_path": item.get("relative_path"),
                                "qc_type": _qc_type(item.get("relative_path")),
                            },
                        )
                    )
        uploaded = 0
        skipped = 0
        total_bytes = 0
        for kind, path, subject_id, metadata in candidates:
            size = path.stat().st_size
            if size > self.max_artifact_bytes:
                skipped += 1
                continue
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            digest = sha256_file(path)
            prepared = self.client.post(
                f"/worker/v1/jobs/{remote_job_id}/artifacts/prepare",
                {
                    "worker_id": self.worker_id,
                    "name": path.name,
                    "content_type": content_type,
                    "sha256": digest,
                },
            )
            self.client.upload(prepared["upload_url"], path, content_type)
            self.client.post(
                f"/worker/v1/jobs/{remote_job_id}/artifacts/complete",
                {
                    "worker_id": self.worker_id,
                    "kind": kind,
                    "name": path.name,
                    "object_key": prepared["object_key"],
                    "bytes": size,
                    "sha256": digest,
                    "content_type": content_type,
                    "subject_id": subject_id,
                    "metadata": metadata,
                },
            )
            uploaded += 1
            total_bytes += size
        return {"uploaded": uploaded, "skipped_too_large": skipped, "bytes": total_bytes}


def _artifact_subject(relative_path: Any, subject_ids: list[str] | None = None) -> str | None:
    parts = Path(str(relative_path or "")).parts
    try:
        index = parts.index("inputs")
    except ValueError:
        match = re.search(r"subject(\d+)", str(relative_path or ""), re.IGNORECASE)
        if match and subject_ids:
            offset = int(match.group(1)) - 1
            return subject_ids[offset] if 0 <= offset < len(subject_ids) else None
        return None
    return parts[index + 1] if len(parts) > index + 1 else None


def _qc_type(relative_path: Any) -> str:
    name = Path(str(relative_path or "")).name.lower()
    if name.startswith("art_screenshot"):
        return "art"
    for prefix, value in (
        ("qa_norm_structural", "normalization_structural"),
        ("qa_norm_functional", "normalization_functional"),
        ("qa_norm_greymatter", "segmentation_grey_matter"),
        ("qa_reg_functional", "functional_anatomical_registration"),
        ("qa_timeart", "time_series_art"),
        ("qa_denoise_timeseries", "denoising_timeseries"),
    ):
        if name.startswith(prefix):
            return value
    return "other"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pull CONN Pilot jobs from the Railway control plane")
    parser.add_argument("--control-url", default=os.environ.get("CONN_PILOT_CONTROL_URL"))
    parser.add_argument("--token", default=os.environ.get("CONN_PILOT_WORKER_TOKEN"))
    parser.add_argument(
        "--registry",
        default=os.environ.get("CONN_PILOT_DATASET_REGISTRY", "config/datasets.local.yaml"),
    )
    parser.add_argument("--worker-id", default=os.environ.get("CONN_PILOT_WORKER_ID", "desktop-worker-1"))
    parser.add_argument("--label", default=os.environ.get("CONN_PILOT_WORKER_LABEL", "CONN desktop worker"))
    parser.add_argument("--work-root", default=os.environ.get("CONN_PILOT_WORK_ROOT", "work"))
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--once", action="store_true")
    return parser


def sanitize_for_remote(value: Any, private_roots: list[str]) -> Any:
    """Remove filesystem locations before a worker writes information to Railway."""
    private_keys = {"path", "root", "run_dir", "project_path", "manifest_path"}
    if isinstance(value, dict):
        return {
            key: sanitize_for_remote(child, private_roots)
            for key, child in value.items()
            if key not in private_keys
        }
    if isinstance(value, list):
        return [sanitize_for_remote(child, private_roots) for child in value]
    if isinstance(value, str):
        result = value
        for root in private_roots:
            if root:
                result = result.replace(root, "<local-path>")
                result = result.replace(root.replace("\\", "/"), "<local-path>")
        return re.sub(r"(?i)\b[A-Z]:[\\/][^\s;,]+", "<local-path>", result)
    return value


def _local_job_has_live_process(job: dict[str, Any]) -> bool | None:
    """Return whether a local execution process still belongs to this persisted job.

    Process inspection is deliberately conservative: an unavailable process inventory returns
    ``None`` so a transient inspection failure never invalidates a potentially live MATLAB run.
    """
    command_lines = _process_command_lines()
    if command_lines is None:
        return None
    needles = {
        str(job.get("id", "")),
        str(job.get("batch_path", "")),
        str(job.get("run_dir", "")),
    }
    normalized_needles = {
        _normalize_process_text(value) for value in needles if value.strip()
    }
    return any(
        needle in _normalize_process_text(command_line)
        for command_line in command_lines
        for needle in normalized_needles
    )


def _process_command_lines() -> list[str] | None:
    if os.name == "nt":
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "@(Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine) "
                "| ConvertTo-Json -Compress"
            ),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if completed.returncode != 0 or not completed.stdout.strip():
                return None
            value = json.loads(completed.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return None
        records = value if isinstance(value, list) else [value]
        return [
            str(record.get("CommandLine") or "")
            for record in records
            if isinstance(record, dict) and record.get("CommandLine")
        ]

    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return None
    command_lines: list[str] = []
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return None
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            command_line = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
        except OSError:
            continue
        if command_line:
            command_lines.append(command_line)
    return command_lines


def _normalize_process_text(value: str) -> str:
    return value.replace("\\", "/").casefold()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.control_url or not args.token:
        print("CONN_PILOT_CONTROL_URL and CONN_PILOT_WORKER_TOKEN are required", file=sys.stderr)
        return 2
    worker = DistributedWorker(
        client=WorkerClient(args.control_url, args.token),
        worker_id=args.worker_id,
        label=args.label,
        registry=load_registry(args.registry),
        work_root=args.work_root,
    )
    try:
        with SupervisorLock(Path(args.work_root).resolve() / "distributed-worker.lock"):
            while True:
                try:
                    worker.run_once()
                except Exception as error:
                    print(f"Distributed worker loop recovered from error: {error}", file=sys.stderr)
                    if args.once:
                        return 1
                if args.once:
                    return 0
                time.sleep(max(5, args.poll_seconds))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
