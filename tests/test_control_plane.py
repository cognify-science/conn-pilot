from __future__ import annotations

import copy
import io
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp import Client  # noqa: E402

from conn_pilot.control_plane import (  # noqa: E402
    ControlPlaneService,
    ControlSettings,
    HybridTokenVerifier,
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
        self.external_credentials: dict[str, dict[str, Any]] = {}
        self.method_decisions: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []
        self.subject_qc_decisions: list[dict[str, Any]] = []
        self.analysis_decisions: list[dict[str, Any]] = []
        self.second_level_runs: list[dict[str, Any]] = []

    def verify_credential(self, token: str) -> dict[str, Any] | None:
        return {"subject": "owner", "role": "admin"} if token == "x" * 48 else None

    def ensure_external_credential(
        self, subject: str, *, provider: str, email: str | None = None
    ) -> dict[str, Any] | None:
        existing = self.external_credentials.get(subject)
        if existing and not existing["active"]:
            return None
        value = existing or {
            "subject": subject,
            "role": "researcher",
            "active": True,
            "provider": provider,
            "email": email,
        }
        self.external_credentials[subject] = value
        return value

    def list_datasets(self) -> list[dict[str, Any]]:
        return list(self.datasets.values())

    def get_system_health(self) -> dict[str, Any]:
        return {"workers": [{"id": "worker-1", "online": True}], "job_counts": {},
                "second_level_counts": {}, "dataset_counts": {"ready": 1}}

    def create_review_session(
        self, job_id: str, owner_subject: str, expires_seconds: int = 3600
    ) -> dict[str, Any]:
        return {"id": "review-1", "job_id": job_id, "owner_subject": owner_subject,
                "expires_at": "2026-09-26T13:00:00Z", "token": "review-token"}

    def resolve_review_session(self, token: str) -> dict[str, Any] | None:
        return ({"id": "review-1", "job_id": "job-1", "owner_subject": "owner"}
                if token == "review-token" else None)

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

    def get_reusable_job_for_project(
        self, project_id: str, subject: str
    ) -> dict[str, Any] | None:
        return next(
            (
                value
                for value in reversed(list(self.jobs.values()))
                if value["project_id"] == project_id
                and value["owner_subject"] == subject
                and value["state"] in {"queued", "running", "succeeded"}
            ),
            None,
        )

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
        return [item for item in self.artifacts if item.get("job_id") == job_id]

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
        value = {"id": f"artifact-{len(self.artifacts) + 1}", "job_id": job_id, **kwargs}
        self.artifacts.append(value)
        return value

    def add_generated_artifact(
        self, job_id: str, owner_subject: str, **kwargs: Any
    ) -> dict[str, Any]:
        value = {"id": f"artifact-{len(self.artifacts) + 1}", "job_id": job_id, **kwargs}
        self.artifacts.append(value)
        return value

    def create_second_level_run(
        self, job_id: str, owner_subject: str, parent_result_version: str,
        sample_version: str, included_subject_ids: list[str], review_snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        existing = next((item for item in self.second_level_runs
                         if item["job_id"] == job_id
                         and item["sample_version"] == sample_version
                         and item["state"] in {"queued", "running", "succeeded"}), None)
        if existing:
            return existing
        value = {
            "id": f"second-level-{len(self.second_level_runs) + 1}", "job_id": job_id,
            "parent_result_version": parent_result_version, "sample_version": sample_version,
            "included_subject_ids": included_subject_ids, "state": "queued",
            "phase": "waiting_for_worker", "attempts": 0, "output_version": None,
            "result_summary": None, "error": None,
        }
        self.second_level_runs.append(value)
        return value

    def list_second_level_runs(
        self, job_id: str, owner_subject: str, parent_result_version: str
    ) -> list[dict[str, Any]]:
        return [item for item in self.second_level_runs if item["job_id"] == job_id
                and item["parent_result_version"] == parent_result_version]

    def get_second_level_run(
        self, run_id: str, owner_subject: str | None = None
    ) -> dict[str, Any] | None:
        return next((item for item in self.second_level_runs if item["id"] == run_id), None)

    def claim_second_level_run(
        self, worker_id: str, dataset_ids: list[str], lease_seconds: int
    ) -> dict[str, Any] | None:
        return None

    def heartbeat_second_level_run(
        self, run_id: str, worker_id: str, phase: str, lease_seconds: int
    ) -> bool:
        return True

    def complete_second_level_run(
        self, run_id: str, worker_id: str, state: str,
        summary: dict[str, Any], error: str | None
    ) -> bool:
        return True

    def record_subject_qc_decision(
        self,
        job_id: str,
        owner_subject: str,
        result_version: str,
        subject_id: str,
        decision: str,
        justification: str | None,
    ) -> dict[str, Any]:
        value = {
            "id": f"qc-{len(self.subject_qc_decisions) + 1}",
            "job_id": job_id,
            "result_version": result_version,
            "subject_id": subject_id,
            "decision": decision,
            "justification": justification,
            "decided_by": owner_subject,
            "decided_at": "2026-09-26T12:00:00Z",
        }
        self.subject_qc_decisions.append(value)
        return value

    def list_subject_qc_decisions(
        self, job_id: str, owner_subject: str, result_version: str
    ) -> list[dict[str, Any]]:
        return [
            item
            for item in self.subject_qc_decisions
            if item["job_id"] == job_id and item["result_version"] == result_version
        ]

    def record_analysis_decision(
        self,
        job_id: str,
        owner_subject: str,
        result_version: str,
        sample_version: str,
        decision: str,
        rationale: str,
    ) -> dict[str, Any]:
        value = {
            "id": f"analysis-{len(self.analysis_decisions) + 1}",
            "job_id": job_id,
            "result_version": result_version,
            "sample_version": sample_version,
            "decision": decision,
            "rationale": rationale,
            "decided_by": owner_subject,
            "decided_at": "2026-09-26T12:00:00Z",
        }
        self.analysis_decisions.append(value)
        return value

    def list_analysis_decisions(
        self, job_id: str, owner_subject: str, result_version: str
    ) -> list[dict[str, Any]]:
        return [
            item
            for item in self.analysis_decisions
            if item["job_id"] == job_id and item["result_version"] == result_version
        ]

    def record_method_decision(
        self,
        owner_subject: str,
        project_id: str,
        component_id: str,
        parameter_name: str,
        selected_value: Any,
        evidence_ids: list[str],
        rationale: str,
        corpus_version: str,
        evidence_snapshot: list[dict[str, Any]],
    ) -> dict[str, Any]:
        value = {
            "id": f"decision-{len(self.method_decisions) + 1}",
            "owner_subject": owner_subject,
            "project_id": project_id,
            "component_id": component_id,
            "parameter_name": parameter_name,
            "selected_value": selected_value,
            "evidence_ids": evidence_ids,
            "rationale": rationale,
            "corpus_version": corpus_version,
            "evidence_snapshot": evidence_snapshot,
        }
        self.method_decisions.append(value)
        return value

    def list_method_decisions(self, project_id: str, subject: str) -> list[dict[str, Any]]:
        return [
            value
            for value in self.method_decisions
            if value["project_id"] == project_id and value["owner_subject"] == subject
        ]

    def resolve_project_parameter(
        self,
        owner_subject: str,
        project_id: str,
        parameter_path: str,
        parameter_record: dict[str, Any],
        component_id: str,
        parameter_name: str,
        selected_value: Any,
        evidence_ids: list[str],
        rationale: str,
        corpus_version: str,
        evidence_snapshot: list[dict[str, Any]],
    ) -> dict[str, Any]:
        project = self.get_project(project_id, owner_subject)
        if not project:
            raise ValueError("Unknown project")
        decision_id = f"decision-{len(self.method_decisions) + 1}"
        stored_record = {**parameter_record, "method_decision_id": decision_id}
        target = project["spec"].setdefault("parameters", {})
        parts = parameter_path.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = stored_record
        project["state"] = "draft"
        decision = {
            "id": decision_id,
            "owner_subject": owner_subject,
            "project_id": project_id,
            "parameter_path": parameter_path,
            "component_id": component_id,
            "parameter_name": parameter_name,
            "selected_value": selected_value,
            "evidence_ids": evidence_ids,
            "rationale": rationale,
            "corpus_version": corpus_version,
            "evidence_snapshot": evidence_snapshot,
        }
        self.method_decisions.append(decision)
        return {"decision": decision, "parameter_record": stored_record}


def remote_spec() -> dict[str, Any]:
    project = load_yaml(ROOT / "examples" / "project.template.yaml")
    return {key: project[key] for key in ("project", "design", "seeds", "parameters")}


class ControlPlaneTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth0_jwt_is_verified_and_provisions_researcher(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()

        class SigningKey:
            key = public_key

        class JwkClient:
            def get_signing_key_from_jwt(self, _token: str) -> SigningKey:
                return SigningKey()

        now = int(time.time())
        token = jwt.encode(
            {
                "iss": "https://brainai.us.auth0.com/",
                "aud": "https://control.example/mcp",
                "sub": "auth0|researcher-1",
                "iat": now,
                "exp": now + 300,
                "scope": "openid profile conn-pilot:use",
                "client_id": "mcp-client",
            },
            private_key,
            algorithm="RS256",
        )
        store = FakeStore()
        verifier = HybridTokenVerifier(
            store,
            "https://control.example/mcp",
            auth0_issuer="https://brainai.us.auth0.com/",
            auth0_audience="https://control.example/mcp",
            jwk_client=JwkClient(),
        )
        access = await verifier.verify_token(token)
        self.assertIsNotNone(access)
        assert access is not None
        self.assertEqual(access.subject, "auth0:auth0|researcher-1")
        self.assertIn("conn-pilot:use", access.scopes)
        self.assertEqual(store.external_credentials[access.subject]["role"], "researcher")

    async def test_auth0_jwt_without_required_permission_is_rejected(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()

        class SigningKey:
            key = public_key

        class JwkClient:
            def get_signing_key_from_jwt(self, _token: str) -> SigningKey:
                return SigningKey()

        now = int(time.time())
        token = jwt.encode(
            {
                "iss": "https://brainai.us.auth0.com/",
                "aud": "https://control.example/mcp",
                "sub": "auth0|researcher-without-permission",
                "iat": now,
                "exp": now + 300,
                "scope": "openid profile",
                "client_id": "mcp-client",
            },
            private_key,
            algorithm="RS256",
        )
        store = FakeStore()
        verifier = HybridTokenVerifier(
            store,
            "https://control.example/mcp",
            auth0_issuer="https://brainai.us.auth0.com/",
            auth0_audience="https://control.example/mcp",
            jwk_client=JwkClient(),
        )

        self.assertIsNone(await verifier.verify_token(token))
        self.assertNotIn("auth0:auth0|researcher-without-permission", store.external_credentials)

    async def test_auth0_permission_claim_is_accepted(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()

        class SigningKey:
            key = public_key

        class JwkClient:
            def get_signing_key_from_jwt(self, _token: str) -> SigningKey:
                return SigningKey()

        now = int(time.time())
        token = jwt.encode(
            {
                "iss": "https://brainai.us.auth0.com/",
                "aud": "https://control.example/mcp",
                "sub": "email|researcher-with-permission",
                "iat": now,
                "exp": now + 300,
                "scope": "openid profile",
                "permissions": ["conn-pilot:use"],
                "client_id": "mcp-client",
            },
            private_key,
            algorithm="RS256",
        )
        store = FakeStore()
        verifier = HybridTokenVerifier(
            store,
            "https://control.example/mcp",
            auth0_issuer="https://brainai.us.auth0.com/",
            auth0_audience="https://control.example/mcp",
            jwk_client=JwkClient(),
        )

        access = await verifier.verify_token(token)
        self.assertIsNotNone(access)
        assert access is not None
        self.assertIn("conn-pilot:use", access.scopes)

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
            topics = await client.call_tool("list_guidance_topics", {})
            guidance = await client.call_tool(
                "get_parameter_guidance",
                {
                    "component_id": "reported_denoising",
                    "parameter_name": "bandpass_filter",
                    "limit": 2,
                },
            )
        self.assertEqual(
            tools,
            {
                "get_product_capabilities",
                "start_available_flow",
                "run_available_flow",
                "list_pipelines",
                "list_datasets",
                "get_system_health",
                "create_review_link",
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
                "get_subject_qc",
                "set_subject_qc_decision",
                "record_scientific_decision",
                "request_second_level_recalculation",
                "get_second_level_recalculation",
                "generate_reproducibility_package",
                "get_result_download_url",
                "list_guidance_topics",
                "get_parameter_guidance",
                "compare_method_options",
                "get_evidence_record",
                "validate_parameter_choice",
                "record_method_decision",
                "list_method_decisions",
                "list_unresolved_project_parameters",
                "get_project_parameter_guidance",
                "resolve_project_parameter",
            },
        )
        self.assertEqual(pipelines.structured_content["data"]["count"], 1)
        self.assertEqual(datasets.structured_content["data"]["count"], 1)
        self.assertGreater(topics.structured_content["data"]["count"], 1)
        self.assertEqual(guidance.structured_content["data"]["returned_count"], 2)

    def test_guided_product_flow_is_discoverable_and_stops_for_scientific_choices(self) -> None:
        store = FakeStore()
        service = ControlPlaneService(
            store, ROOT / "catalog", require_literature_decisions=True
        )
        capabilities = service.get_product_capabilities(storage_available=True)
        self.assertTrue(capabilities["data"]["ready_for_execution"])
        flow = capabilities["data"]["guided_flows"][0]
        self.assertEqual(flow["id"], "rsfmri_seed_to_voxel_one_sample_v1")
        self.assertEqual(flow["availability"][0]["dataset_id"], "study_001")
        self.assertTrue(flow["availability"][0]["available"])
        self.assertEqual(
            {item["id"] for item in flow["seed_options"]},
            {"left_amygdala", "right_amygdala"},
        )

        started = service.start_available_flow(
            "researcher-1",
            flow["id"],
            "study_001",
            "guided-pilot",
            "Estimate mean amygdala connectivity.",
            ["left_amygdala"],
            True,
        )
        self.assertEqual(started["data"]["status"], "needs_parameter_decisions")
        self.assertEqual(started["data"]["unresolved_parameter_count"], 7)
        self.assertEqual(
            started["data"]["next_action"]["tool"], "get_project_parameter_guidance"
        )
        project = started["data"]["project"]
        self.assertEqual(project["owner_subject"], "researcher-1")
        self.assertEqual(project["spec"]["design"]["groups"]["sample"], ["sub-001"])
        self.assertEqual(project["spec"]["seeds"][0]["conn_source"], "atlas.Amygdala l")

        blocked = service.run_available_flow("researcher-1", project["id"])
        self.assertTrue(blocked["ok"])
        self.assertEqual(blocked["data"]["status"], "needs_parameter_decisions")
        self.assertEqual(store.jobs, {})

    def test_guided_flow_rejects_unpublished_seed(self) -> None:
        service = ControlPlaneService(FakeStore(), ROOT / "catalog")
        with self.assertRaisesRegex(ValueError, "Unknown seed_ids"):
            service.start_available_flow(
                "owner", "rsfmri_seed_to_voxel_one_sample_v1", "study_001",
                "guided-pilot", "Question", ["hippocampus"], True,
            )

    def test_run_available_flow_queues_a_fully_documented_project(self) -> None:
        store = FakeStore()
        service = ControlPlaneService(
            store, ROOT / "catalog", require_literature_decisions=True
        )
        project = service.create_project(
            "owner", "study_001", "rsfmri_seed_to_voxel", "1.0.0", remote_spec()
        )["data"]["project"]
        pipeline = service.catalog.resolve("rsfmri_seed_to_voxel", "1.0.0")
        for index, (path, specification) in enumerate(
            pipeline.definition["project_contract"]["parameters"].items(), start=1
        ):
            guidance = specification.get("literature_guidance") or {}
            if not guidance.get("required_remote"):
                continue
            target = project["spec"]["parameters"]
            parts = path.split(".")
            for part in parts[:-1]:
                target = target[part]
            record = target[parts[-1]]
            decision_id = f"documented-{index}"
            record.update(
                method_decision_id=decision_id,
                evidence_ids=[f"evidence-{index}"],
                corpus_version="corpus-v1",
                confirmed_by_investigator=True,
            )
            store.method_decisions.append(
                {
                    "id": decision_id,
                    "owner_subject": "owner",
                    "project_id": project["id"],
                    "parameter_path": path,
                    "selected_value": record["value"],
                    "evidence_ids": record["evidence_ids"],
                    "corpus_version": record["corpus_version"],
                }
            )
        response = service.run_available_flow("owner", project["id"])
        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["status"], "queued")
        self.assertEqual(response["data"]["next_action"]["tool"], "get_job_status")
        self.assertEqual(response["data"]["job"]["phase"], "waiting_for_worker")
        repeated = service.run_available_flow("owner", project["id"])
        self.assertTrue(repeated["data"]["reused_existing_job"])
        self.assertEqual(repeated["data"]["job"]["id"], response["data"]["job"]["id"])
        self.assertEqual(len(store.jobs), 1)

    def test_subject_qc_decisions_are_versioned_and_keep_review_layers_separate(self) -> None:
        store = FakeStore()
        service = ControlPlaneService(store, ROOT / "catalog")
        project = store.create_project(
            "owner", "study_001", "rsfmri_seed_to_voxel", "1.0.0", remote_spec()
        )
        job = store.create_job(project)
        job.update(
            state="succeeded",
            result_version="sha256:result-one",
            result_summary={
                "qc": {
                    "technical_completeness": {"passed": True, "artifact_counts": {}},
                    "art_thresholds": {"global_signal_z": 3, "motion_mm": 0.5},
                    "subjects": [
                        {
                            "subject_id": "sub-001",
                            "qc_images": 1,
                            "preprocessing_qc": 3,
                            "metrics": {"outlier_count": 2, "outlier_percent": 1.25},
                        },
                        {
                            "subject_id": "sub-002",
                            "qc_images": 1,
                            "preprocessing_qc": 3,
                            "metrics": {"outlier_count": 8, "outlier_percent": 5.0},
                        },
                    ],
                }
            },
        )
        store.artifacts.extend(
            [
                {
                    "id": "art-1",
                    "job_id": job["id"],
                    "kind": "qc_images",
                    "name": "art_screenshot.jpg",
                    "object_key": "jobs/one/art-1.jpg",
                    "subject_id": "sub-001",
                },
                {
                    "id": "art-2",
                    "job_id": job["id"],
                    "kind": "qc_images",
                    "name": "art_screenshot.jpg",
                    "object_key": "jobs/one/art-2.jpg",
                    "subject_id": "sub-002",
                },
                {
                    "id": "second-1",
                    "job_id": job["id"],
                    "kind": "second_level_maps",
                    "name": "SPM.mat",
                    "object_key": "jobs/one/SPM.mat",
                    "subject_id": None,
                },
            ]
        )

        evidence = service.get_subject_qc_evidence("owner", job["id"], "sub-001")
        self.assertEqual(evidence["data"]["subjects"][0]["metrics"]["outlier_count"], 2)
        self.assertEqual(evidence["data"]["subjects"][0]["art_images"][0]["id"], "art-1")

        with self.assertRaisesRegex(ValueError, "justification"):
            service.set_subject_qc_decision(
                "owner", job["id"], "sha256:result-one", "sub-002", "exclude"
            )
        accepted = service.set_subject_qc_decision(
            "owner", job["id"], "sha256:result-one", "sub-001", "accept"
        )
        self.assertEqual(accepted["data"]["decision"]["decided_by"], "owner")
        excluded = service.set_subject_qc_decision(
            "owner",
            job["id"],
            "sha256:result-one",
            "sub-002",
            "exclude",
            "Excessive ART outliers after visual review.",
        )
        review = excluded["data"]["review"]
        self.assertTrue(review["technical_completeness"]["passed"])
        self.assertTrue(review["subject_quality"]["complete"])
        self.assertEqual(review["second_level"]["status"], "stale")
        self.assertTrue(review["second_level"]["blocked"])
        self.assertFalse(review["scientific_acceptance"]["eligible"])
        with self.assertRaisesRegex(ValueError, "acceptance is blocked"):
            service.record_scientific_decision(
                "owner",
                job["id"],
                "sha256:result-one",
                review["sample"]["version"],
                "accept",
                "Reviewed.",
            )

        restored = service.set_subject_qc_decision(
            "owner", job["id"], "sha256:result-one", "sub-002", "accept"
        )["data"]["review"]
        self.assertEqual(restored["second_level"]["status"], "current")
        self.assertTrue(restored["scientific_acceptance"]["eligible"])
        scientific = service.record_scientific_decision(
            "owner",
            job["id"],
            "sha256:result-one",
            restored["sample"]["version"],
            "accept",
            "Technical and subject-level review completed.",
        )
        self.assertEqual(
            scientific["data"]["review"]["scientific_acceptance"]["status"], "accept"
        )

        with self.assertRaisesRegex(ValueError, "result_version"):
            service.set_subject_qc_decision(
                "owner", job["id"], "sha256:old", "sub-001", "needs_review"
            )

    def test_literature_decision_is_validated_and_persisted_with_snapshot(self) -> None:
        store = FakeStore()
        service = ControlPlaneService(store, ROOT / "catalog")
        created = service.create_project(
            "owner", "study_001", "rsfmri_seed_to_voxel", "1.0.0", remote_spec()
        )
        project_id = created["data"]["project"]["id"]
        guidance = service.get_parameter_guidance(
            "reported_denoising", "bandpass_filter", limit=1
        )
        observation = guidance["data"]["observations"][0]
        recorded = service.record_method_decision(
            "owner",
            project_id,
            "reported_denoising",
            "bandpass_filter",
            observation["value"],
            [observation["evidence_id"]],
            "Investigator selected this reported range after reviewing applicability.",
        )
        decisions = service.list_method_decisions("owner", project_id)
        self.assertEqual(recorded["data"]["evidence_alignment"], "exact_explicit_observation")
        self.assertFalse(recorded["data"]["scientific_validity_determined"])
        self.assertEqual(decisions["data"]["count"], 1)
        self.assertEqual(len(store.method_decisions[0]["evidence_snapshot"]), 1)

    def test_strict_remote_project_requires_and_persists_executable_decisions(self) -> None:
        store = FakeStore()
        service = ControlPlaneService(
            store,
            ROOT / "catalog",
            require_literature_decisions=True,
        )
        created = service.create_project(
            "owner", "study_001", "rsfmri_seed_to_voxel", "1.0.0", remote_spec()
        )
        project_id = created["data"]["project"]["id"]
        unresolved = service.list_unresolved_project_parameters("owner", project_id)
        self.assertEqual(unresolved["data"]["required_count"], 7)
        self.assertEqual(unresolved["data"]["unresolved_count"], 7)
        blocked = service.validate_project("owner", project_id)
        self.assertFalse(blocked["ok"])
        self.assertIn(
            "Unresolved literature-guided parameters",
            blocked["errors"][0],
        )

        guidance = service.get_project_parameter_guidance(
            "owner", project_id, "denoising.bandpass_filter_hz"
        )
        option = guidance["data"]["options"][0]
        resolved = service.resolve_project_parameter(
            "owner",
            project_id,
            "denoising.bandpass_filter_hz",
            option["value"],
            [option["evidence_ids"][0]],
            "Chosen after the investigator reviewed acquisition and denoising compatibility.",
        )
        self.assertEqual(resolved["data"]["remaining_unresolved_count"], 6)
        record = store.projects[project_id]["spec"]["parameters"]["denoising"][
            "bandpass_filter_hz"
        ]
        self.assertTrue(record["confirmed_by_investigator"])
        self.assertEqual(record["method_decision_id"], store.method_decisions[0]["id"])
        self.assertEqual(len(store.method_decisions[0]["evidence_snapshot"]), 1)

    def test_project_creation_rejects_forged_decision_provenance(self) -> None:
        spec = remote_spec()
        record = spec["parameters"]["denoising"]["bandpass_filter_hz"]
        record.update(
            method_decision_id="invented",
            evidence_ids=["invented"],
            corpus_version="invented",
        )
        service = ControlPlaneService(FakeStore(), ROOT / "catalog")
        with self.assertRaisesRegex(ValueError, "must be created by"):
            service.create_project(
                "owner", "study_001", "rsfmri_seed_to_voxel", "1.0.0", spec
            )

    def test_resolution_status_detects_a_mismatched_persisted_decision(self) -> None:
        store = FakeStore()
        service = ControlPlaneService(store, ROOT / "catalog")
        project_id = service.create_project(
            "owner", "study_001", "rsfmri_seed_to_voxel", "1.0.0", remote_spec()
        )["data"]["project"]["id"]
        option = service.get_project_parameter_guidance(
            "owner", project_id, "preprocessing.smoothing_fwhm_mm", limit=1
        )["data"]["options"][0]
        service.resolve_project_parameter(
            "owner",
            project_id,
            "preprocessing.smoothing_fwhm_mm",
            option["value"],
            [option["evidence_ids"][0]],
            "Investigator selected this value after review.",
        )
        store.method_decisions[0]["selected_value"] = 6.0
        status = service.list_unresolved_project_parameters("owner", project_id)
        smoothing = next(
            item
            for item in status["data"]["parameters"]
            if item["parameter_path"] == "preprocessing.smoothing_fwhm_mm"
        )
        self.assertFalse(smoothing["resolved"])
        self.assertEqual(
            smoothing["resolution_integrity"], "missing_or_mismatched_decision"
        )

    def test_execution_plan_contains_resolved_parameter_provenance(self) -> None:
        store = FakeStore()
        service = ControlPlaneService(store, ROOT / "catalog")
        project_id = service.create_project(
            "owner", "study_001", "rsfmri_seed_to_voxel", "1.0.0", remote_spec()
        )["data"]["project"]["id"]
        guidance = service.get_project_parameter_guidance(
            "owner", project_id, "preprocessing.smoothing_fwhm_mm", limit=1
        )["data"]
        option = guidance["options"][0]
        service.resolve_project_parameter(
            "owner",
            project_id,
            "preprocessing.smoothing_fwhm_mm",
            option["value"],
            [option["evidence_ids"][0]],
            "Investigator reviewed the spatial scale and selected this cited value.",
        )
        plan = service.generate_execution_plan("owner", project_id)
        self.assertTrue(plan["ok"])
        self.assertIn(
            "preprocessing.smoothing_fwhm_mm", plan["data"]["resolved_parameters"]
        )
        self.assertEqual(
            plan["data"]["method_decisions"][0]["parameter_path"],
            "preprocessing.smoothing_fwhm_mm",
        )

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

    def test_worker_does_not_restore_a_failed_local_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "worker-state.json"
            state_path.write_text(
                '{"schema_version":"conn_pilot_worker_state_v1","local_job_id":"failed-1"}',
                encoding="utf-8",
            )

            class Store:
                @staticmethod
                def get(_job_id: str) -> dict[str, Any]:
                    return {"id": "failed-1", "state": "failed"}

            class Service:
                store = Store()

            self.assertIsNone(
                __import__(
                    "conn_pilot.distributed_worker", fromlist=["DistributedWorker"]
                ).DistributedWorker._restored_local_job_id(state_path, Service())
            )

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
