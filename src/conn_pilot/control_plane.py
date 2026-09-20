from __future__ import annotations

import json
import os
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

try:
    import boto3
except ImportError:  # Allows contract tests before production dependencies are installed.
    boto3 = None  # type: ignore[assignment]
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse

from .catalog import Catalog
from .control_store import PostgresControlStore
from .project import validate_project as validate_project_definition


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_RESPONSE_SCHEMA = "conn_pilot_control_response_v1"
REMOTE_SPEC_FIELDS = {"project", "design", "seeds", "parameters"}


class Store(Protocol):
    def verify_credential(self, token: str) -> dict[str, Any] | None: ...
    def list_datasets(self) -> list[dict[str, Any]]: ...
    def get_dataset(self, dataset_id: str) -> dict[str, Any] | None: ...
    def create_project(
        self, owner_subject: str, dataset_id: str, pipeline_id: str, pipeline_version: str, spec: dict[str, Any]
    ) -> dict[str, Any]: ...
    def get_project(self, project_id: str, subject: str | None = None) -> dict[str, Any] | None: ...
    def save_validation(self, project_id: str, validation: dict[str, Any]) -> None: ...
    def create_job(self, project: dict[str, Any]) -> dict[str, Any]: ...
    def get_job(self, job_id: str, subject: str | None = None) -> dict[str, Any] | None: ...
    def get_events(self, job_id: str, subject: str) -> list[dict[str, Any]]: ...
    def list_artifacts(self, job_id: str, subject: str) -> list[dict[str, Any]]: ...
    def register_worker(self, worker_id: str, label: str, capabilities: dict[str, Any]) -> None: ...
    def sync_datasets(self, worker_id: str, datasets: list[dict[str, Any]]) -> None: ...
    def claim_job(self, worker_id: str, dataset_ids: list[str], lease_seconds: int) -> dict[str, Any] | None: ...
    def heartbeat_job(self, job_id: str, worker_id: str, phase: str, lease_seconds: int) -> bool: ...
    def complete_job(
        self, job_id: str, worker_id: str, state: str, summary: dict[str, Any], error: str | None
    ) -> bool: ...
    def add_artifact(self, job_id: str, worker_id: str, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ControlSettings:
    database_url: str
    public_base_url: str
    admin_subject: str
    admin_token: str
    worker_token: str
    host: str
    port: int
    lease_seconds: int = 300

    @property
    def mcp_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/mcp"


class DatabaseTokenVerifier(TokenVerifier):
    def __init__(self, store: Store, resource: str) -> None:
        self.store = store
        self.resource = resource

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = self.store.verify_credential(token)
        if not identity:
            return None
        return AccessToken(
            token=token,
            client_id="conn-pilot-codex",
            subject=str(identity["subject"]),
            scopes=["conn-pilot:use"],
            resource=self.resource,
        )


class ArtifactStorage:
    def __init__(self) -> None:
        self.bucket = os.environ.get("BUCKET") or os.environ.get("S3_BUCKET", "")
        self.endpoint = os.environ.get("ENDPOINT") or os.environ.get("S3_ENDPOINT", "")
        access_key = os.environ.get("ACCESS_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID", "")
        secret_key = os.environ.get("SECRET_ACCESS_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        region = os.environ.get("REGION") or os.environ.get("AWS_REGION", "auto")
        self.available = bool(boto3 and self.bucket and self.endpoint and access_key and secret_key)
        self.client = (
            boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
            if self.available
            else None
        )

    def prepare_upload(self, job_id: str, name: str, content_type: str) -> dict[str, str]:
        if not self.client:
            raise ValueError("Artifact bucket is not configured")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._") or "artifact"
        object_key = f"jobs/{job_id}/{uuid.uuid4().hex}-{safe_name}"
        url = self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": object_key, "ContentType": content_type},
            ExpiresIn=3600,
        )
        return {"object_key": object_key, "upload_url": url}

    def download_url(self, object_key: str) -> str:
        if not self.client:
            raise ValueError("Artifact bucket is not configured")
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": object_key}, ExpiresIn=3600
        )


class ControlPlaneService:
    def __init__(self, store: Store, catalog_root: str | Path) -> None:
        self.store = store
        self.catalog = Catalog(catalog_root)

    def list_pipelines(self) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        for record in self.catalog.list_pipelines():
            pipeline = self.catalog.resolve(record["id"], record["version"])
            records.append(
                {
                    "id": pipeline.id,
                    "version": pipeline.version,
                    "family": record["family"],
                    "status": record["status"],
                    "description": pipeline.definition.get("description", ""),
                    "supported_designs": pipeline.definition["project_contract"].get("design_types", []),
                }
            )
        return _response("list_pipelines", {"pipelines": records, "count": len(records)})

    def list_datasets(self) -> dict[str, Any]:
        datasets = self.store.list_datasets()
        return _response("list_datasets", {"datasets": datasets, "count": len(datasets)})

    def inspect_dataset(self, dataset_id: str) -> dict[str, Any]:
        dataset = self._dataset(dataset_id)
        return _response(
            "inspect_dataset",
            {"dataset": dataset, "cached": True, "requires_worker": dataset.get("status") != "ready"},
        )

    def create_project(
        self,
        subject: str,
        dataset_id: str,
        pipeline_id: str,
        pipeline_version: str,
        spec: dict[str, Any],
    ) -> dict[str, Any]:
        self._dataset(dataset_id)
        self.catalog.resolve(pipeline_id, pipeline_version)
        if not isinstance(spec, dict):
            raise ValueError("spec must be an object")
        unknown = sorted(set(spec) - REMOTE_SPEC_FIELDS)
        missing = sorted(REMOTE_SPEC_FIELDS - set(spec))
        if unknown:
            raise ValueError(f"Unknown project spec fields: {', '.join(unknown)}")
        if missing:
            raise ValueError(f"Missing project spec fields: {', '.join(missing)}")
        project = self.store.create_project(subject, dataset_id, pipeline_id, pipeline_version, spec)
        return _response("create_project", {"project": project})

    def validate_project(self, subject: str, project_id: str) -> dict[str, Any]:
        project = self._project(project_id, subject)
        dataset = self._dataset(project["dataset_id"])
        pipeline = self.catalog.resolve(project["pipeline_id"], project["pipeline_version"])
        definition = materialize_remote_project(project, dataset, use_placeholders=True)
        result = validate_project_definition(definition, pipeline, check_paths=False)
        validation = {
            "valid": result.valid,
            "errors": list(result.errors),
            "warnings": list(result.warnings),
            "dataset_fingerprint": dataset["fingerprint"],
            "dataset_status": dataset["status"],
        }
        if dataset["status"] != "ready":
            validation["valid"] = False
            validation["errors"].append("Dataset is not ready on its assigned worker")
        self.store.save_validation(project_id, validation)
        return _response(
            "validate_project",
            {"project_id": project_id, **validation},
            ok=bool(validation["valid"]),
            errors=validation["errors"],
            warnings=validation["warnings"],
        )

    def generate_execution_plan(self, subject: str, project_id: str) -> dict[str, Any]:
        validation = self.validate_project(subject, project_id)
        project = self._project(project_id, subject)
        dataset = self._dataset(project["dataset_id"])
        pipeline = self.catalog.resolve(project["pipeline_id"], project["pipeline_version"])
        stages = [
            {"order": index, "id": stage["id"], "version": str(stage["version"])}
            for index, stage in enumerate(pipeline.stages, start=1)
        ]
        data = {
            "project_id": project_id,
            "dataset_id": dataset["id"],
            "dataset_fingerprint": dataset["fingerprint"],
            "worker_id": dataset["worker_id"],
            "pipeline": {"id": pipeline.id, "version": pipeline.version},
            "stages": stages,
            "execution": {"mode": "pull_worker", "concurrency": 1, "input_location": "worker_local"},
            "ready_to_submit": validation["ok"],
        }
        return _response(
            "generate_execution_plan",
            data,
            ok=validation["ok"],
            errors=validation["errors"],
            warnings=validation["warnings"],
        )

    def submit_job(self, subject: str, project_id: str) -> dict[str, Any]:
        validation = self.validate_project(subject, project_id)
        if not validation["ok"]:
            return _response(
                "submit_job", {}, ok=False, errors=validation["errors"], warnings=validation["warnings"]
            )
        project = self._project(project_id, subject)
        job = self.store.create_job(project)
        return _response("submit_job", {"job": job})

    def get_job_status(self, subject: str, job_id: str) -> dict[str, Any]:
        job = self._job(job_id, subject)
        return _response(
            "get_job_status",
            {"job": job, "terminal": job["state"] in {"succeeded", "failed", "cancelled"}},
            ok=job["state"] != "failed",
            errors=[job["error"]] if job.get("error") else [],
        )

    def get_job_logs(self, subject: str, job_id: str) -> dict[str, Any]:
        self._job(job_id, subject)
        return _response("get_job_logs", {"job_id": job_id, "events": self.store.get_events(job_id, subject)})

    def list_results(self, subject: str, job_id: str) -> dict[str, Any]:
        job = self._job(job_id, subject)
        artifacts = self.store.list_artifacts(job_id, subject)
        return _response(
            "list_results",
            {"job_id": job_id, "state": job["state"], "artifacts": artifacts, "count": len(artifacts)},
        )

    def get_qc_summary(self, subject: str, job_id: str) -> dict[str, Any]:
        job = self._job(job_id, subject)
        summary = job.get("result_summary") or {}
        return _response(
            "get_qc_summary",
            {
                "job_id": job_id,
                "state": job["state"],
                "qc": summary.get("qc", {}),
                "scientific_review_required": True,
            },
        )

    def _dataset(self, dataset_id: str) -> dict[str, Any]:
        dataset = self.store.get_dataset(dataset_id)
        if not dataset:
            raise ValueError(f"Unknown dataset: {dataset_id}")
        return dataset

    def _project(self, project_id: str, subject: str) -> dict[str, Any]:
        project = self.store.get_project(project_id, subject)
        if not project:
            raise ValueError(f"Unknown project: {project_id}")
        return project

    def _job(self, job_id: str, subject: str) -> dict[str, Any]:
        job = self.store.get_job(job_id, subject)
        if not job:
            raise ValueError(f"Unknown job: {job_id}")
        return job


def materialize_remote_project(
    project: dict[str, Any], dataset: dict[str, Any], *, use_placeholders: bool
) -> dict[str, Any]:
    metadata = dataset.get("metadata", {})
    subjects = metadata.get("subjects", [])
    root = f"/datasets/{dataset['id']}" if use_placeholders else str(metadata.get("root", ""))
    materialized_subjects = []
    for item in subjects:
        subject_id = str(item["id"] if isinstance(item, dict) else item)
        if use_placeholders:
            functional = [f"{root}/{subject_id}/functional.nii.gz"]
            structural = [f"{root}/{subject_id}/structural.nii.gz"]
        else:
            functional = list(item.get("functional", []))
            structural = list(item.get("structural", []))
        materialized_subjects.append(
            {"id": subject_id, "functional": functional, "structural": structural}
        )
    spec = project["spec"]
    return {
        "schema_version": "conn_pilot_project_v1",
        "pipeline": {"id": project["pipeline_id"], "version": project["pipeline_version"]},
        "project": spec["project"],
        "dataset": {
            "layout": metadata.get("layout", "bids"),
            "root": root,
            "tr_seconds": metadata.get("tr_seconds"),
        },
        "subjects": materialized_subjects,
        "design": spec["design"],
        "seeds": spec["seeds"],
        "parameters": spec["parameters"],
    }


def load_control_settings() -> ControlSettings:
    port = int(os.environ.get("PORT", os.environ.get("CONN_PILOT_REMOTE_PORT", "8000")))
    base = os.environ.get("CONN_PILOT_PUBLIC_BASE_URL", f"http://127.0.0.1:{port}").rstrip("/")
    values = ControlSettings(
        database_url=os.environ.get("DATABASE_URL", ""),
        public_base_url=base,
        admin_subject=os.environ.get("CONN_PILOT_ADMIN_SUBJECT", "owner"),
        admin_token=os.environ.get("CONN_PILOT_ADMIN_TOKEN", ""),
        worker_token=os.environ.get("CONN_PILOT_WORKER_TOKEN", ""),
        host=os.environ.get("CONN_PILOT_REMOTE_HOST", "0.0.0.0"),
        port=port,
        lease_seconds=int(os.environ.get("CONN_PILOT_LEASE_SECONDS", "300")),
    )
    if len(values.admin_token) < 32 or len(values.worker_token) < 32:
        raise ValueError("Admin and worker tokens must contain at least 32 characters")
    parsed = urlsplit(values.public_base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        raise ValueError("CONN_PILOT_PUBLIC_BASE_URL must be an HTTP(S) origin without a path")
    return values


def build_control_plane_server(
    settings: ControlSettings,
    store: Store,
    *,
    artifact_storage: ArtifactStorage | None = None,
    require_mcp_auth: bool = True,
) -> MCPServer:
    storage = artifact_storage or ArtifactStorage()
    service = ControlPlaneService(store, REPO_ROOT / "catalog")
    parsed = urlsplit(settings.public_base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    verifier = DatabaseTokenVerifier(store, settings.mcp_url) if require_mcp_auth else None
    auth = (
        AuthSettings(
            issuer_url=AnyHttpUrl(f"{origin}/"),
            resource_server_url=AnyHttpUrl(settings.mcp_url),
            required_scopes=["conn-pilot:use"],
            validate_token_resource=True,
        )
        if require_mcp_auth
        else None
    )
    server = MCPServer(
        "CONN Pilot",
        instructions=(
            "Use dataset_id, project_id and job_id; never invent server paths. Submit long CONN analyses "
            "as jobs and poll get_job_status. Scientific QC decisions always require investigator review."
        ),
        token_verifier=verifier,
        auth=auth,
    )
    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)

    def subject() -> str:
        token = get_access_token()
        if token and token.subject:
            return token.subject
        if not require_mcp_auth:
            return settings.admin_subject
        raise ValueError("Authenticated subject is unavailable")

    @server.tool(annotations=read_only)
    def list_pipelines() -> dict[str, Any]:
        """List validated CONN pipelines available to remote projects."""
        return service.list_pipelines()

    @server.tool(annotations=read_only)
    def list_datasets() -> dict[str, Any]:
        """List sanitized metadata for datasets registered by an online local worker."""
        return service.list_datasets()

    @server.tool(annotations=read_only)
    def inspect_dataset(dataset_id: str) -> dict[str, Any]:
        """Read the worker's cached dataset inspection without exposing local filesystem paths."""
        return service.inspect_dataset(dataset_id)

    @server.tool()
    def create_project(
        dataset_id: str, pipeline_id: str, pipeline_version: str, spec: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a remote project from a dataset identifier and a path-free scientific specification."""
        return service.create_project(subject(), dataset_id, pipeline_id, pipeline_version, spec)

    @server.tool(annotations=read_only)
    def validate_project(project_id: str) -> dict[str, Any]:
        """Validate a remote project contract against cached dataset metadata."""
        return service.validate_project(subject(), project_id)

    @server.tool(annotations=read_only)
    def generate_execution_plan(project_id: str) -> dict[str, Any]:
        """Generate the stages and worker assignment for a validated remote project."""
        return service.generate_execution_plan(subject(), project_id)

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False))
    def submit_job(project_id: str) -> dict[str, Any]:
        """Queue a project for execution when its assigned local worker becomes available."""
        return service.submit_job(subject(), project_id)

    @server.tool(annotations=read_only)
    def get_job_status(job_id: str) -> dict[str, Any]:
        """Read the persistent remote state of a queued or running CONN job."""
        return service.get_job_status(subject(), job_id)

    @server.tool(annotations=read_only)
    def get_job_logs(job_id: str) -> dict[str, Any]:
        """Read structured lifecycle events reported by the control plane and worker."""
        return service.get_job_logs(subject(), job_id)

    @server.tool(annotations=read_only)
    def list_results(job_id: str) -> dict[str, Any]:
        """List selected result artifacts uploaded by the local worker."""
        return service.list_results(subject(), job_id)

    @server.tool(annotations=read_only)
    def get_qc_summary(job_id: str) -> dict[str, Any]:
        """Read the technical QC summary while keeping scientific acceptance under human review."""
        return service.get_qc_summary(subject(), job_id)

    @server.tool(annotations=read_only)
    def get_result_download_url(job_id: str, artifact_id: str) -> dict[str, Any]:
        """Create a one-hour download URL for one authorized result artifact."""
        artifacts = service.store.list_artifacts(job_id, subject())
        artifact = next((item for item in artifacts if item["id"] == artifact_id), None)
        if not artifact:
            raise ValueError("Unknown artifact")
        return _response(
            "get_result_download_url",
            {"artifact_id": artifact_id, "url": storage.download_url(artifact["object_key"]), "expires_in": 3600},
        )

    def authorized_worker(request: Request) -> bool:
        header = request.headers.get("authorization", "")
        supplied = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
        return bool(supplied) and secrets.compare_digest(supplied, settings.worker_token)

    async def worker_json(request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
        if not authorized_worker(request):
            return None, JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return None, JSONResponse({"error": "invalid_json"}, status_code=400)
        if not isinstance(body, dict):
            return None, JSONResponse({"error": "body_must_be_object"}, status_code=400)
        return body, None

    @server.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "conn-pilot-control-plane"})

    @server.custom_route("/worker/v1/heartbeat", methods=["POST"])
    async def worker_heartbeat(request: Request) -> JSONResponse:
        body, error = await worker_json(request)
        if error:
            return error
        assert body is not None
        worker_id = str(body.get("worker_id", "")).strip()
        if not worker_id:
            return JSONResponse({"error": "worker_id_required"}, status_code=400)
        datasets = body.get("datasets", [])
        if not isinstance(datasets, list):
            return JSONResponse({"error": "datasets_must_be_array"}, status_code=400)
        store.register_worker(worker_id, str(body.get("label", worker_id)), body.get("capabilities", {}))
        store.sync_datasets(worker_id, datasets)
        return JSONResponse({"ok": True, "server_time": _now(), "lease_seconds": settings.lease_seconds})

    @server.custom_route("/worker/v1/claim", methods=["POST"])
    async def worker_claim(request: Request) -> JSONResponse:
        body, error = await worker_json(request)
        if error:
            return error
        assert body is not None
        worker_id = str(body.get("worker_id", ""))
        dataset_ids = [str(value) for value in body.get("dataset_ids", [])]
        job = store.claim_job(worker_id, dataset_ids, settings.lease_seconds)
        return JSONResponse({"ok": True, "job": job})

    @server.custom_route("/worker/v1/jobs/{job_id:str}/heartbeat", methods=["POST"])
    async def job_heartbeat(request: Request) -> JSONResponse:
        body, error = await worker_json(request)
        if error:
            return error
        assert body is not None
        updated = store.heartbeat_job(
            request.path_params["job_id"],
            str(body.get("worker_id", "")),
            str(body.get("phase", "running")),
            settings.lease_seconds,
        )
        return JSONResponse({"ok": updated}, status_code=200 if updated else 409)

    @server.custom_route("/worker/v1/jobs/{job_id:str}/complete", methods=["POST"])
    async def job_complete(request: Request) -> JSONResponse:
        body, error = await worker_json(request)
        if error:
            return error
        assert body is not None
        updated = store.complete_job(
            request.path_params["job_id"],
            str(body.get("worker_id", "")),
            str(body.get("state", "")),
            body.get("summary", {}),
            body.get("error"),
        )
        return JSONResponse({"ok": updated}, status_code=200 if updated else 409)

    @server.custom_route("/worker/v1/jobs/{job_id:str}/artifacts/prepare", methods=["POST"])
    async def artifact_prepare(request: Request) -> JSONResponse:
        body, error = await worker_json(request)
        if error:
            return error
        assert body is not None
        try:
            prepared = storage.prepare_upload(
                request.path_params["job_id"], str(body.get("name", "artifact")), str(body.get("content_type", "application/octet-stream"))
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)
        return JSONResponse({"ok": True, **prepared})

    @server.custom_route("/worker/v1/jobs/{job_id:str}/artifacts/complete", methods=["POST"])
    async def artifact_complete(request: Request) -> JSONResponse:
        body, error = await worker_json(request)
        if error:
            return error
        assert body is not None
        try:
            artifact = store.add_artifact(
                request.path_params["job_id"],
                str(body.get("worker_id", "")),
                kind=str(body.get("kind", "result")),
                name=str(body["name"]),
                object_key=str(body["object_key"]),
                bytes_count=int(body["bytes"]),
                sha256=str(body["sha256"]),
                content_type=str(body.get("content_type", "application/octet-stream")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "artifact": artifact})

    return server


def _response(
    operation: str,
    data: dict[str, Any],
    *,
    ok: bool = True,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": CONTROL_RESPONSE_SCHEMA,
        "operation": operation,
        "ok": ok,
        "generated_at": _now(),
        "data": data,
        "errors": errors or [],
        "warnings": warnings or [],
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    settings = load_control_settings()
    store = PostgresControlStore(settings.database_url)
    store.ensure_schema()
    store.bootstrap_credential(settings.admin_subject, settings.admin_token)
    server = build_control_plane_server(settings, store)
    parsed = urlsplit(settings.public_base_url)
    server.run(
        transport="streamable-http",
        host=settings.host,
        port=settings.port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[parsed.netloc, "127.0.0.1:*", "localhost:*"],
            allowed_origins=[f"{parsed.scheme}://{parsed.netloc}", "http://127.0.0.1:*", "http://localhost:*"],
        ),
    )


if __name__ == "__main__":
    main()
