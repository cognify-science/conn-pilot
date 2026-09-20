from __future__ import annotations

import copy
import io
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp import Client  # noqa: E402

from conn_pilot.control_plane import (  # noqa: E402
    ControlPlaneService,
    ControlSettings,
    build_control_plane_server,
)
from conn_pilot.distributed_worker import (  # noqa: E402
    WorkerClient,
    inventory_record,
    load_registry,
    sanitize_for_remote,
)
from conn_pilot.io import load_yaml  # noqa: E402


class FakeStore:
    def __init__(self) -> None:
        self.datasets = {
            "study_001": {
                "id": "study_001",
                "label": "Study 001",
                "worker_id": "worker-1",
                "fingerprint": "sha256:abc",
                "status": "ready",
                "metadata": {
                    "layout": "bids",
                    "tr_seconds": 2.0,
                    "subjects": [{"id": "sub-001"}],
                    "subject_count": 1,
                    "file_count": 2,
                    "total_bytes": 12,
                },
                "updated_at": "2026-09-19T00:00:00Z",
            }
        }
        self.projects: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.validations: dict[str, dict[str, Any]] = {}

    def verify_credential(self, token: str) -> dict[str, Any] | None:
        return {"subject": "owner", "role": "admin"} if token == "x" * 48 else None

    def list_datasets(self) -> list[dict[str, Any]]:
        return list(self.datasets.values())

    def get_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        return self.datasets.get(dataset_id)

    def create_project(
        self, owner_subject: str, dataset_id: str, pipeline_id: str, pipeline_version: str, spec: dict[str, Any]
    ) -> dict[str, Any]:
        value = {
            "id": "project-1",
            "owner_subject": owner_subject,
            "dataset_id": dataset_id,
            "pipeline_id": pipeline_id,
            "pipeline_version": pipeline_version,
            "spec": copy.deepcopy(spec),
            "state": "draft",
        }
        self.projects[value["id"]] = value
        return value

    def get_project(self, project_id: str, subject: str | None = None) -> dict[str, Any] | None:
        value = self.projects.get(project_id)
        return value if value and (subject is None or value["owner_subject"] == subject) else None

    def save_validation(self, project_id: str, validation: dict[str, Any]) -> None:
        self.validations[project_id] = validation
        self.projects[project_id]["state"] = "validated" if validation["valid"] else "invalid"

    def create_job(self, project: dict[str, Any]) -> dict[str, Any]:
        value = {
            "id": "job-1",
            "owner_subject": project["owner_subject"],
            "project_id": project["id"],
            "dataset_id": project["dataset_id"],
            "state": "queued",
            "phase": "waiting_for_worker",
            "attempts": 0,
        }
        self.jobs[value["id"]] = value
        return value

    def retry_job(self, job_id: str, subject: str) -> dict[str, Any]:
        value = self.get_job(job_id, subject)
        if not value or value["state"] != "failed":
            raise ValueError("Only an owned failed job can be retried")
        value.update(state="queued", phase="waiting_for_worker", error=None)
        return value

    def get_job(self, job_id: str, subject: str | None = None) -> dict[str, Any] | None:
        value = self.jobs.get(job_id)
        return value if value and (subject is None or value["owner_subject"] == subject) else None

    def get_events(self, job_id: str, subject: str) -> list[dict[str, Any]]:
        return [{"kind": "queued", "message": "Job queued", "details": {}}]

    def list_artifacts(self, job_id: str, subject: str) -> list[dict[str, Any]]:
        return []

    def register_worker(self, worker_id: str, label: str, capabilities: dict[str, Any]) -> None:
        return None

    def sync_datasets(self, worker_id: str, datasets: list[dict[str, Any]]) -> None:
        return None

    def claim_job(self, worker_id: str, dataset_ids: list[str], lease_seconds: int) -> dict[str, Any] | None:
        return None

    def heartbeat_job(self, job_id: str, worker_id: str, phase: str, lease_seconds: int) -> bool:
        return True

    def complete_job(
        self, job_id: str, worker_id: str, state: str, summary: dict[str, Any], error: str | None
    ) -> bool:
        return True

    def add_artifact(self, job_id: str, worker_id: str, **kwargs: Any) -> dict[str, Any]:
        return kwargs


def remote_spec() -> dict[str, Any]:
    project = load_yaml(ROOT / "examples" / "project.template.yaml")
    return {key: project[key] for key in ("project", "design", "seeds", "parameters")}


class ControlPlaneTests(unittest.IsolatedAsyncioTestCase):
    def test_project_is_validated_and_queued_without_local_paths(self) -> None:
        store = FakeStore()
        service = ControlPlaneService(store, ROOT / "catalog")
        created = service.create_project(
            "owner", "study_001", "rsfmri_seed_to_voxel", "1.0.0", remote_spec()
        )
        project_id = created["data"]["project"]["id"]
        validation = service.validate_project("owner", project_id)
        plan = service.generate_execution_plan("owner", project_id)
        submitted = service.submit_job("owner", project_id)
        self.assertTrue(validation["ok"])
        self.assertTrue(plan["data"]["ready_to_submit"])
        self.assertEqual(submitted["data"]["job"]["phase"], "waiting_for_worker")
        self.assertNotIn("root", store.projects[project_id]["spec"])

    async def test_remote_mcp_exposes_distributed_tools(self) -> None:
        settings = ControlSettings(
            database_url="unused",
            public_base_url="http://127.0.0.1:8000",
            admin_subject="owner",
            admin_token="x" * 48,
            worker_token="y" * 48,
            host="127.0.0.1",
            port=8000,
        )
        server = build_control_plane_server(settings, FakeStore(), require_mcp_auth=False)
        async with Client(server) as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            pipelines = await client.call_tool("list_pipelines", {})
            datasets = await client.call_tool("list_datasets", {})
        self.assertEqual(
            tools,
            {
                "list_pipelines",
                "list_datasets",
                "inspect_dataset",
                "create_project",
                "validate_project",
                "generate_execution_plan",
                "submit_job",
                "retry_job",
                "get_job_status",
                "get_job_logs",
                "list_results",
                "get_qc_summary",
                "get_result_download_url",
            },
        )
        self.assertEqual(pipelines.structured_content["data"]["count"], 1)
        self.assertEqual(datasets.structured_content["data"]["count"], 1)

    def test_worker_retries_a_temporary_dns_failure(self) -> None:
        sleeps: list[float] = []
        client = WorkerClient(
            "https://control.example",
            "x" * 48,
            retry_attempts=2,
            sleeper=sleeps.append,
        )
        response = io.BytesIO(b'{"ok": true}')
        with patch(
            "conn_pilot.distributed_worker.urllib.request.urlopen",
            side_effect=[urllib.error.URLError("temporary DNS failure"), response],
        ):
            result = client.post("/worker/v1/heartbeat", {"worker_id": "one"})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleeps, [1.0])

    def test_failed_remote_job_can_be_requeued(self) -> None:
        store = FakeStore()
        project = store.create_project(
            "owner", "study_001", "rsfmri_seed_to_voxel", "1.0.0", remote_spec()
        )
        job = store.create_job(project)
        job.update(state="failed", phase="failed", error="temporary network failure")
        service = ControlPlaneService(store, ROOT / "catalog")
        retried = service.retry_job("owner", job["id"])
        self.assertTrue(retried["ok"])
        self.assertEqual(retried["data"]["job"]["state"], "queued")

    def test_worker_inventory_never_contains_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "study"
            functional = root / "sub-001" / "func" / "sub-001_task-rest_bold.nii.gz"
            structural = root / "sub-001" / "anat" / "sub-001_T1w.nii.gz"
            functional.parent.mkdir(parents=True)
            structural.parent.mkdir(parents=True)
            functional.write_bytes(b"bold")
            structural.write_bytes(b"t1")
            registry_path = Path(directory) / "registry.yaml"
            registry_path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": "conn_pilot_dataset_registry_v1",
                        "datasets": [
                            {
                                "id": "study_001",
                                "label": "Study",
                                "root": str(root),
                                "layout": "bids",
                                "tr_seconds": 2.0,
                                "subjects": [
                                    {
                                        "id": "sub-001",
                                        "functional": [str(functional.relative_to(root))],
                                        "structural": [str(structural.relative_to(root))],
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            dataset = load_registry(registry_path)["study_001"]
            record = inventory_record(dataset)
        serialized = str(record)
        self.assertEqual(record["status"], "ready")
        self.assertNotIn(str(root), serialized)
        self.assertNotIn("func", serialized)
        self.assertEqual(record["metadata"]["subject_count"], 1)

    def test_worker_sanitizes_paths_from_remote_summaries(self) -> None:
        value = {
            "path": r"D:\Studies\one\secret.nii.gz",
            "message": r"Missing file D:\Studies\one\secret.nii.gz",
            "nested": [{"run_dir": r"C:\private\run", "relative_path": "qa/report.png"}],
        }
        sanitized = sanitize_for_remote(value, [r"D:\Studies\one", r"C:\private"])
        serialized = str(sanitized)
        self.assertNotIn("D:\\Studies", serialized)
        self.assertNotIn("C:\\private", serialized)
        self.assertNotIn("path", sanitized)
        self.assertEqual(sanitized["nested"][0]["relative_path"], "qa/report.png")


if __name__ == "__main__":
    unittest.main()
