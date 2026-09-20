from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .control_plane import materialize_remote_project
from .io import load_yaml, sha256_file, write_json, write_yaml
from .mcp_server import build_operation_service


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
    return {
        "id": str(dataset["id"]),
        "label": str(dataset.get("label", dataset["id"])),
        "root": str(root),
        "layout": str(dataset.get("layout", "bids")),
        "tr_seconds": dataset.get("tr_seconds"),
        "subjects": normalized_subjects,
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
        project_path = remote_dir / "project.yaml"
        write_yaml(project_path, project_definition)
        service = build_operation_service()
        state_path = remote_dir / "worker-state.json"
        local_job_id = self._restored_local_job_id(state_path, service)
        if not local_job_id:
            submitted = service.submit_job(str(project_path))
            if not submitted["ok"]:
                errors = sanitize_for_remote(submitted["errors"], [dataset["root"], str(self.work_root)])
                self._complete(remote_job_id, "failed", {"submission_errors": errors}, "; ".join(errors))
                return
            local_job_id = str(submitted["data"]["job"]["id"])
            write_json(
                state_path,
                {
                    "schema_version": "conn_pilot_worker_state_v1",
                    "remote_job_id": remote_job_id,
                    "local_job_id": local_job_id,
                },
            )
        last_heartbeat = 0.0
        while True:
            status = service.get_job_status(local_job_id)
            job = status["data"]["job"]
            now = time.monotonic()
            if now - last_heartbeat >= self.heartbeat_seconds:
                self.client.post(
                    f"/worker/v1/jobs/{remote_job_id}/heartbeat",
                    {"worker_id": self.worker_id, "phase": status["data"]["phase"]},
                )
                last_heartbeat = now
            if status["data"]["terminal"]:
                break
            time.sleep(min(5, self.heartbeat_seconds))
        if job["state"] != "succeeded":
            self._complete(remote_job_id, "failed", {"local_job_id": local_job_id}, job.get("error"))
            return
        results = service.list_results(local_job_id)
        qc = service.get_qc_summary(local_job_id)
        run_dir = Path(job["run_dir"])
        upload_summary = self._upload_selected(remote_job_id, run_dir, results["data"].get("artifacts", {}))
        self._complete(
            remote_job_id,
            "succeeded",
            {
                "local_job_id": local_job_id,
                "qc": sanitize_for_remote(qc["data"], [dataset["root"], str(self.work_root)]),
                "artifact_counts": results["data"].get("artifacts", {}).get("counts", {}),
                "uploads": upload_summary,
            },
            None,
        )

    @staticmethod
    def _restored_local_job_id(state_path: Path, service: Any) -> str | None:
        if not state_path.is_file():
            return None
        try:
            value = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if value.get("schema_version") != "conn_pilot_worker_state_v1":
            return None
        local_job_id = str(value.get("local_job_id", ""))
        return local_job_id if local_job_id and service.store.get(local_job_id) else None

    def run_once(self) -> bool:
        self.heartbeat()
        job = self.claim()
        if not job:
            return False
        try:
            self.run_job(job)
        except Exception as error:
            self._complete(str(job["id"]), "failed", {}, f"Worker error: {error}")
        return True

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
        candidates: list[tuple[str, Path]] = []
        for name in ("artifacts.json", "project.request.yaml", "matlab_stdout.log", "matlab_stderr.log"):
            path = run_dir / name
            if path.is_file():
                candidates.append(("provenance", path))
        for group in ("qc_images", "second_level_maps"):
            for item in manifest.get("groups", {}).get(group, []):
                path = Path(str(item.get("path", "")))
                if path.is_file():
                    candidates.append((group, path))
        uploaded = 0
        skipped = 0
        total_bytes = 0
        for kind, path in candidates:
            size = path.stat().st_size
            if size > self.max_artifact_bytes:
                skipped += 1
                continue
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            prepared = self.client.post(
                f"/worker/v1/jobs/{remote_job_id}/artifacts/prepare",
                {"worker_id": self.worker_id, "name": path.name, "content_type": content_type},
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
                    "sha256": sha256_file(path),
                    "content_type": content_type,
                },
            )
            uploaded += 1
            total_bytes += size
        return {"uploaded": uploaded, "skipped_too_large": skipped, "bytes": total_bytes}


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
    while True:
        worker.run_once()
        if args.once:
            return 0
        time.sleep(max(5, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
