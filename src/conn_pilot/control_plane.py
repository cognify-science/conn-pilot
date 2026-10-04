from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import jwt
from jwt import PyJWKClient

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

from . import __version__
from .catalog import Catalog
from .control_store import PostgresControlStore
from .io import nested_get
from .literature import LiteratureEvidenceService
from .parameter_resolver import ParameterResolver
from .project import validate_project as validate_project_definition
from .quality_report import build_experiment_quality_report
from .reporting import build_reproducibility_package
from .seed_catalog import SeedCatalog
from .pipeline_graph import (
    build_node_execution_plan,
    compare_node_plans,
    composition_snapshot,
    resolve_pipeline_graph,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_RESPONSE_SCHEMA = "conn_pilot_control_response_v1"
REMOTE_SPEC_FIELDS = {"project", "design", "seeds", "parameters"}
REMOTE_SPEC_OPTIONAL_FIELDS = {"composition", "hypothesis"}
GUIDED_FLOW_ID = "rsfmri_seed_to_voxel_v1"
LEGACY_GUIDED_FLOW_IDS = {"rsfmri_seed_to_voxel_one_sample_v1"}
GUIDED_PIPELINE = ("rsfmri_seed_to_voxel", "1.0.0")
ROI_TO_ROI_FLOW_ID = "rsfmri_roi_to_roi_v1"
GUIDED_FLOWS = {
    GUIDED_FLOW_ID: GUIDED_PIPELINE,
    ROI_TO_ROI_FLOW_ID: ("rsfmri_roi_to_roi", "1.0.0"),
}
LEGACY_GUIDED_SEEDS = {
    "left_amygdala": "atlas.Amygdala l",
    "right_amygdala": "atlas.Amygdala r",
}
LOGGER = logging.getLogger(__name__)


class Store(Protocol):
    def verify_credential(self, token: str) -> dict[str, Any] | None: ...
    def ensure_external_credential(
        self, subject: str, *, provider: str, email: str | None = None
    ) -> dict[str, Any] | None: ...
    def list_datasets(self) -> list[dict[str, Any]]: ...
    def get_system_health(self) -> dict[str, Any]: ...
    def get_dataset(self, dataset_id: str) -> dict[str, Any] | None: ...
    def create_project(
        self, owner_subject: str, dataset_id: str, pipeline_id: str, pipeline_version: str, spec: dict[str, Any]
    ) -> dict[str, Any]: ...
    def get_project(self, project_id: str, subject: str | None = None) -> dict[str, Any] | None: ...
    def save_validation(self, project_id: str, validation: dict[str, Any]) -> None: ...
    def create_job(self, project: dict[str, Any]) -> dict[str, Any]: ...
    def get_reusable_job_for_project(
        self, project_id: str, subject: str
    ) -> dict[str, Any] | None: ...
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
    def add_generated_artifact(
        self, job_id: str, owner_subject: str, **kwargs: Any
    ) -> dict[str, Any]: ...
    def create_second_level_run(
        self, job_id: str, owner_subject: str, parent_result_version: str,
        sample_version: str, included_subject_ids: list[str], review_snapshot: dict[str, Any]
    ) -> dict[str, Any]: ...
    def list_second_level_runs(
        self, job_id: str, owner_subject: str, parent_result_version: str
    ) -> list[dict[str, Any]]: ...
    def get_second_level_run(
        self, run_id: str, owner_subject: str | None = None
    ) -> dict[str, Any] | None: ...
    def claim_second_level_run(
        self, worker_id: str, dataset_ids: list[str], lease_seconds: int
    ) -> dict[str, Any] | None: ...
    def heartbeat_second_level_run(
        self, run_id: str, worker_id: str, phase: str, lease_seconds: int
    ) -> bool: ...
    def complete_second_level_run(
        self, run_id: str, worker_id: str, state: str,
        summary: dict[str, Any], error: str | None
    ) -> bool: ...
    def record_subject_qc_decision(
        self, job_id: str, owner_subject: str, result_version: str, subject_id: str,
        decision: str, justification: str | None
    ) -> dict[str, Any]: ...
    def list_subject_qc_decisions(
        self, job_id: str, owner_subject: str, result_version: str
    ) -> list[dict[str, Any]]: ...
    def record_analysis_decision(
        self, job_id: str, owner_subject: str, result_version: str, sample_version: str,
        decision: str, rationale: str
    ) -> dict[str, Any]: ...
    def list_analysis_decisions(
        self, job_id: str, owner_subject: str, result_version: str
    ) -> list[dict[str, Any]]: ...
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
    ) -> dict[str, Any]: ...
    def list_method_decisions(self, project_id: str, subject: str) -> list[dict[str, Any]]: ...
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
    ) -> dict[str, Any]: ...


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
    auth0_issuer: str = ""
    auth0_audience: str = ""

    @property
    def mcp_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/mcp"


class HybridTokenVerifier(TokenVerifier):
    """Accept legacy local credentials and short-lived Auth0 JWT access tokens."""

    def __init__(
        self,
        store: Store,
        resource: str,
        *,
        auth0_issuer: str = "",
        auth0_audience: str = "",
        jwk_client: Any | None = None,
    ) -> None:
        self.store = store
        self.resource = resource
        self.auth0_issuer = auth0_issuer.rstrip("/") + "/" if auth0_issuer else ""
        self.auth0_audience = auth0_audience
        self.jwk_client = (
            jwk_client
            if jwk_client is not None
            else PyJWKClient(f"{self.auth0_issuer}.well-known/jwks.json", cache_keys=True)
            if self.auth0_issuer
            else None
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = self.store.verify_credential(token)
        if identity:
            scopes = ["conn-pilot:use"]
            if identity.get("role") == "admin":
                scopes.append("conn-pilot:admin")
            return AccessToken(
                token=token,
                client_id="conn-pilot-local",
                subject=str(identity["subject"]),
                scopes=scopes,
                resource=self.resource,
            )
        if not self.jwk_client or not self.auth0_issuer or not self.auth0_audience:
            LOGGER.warning("OAuth token rejected: verifier_not_configured")
            return None
        try:
            signing_key = await asyncio.to_thread(self.jwk_client.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.auth0_audience,
                issuer=self.auth0_issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            LOGGER.warning("OAuth token rejected: %s", type(exc).__name__)
            return None
        raw_scope = claims.get("scope", "")
        scopes = raw_scope.split() if isinstance(raw_scope, str) else list(raw_scope)
        raw_permissions = claims.get("permissions", [])
        permissions = (
            raw_permissions.split()
            if isinstance(raw_permissions, str)
            else list(raw_permissions)
        )
        scopes = list(dict.fromkeys([*scopes, *permissions]))
        if "conn-pilot:use" not in scopes:
            LOGGER.warning("OAuth token rejected: missing_required_scope")
            return None

        subject = f"auth0:{claims['sub']}"
        identity = self.store.ensure_external_credential(
            subject,
            provider="auth0",
            email=claims.get("email") if claims.get("email_verified") else None,
        )
        if not identity:
            LOGGER.warning("OAuth token rejected: external_identity_disabled")
            return None
        if identity.get("role") == "admin":
            scopes.append("conn-pilot:admin")
        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id") or claims.get("azp") or "oauth-client"),
            subject=subject,
            scopes=scopes,
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

    def put_bytes(self, job_id: str, name: str, content_type: str, content: bytes) -> str:
        if not self.client:
            raise ValueError("Artifact bucket is not configured")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._") or "artifact"
        object_key = f"jobs/{job_id}/{uuid.uuid4().hex}-{safe_name}"
        self.client.put_object(
            Bucket=self.bucket, Key=object_key, Body=content, ContentType=content_type
        )
        return object_key

    def get_bytes(self, object_key: str, *, max_bytes: int) -> bytes:
        if not self.client:
            raise ValueError("Artifact bucket is not configured")
        response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        declared = int(response.get("ContentLength") or 0)
        if declared > max_bytes:
            response["Body"].close()
            raise ValueError("Artifact exceeds the reproducibility package size limit")
        content = response["Body"].read(max_bytes + 1)
        response["Body"].close()
        if len(content) > max_bytes:
            raise ValueError("Artifact exceeds the reproducibility package size limit")
        return content


class ControlPlaneService:
    def __init__(
        self,
        store: Store,
        catalog_root: str | Path,
        literature_root: str | Path | None = None,
        *,
        require_literature_decisions: bool = False,
    ) -> None:
        self.store = store
        self.catalog = Catalog(catalog_root)
        self.seed_catalog = SeedCatalog(Path(catalog_root) / "seeds" / "conn25b.json")
        self.literature = LiteratureEvidenceService(
            literature_root or Path.cwd() / "knowledge" / "pipeline_review"
        )
        self.parameter_resolver = ParameterResolver(self.literature)
        self.require_literature_decisions = require_literature_decisions

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

    def list_available_seeds(
        self,
        query: str | None = None,
        collection: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search the versioned inventory of seed regions shipped with CONN."""
        return _response(
            "list_available_seeds",
            self.seed_catalog.search(
                query=query, collection=collection, limit=limit, offset=offset
            ),
        )

    def get_system_health(self, storage_available: bool) -> dict[str, Any]:
        health = self.store.get_system_health()
        health["artifact_storage_available"] = storage_available
        health["ready_for_execution"] = bool(
            storage_available and any(item.get("online") for item in health["workers"])
        )
        return _response("get_system_health", health)

    def get_product_capabilities(self, storage_available: bool) -> dict[str, Any]:
        """Describe the usable product surface and dataset-specific guided flows."""
        health = self.store.get_system_health()
        workers = {str(item.get("id")): item for item in health.get("workers", [])}
        datasets = self.store.list_datasets()
        availability = []
        for dataset in datasets:
            reasons: list[str] = []
            metadata = dataset.get("metadata") or {}
            if dataset.get("status") != "ready":
                reasons.append("dataset_not_ready")
            if metadata.get("layout") != "bids":
                reasons.append("bids_layout_required")
            worker = workers.get(str(dataset.get("worker_id")))
            if not worker or not worker.get("online"):
                reasons.append("assigned_worker_offline")
            if not storage_available:
                reasons.append("artifact_storage_unavailable")
            availability.append(
                {
                    "dataset_id": dataset["id"],
                    "dataset_label": dataset.get("label"),
                    "subject_count": metadata.get("subject_count"),
                    "worker_id": dataset.get("worker_id"),
                    "available": not reasons,
                    "unavailable_reasons": reasons,
                }
            )
        flows = []
        for flow_id, pipeline_ref in GUIDED_FLOWS.items():
            pipeline = self.catalog.resolve(*pipeline_ref)
            analysis = pipeline.definition.get("execution", {}).get("analysis", {})
            guided_parameters = [
                path
                for path, specification in pipeline.definition["project_contract"]
                .get("parameters", {}).items()
                if (specification.get("literature_guidance") or {}).get("required_remote")
            ]
            flows.append(
                {
                    "id": flow_id,
                    "label": (
                        "Resting-state seed-to-voxel"
                        if analysis.get("kind") == "seed_to_voxel"
                        else "Resting-state ROI-to-ROI"
                    ),
                    "status": pipeline.definition.get("status"),
                    "description": pipeline.definition.get("description", ""),
                    "pipeline": {"id": pipeline.id, "version": pipeline.version},
                    "design_options": pipeline.definition["project_contract"].get("design_types", []),
                    "minimum_regions": pipeline.definition["project_contract"].get("region_count", {}).get("minimum", 1),
                    "input": {"layout": "bids", "state": "raw", "sessions_per_subject": 1},
                    "seed_catalog": {
                        "catalog_version": self.seed_catalog.metadata.get("catalog_version"),
                        "conn_version": self.seed_catalog.metadata.get("conn_version"),
                        "seed_count": self.seed_catalog.metadata.get("seed_count"),
                        "collections": self.seed_catalog.metadata.get("collections"),
                        "search_tool": "list_available_seeds",
                    },
                    "graph": resolve_pipeline_graph(pipeline),
                    "investigator_parameter_decisions": guided_parameters,
                    "outputs": [
                        "subject_qc_images_and_metrics",
                        analysis.get("first_level_artifact"),
                        "versioned_second_level_results",
                        "reproducibility_package",
                    ],
                    "limitations": pipeline.definition.get("scope", {}).get("limitations", []),
                    "availability": availability,
                    "start_tool": "compose_pipeline",
                }
            )
        return _response(
            "get_product_capabilities",
            {
                "product": "CONN Pilot",
                "interaction_modes": {
                    "codex_mcp": "complete_workflow",
                    "signed_result_urls": "conversation_first_visual_review",
                },
                "capabilities": [
                    "literature_guided_parameter_selection",
                    "validated_conn_execution",
                    "modular_versioned_pipeline_graphs",
                    "seed_to_voxel_and_roi_to_roi",
                    "one_sample_or_two_independent_group_designs",
                    "continuous_covariates_and_investigator_defined_contrasts",
                    "subject_level_quality_review",
                    "versioned_sample_recalculation",
                    "scientific_acceptance",
                    "experiment_quality_and_hypothesis_report",
                    "reproducibility_export",
                ],
                "guided_flows": flows,
                "guided_flow_count": len(flows),
                "ready_for_execution": any(item["available"] for item in availability),
                "workflow": [
                    "get_product_capabilities",
                    "list_available_seeds",
                    "compose_pipeline",
                    "resolve_project_parameter",
                    "run_available_flow",
                    "get_job_status",
                    "get_subject_qc",
                    "get_experiment_quality_report",
                    "set_subject_qc_decision",
                    "request_second_level_recalculation_if_sample_changed",
                    "record_scientific_decision",
                    "generate_reproducibility_package",
                ],
            },
        )

    def start_available_flow(
        self,
        subject: str,
        flow_id: str,
        dataset_id: str,
        project_name: str,
        research_question: str,
        seed_ids: list[str],
        storage_available: bool,
        design_type: str = "one_sample",
        groups: dict[str, list[str]] | None = None,
        covariates: dict[str, dict[str, float]] | None = None,
        contrasts: list[dict[str, Any]] | None = None,
        hypothesis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_flow_id = GUIDED_FLOW_ID if flow_id in LEGACY_GUIDED_FLOW_IDS else flow_id
        if normalized_flow_id not in GUIDED_FLOWS:
            raise ValueError(f"Unknown guided flow: {flow_id}")
        pipeline_ref = GUIDED_FLOWS[normalized_flow_id]
        pipeline = self.catalog.resolve(*pipeline_ref)
        if not isinstance(project_name, str) or not project_name.strip():
            raise ValueError("project_name is required")
        if not isinstance(research_question, str) or not research_question.strip():
            raise ValueError("research_question is required")
        if not isinstance(seed_ids, list) or not seed_ids:
            raise ValueError("Select at least one seed_id from the published seed catalog")
        selected = [LEGACY_GUIDED_SEEDS.get(str(value), str(value)) for value in seed_ids]
        selected_seeds = self.seed_catalog.resolve(selected)
        minimum_regions = int(
            pipeline.definition["project_contract"].get("region_count", {}).get("minimum", 1)
        )
        if len(selected_seeds) < minimum_regions:
            raise ValueError(
                f"Flow {normalized_flow_id} requires at least {minimum_regions} regions"
            )
        dataset = self._dataset(dataset_id)
        health = self.store.get_system_health()
        worker = next(
            (item for item in health.get("workers", [])
             if str(item.get("id")) == str(dataset.get("worker_id"))),
            None,
        )
        unavailable = []
        if dataset.get("status") != "ready":
            unavailable.append("dataset_not_ready")
        if (dataset.get("metadata") or {}).get("layout") != "bids":
            unavailable.append("bids_layout_required")
        if not worker or not worker.get("online"):
            unavailable.append("assigned_worker_offline")
        if not storage_available:
            unavailable.append("artifact_storage_unavailable")
        if unavailable:
            raise ValueError("Flow is not currently available: " + ", ".join(unavailable))
        subjects = [
            str(item["id"])
            for item in (dataset.get("metadata") or {}).get("subjects", [])
            if isinstance(item, dict) and item.get("id")
        ]
        if not subjects:
            raise ValueError("The dataset has no registered subjects")
        design = _guided_design(
            subject_ids=subjects,
            design_type=design_type,
            groups=groups,
            covariates=covariates,
            contrasts=contrasts,
        )
        spec = _guided_flow_spec(
            project_name.strip(), research_question.strip(), design, selected_seeds,
            composition=composition_snapshot(pipeline),
            hypothesis=_guided_hypothesis(hypothesis, design),
        )
        project = self.store.create_project(
            subject, dataset_id, pipeline_ref[0], pipeline_ref[1], spec
        )
        unresolved = [
            item
            for item in self._parameter_resolution_status(subject, project, dataset, pipeline)
            if not item["resolved"]
        ]
        first = unresolved[0] if unresolved else None
        return _response(
            "start_available_flow",
            {
                "status": "needs_parameter_decisions" if unresolved else "ready_to_run",
                "flow_id": normalized_flow_id,
                "project": project,
                "unresolved_parameter_count": len(unresolved),
                "unresolved_parameter_paths": [item["parameter_path"] for item in unresolved],
                "next_action": (
                    {
                        "tool": "get_project_parameter_guidance",
                        "arguments": {
                            "project_id": project["id"],
                            "parameter_path": first["parameter_path"],
                        },
                        "requires_investigator_choice": True,
                    }
                    if first
                    else {"tool": "run_available_flow", "arguments": {"project_id": project["id"]}}
                ),
            },
        )

    def run_available_flow(self, subject: str, project_id: str) -> dict[str, Any]:
        project = self._project(project_id, subject)
        pipeline_ref = (project["pipeline_id"], project["pipeline_version"])
        flow_id = next(
            (key for key, value in GUIDED_FLOWS.items() if value == pipeline_ref), None
        )
        if not flow_id:
            raise ValueError("Project is not associated with a guided product flow")
        dataset = self._dataset(project["dataset_id"])
        pipeline = self.catalog.resolve(project["pipeline_id"], project["pipeline_version"])
        unresolved = [
            item
            for item in self._parameter_resolution_status(subject, project, dataset, pipeline)
            if not item["resolved"]
        ]
        if unresolved:
            first = unresolved[0]
            return _response(
                "run_available_flow",
                {
                    "status": "needs_parameter_decisions",
                    "project_id": project_id,
                    "unresolved_parameter_count": len(unresolved),
                    "unresolved_parameter_paths": [item["parameter_path"] for item in unresolved],
                    "next_action": {
                        "tool": "get_project_parameter_guidance",
                        "arguments": {
                            "project_id": project_id,
                            "parameter_path": first["parameter_path"],
                        },
                        "requires_investigator_choice": True,
                    },
                },
                warnings=["The flow was not queued because methodological decisions are incomplete."],
            )
        existing = self.store.get_reusable_job_for_project(project_id, subject)
        if existing:
            return _response(
                "run_available_flow",
                {
                    "status": existing["state"],
                    "flow_id": flow_id,
                    "project_id": project_id,
                    "job": existing,
                    "reused_existing_job": True,
                    "next_action": {
                        "tool": "get_job_status", "arguments": {"job_id": existing["id"]}
                    },
                },
            )
        validation = self.validate_project(subject, project_id)
        if not validation["ok"]:
            return _response(
                "run_available_flow",
                {"status": "blocked", "project_id": project_id, "next_action": "correct_project"},
                ok=False,
                errors=validation["errors"],
                warnings=validation["warnings"],
            )
        job = self.store.create_job(project)
        return _response(
            "run_available_flow",
            {
                "status": "queued",
                "flow_id": flow_id,
                "project_id": project_id,
                "job": job,
                "reused_existing_job": False,
                "next_action": {"tool": "get_job_status", "arguments": {"job_id": job["id"]}},
            },
        )

    def get_pipeline_builder_capabilities(self) -> dict[str, Any]:
        templates = []
        modules: dict[tuple[str, str], dict[str, Any]] = {}
        for flow_id, pipeline_ref in GUIDED_FLOWS.items():
            pipeline = self.catalog.resolve(*pipeline_ref)
            graph = resolve_pipeline_graph(pipeline)
            templates.append(
                {
                    "flow_id": flow_id,
                    "pipeline": graph["pipeline"],
                    "status": graph["status"],
                    "analysis": graph["analysis"],
                    "design_options": pipeline.definition["project_contract"].get("design_types", []),
                    "minimum_regions": pipeline.definition["project_contract"].get("region_count", {}).get("minimum", 1),
                    "graph": graph,
                }
            )
            for node in graph["nodes"]:
                key = (node["id"], node["version"])
                modules[key] = {
                    name: node[name]
                    for name in (
                        "id", "version", "kind", "category", "status",
                        "requires", "provides", "project_inputs",
                    )
                }
        return _response(
            "get_pipeline_builder_capabilities",
            {
                "composition_policy": "validated_templates_only",
                "free_matlab_allowed": False,
                "templates": templates,
                "template_count": len(templates),
                "modules": list(modules.values()),
                "module_count": len(modules),
            },
        )

    def get_project_pipeline_graph(
        self, subject: str, project_id: str
    ) -> dict[str, Any]:
        project = self._project(project_id, subject)
        dataset = self._dataset(project["dataset_id"])
        pipeline = self.catalog.resolve(project["pipeline_id"], project["pipeline_version"])
        definition = materialize_remote_project(project, dataset, use_placeholders=True)
        return _response(
            "get_project_pipeline_graph",
            {
                "project_id": project_id,
                "graph": resolve_pipeline_graph(pipeline),
                "execution_plan": build_node_execution_plan(definition, pipeline),
            },
        )

    def preview_pipeline_change(
        self, subject: str, project_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        project = self._project(project_id, subject)
        if not isinstance(changes, dict) or not changes:
            raise ValueError("changes must be a non-empty mapping")
        unknown = sorted(set(changes) - REMOTE_SPEC_FIELDS - REMOTE_SPEC_OPTIONAL_FIELDS)
        if unknown:
            raise ValueError("Unsupported change fields: " + ", ".join(unknown))
        dataset = self._dataset(project["dataset_id"])
        pipeline = self.catalog.resolve(project["pipeline_id"], project["pipeline_version"])
        current = materialize_remote_project(project, dataset, use_placeholders=True)
        candidate_project = {**project, "spec": _deep_merge(project["spec"], changes)}
        candidate = materialize_remote_project(candidate_project, dataset, use_placeholders=True)
        validation = validate_project_definition(candidate, pipeline, check_paths=False)
        impact = compare_node_plans(current, candidate, pipeline)
        return _response(
            "preview_pipeline_change",
            {
                "project_id": project_id,
                "valid": validation.valid,
                "impact": impact,
                "candidate_execution_plan": build_node_execution_plan(candidate, pipeline),
            },
            ok=validation.valid,
            errors=list(validation.errors),
            warnings=list(validation.warnings),
        )

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
        pipeline = self.catalog.resolve(pipeline_id, pipeline_version)
        if not isinstance(spec, dict):
            raise ValueError("spec must be an object")
        unknown = sorted(set(spec) - REMOTE_SPEC_FIELDS - REMOTE_SPEC_OPTIONAL_FIELDS)
        missing = sorted(REMOTE_SPEC_FIELDS - set(spec))
        if unknown:
            raise ValueError(f"Unknown project spec fields: {', '.join(unknown)}")
        if missing:
            raise ValueError(f"Missing project spec fields: {', '.join(missing)}")
        for path in pipeline.definition["project_contract"].get("parameters", {}):
            record = nested_get(spec, f"parameters.{path}")
            if isinstance(record, dict) and any(
                key in record
                for key in ("method_decision_id", "evidence_ids", "corpus_version")
            ):
                raise ValueError(
                    f"parameters.{path} decision provenance must be created by "
                    "resolve_project_parameter"
                )
        project = self.store.create_project(subject, dataset_id, pipeline_id, pipeline_version, spec)
        return _response("create_project", {"project": project})

    def validate_project(self, subject: str, project_id: str) -> dict[str, Any]:
        project = self._project(project_id, subject)
        dataset = self._dataset(project["dataset_id"])
        pipeline = self.catalog.resolve(project["pipeline_id"], project["pipeline_version"])
        definition = materialize_remote_project(project, dataset, use_placeholders=True)
        result = validate_project_definition(definition, pipeline, check_paths=False)
        errors = list(result.errors)
        if self.require_literature_decisions:
            unresolved = [
                item["parameter_path"]
                for item in self._parameter_resolution_status(
                    subject, project, dataset, pipeline
                )
                if not item["resolved"]
            ]
            if unresolved:
                errors.append(
                    "Unresolved literature-guided parameters: " + ", ".join(unresolved)
                )
        validation = {
            "valid": not errors,
            "errors": errors,
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
        decisions = self.store.list_method_decisions(project_id, subject)
        resolution_status = self._parameter_resolution_status(
            subject, project, dataset, pipeline, decisions=decisions
        )
        resolved_parameters = {
            item["parameter_path"]: item["current_record"]
            for item in (
                self.parameter_resolver.guidance(
                    self._resolver_project(project, dataset),
                    pipeline,
                    entry["parameter_path"],
                    limit=1,
                )
                for entry in resolution_status
                if entry["resolved"]
            )
        }
        data = {
            "project_id": project_id,
            "dataset_id": dataset["id"],
            "dataset_fingerprint": dataset["fingerprint"],
            "worker_id": dataset["worker_id"],
            "pipeline": {"id": pipeline.id, "version": pipeline.version},
            "stages": stages,
            "node_execution_plan": build_node_execution_plan(
                materialize_remote_project(project, dataset, use_placeholders=True), pipeline
            ),
            "resolved_parameters": resolved_parameters,
            "method_decisions": [
                {
                    key: decision.get(key)
                    for key in (
                        "id",
                        "parameter_path",
                        "component_id",
                        "parameter_name",
                        "selected_value",
                        "evidence_ids",
                        "rationale",
                        "corpus_version",
                        "created_at",
                    )
                }
                for decision in decisions
            ],
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

    def retry_job(self, subject: str, job_id: str) -> dict[str, Any]:
        self._job(job_id, subject)
        job = self.store.retry_job(job_id, subject)
        return _response("retry_job", {"job": job})

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
        review = self._review_state(subject, job)
        return _response(
            "get_qc_summary",
            {
                "job_id": job_id,
                "state": job["state"],
                "result_version": job.get("result_version"),
                "qc": summary.get("qc", {}),
                "review": review,
            },
        )

    def get_experiment_quality_report(self, subject: str, job_id: str) -> dict[str, Any]:
        job = self._job(job_id, subject)
        project = self._project(job["project_id"], subject)
        review = self._review_state(subject, job)
        return _response(
            "get_experiment_quality_report",
            {"report": build_experiment_quality_report(job=job, project=project, review=review)},
        )

    def get_subject_qc_evidence(
        self, subject: str, job_id: str, subject_id: str | None = None
    ) -> dict[str, Any]:
        job = self._job(job_id, subject)
        review = self._review_state(subject, job)
        records = review["subject_quality"]["subjects"]
        if subject_id is not None:
            records = [item for item in records if item["subject_id"] == subject_id]
            if not records:
                raise ValueError("Unknown subject for this result version")
        return _response(
            "get_subject_qc_evidence",
            {
                "job_id": job_id,
                "result_version": job.get("result_version"),
                "art_thresholds": (job.get("result_summary") or {}).get("qc", {}).get(
                    "art_thresholds", {}
                ),
                "subjects": records,
                "count": len(records),
            },
        )

    def set_subject_qc_decision(
        self,
        subject: str,
        job_id: str,
        result_version: str,
        subject_id: str,
        decision: str,
        justification: str | None = None,
    ) -> dict[str, Any]:
        if decision not in {"accept", "exclude", "needs_review"}:
            raise ValueError("decision must be accept, exclude, or needs_review")
        normalized = justification.strip() if isinstance(justification, str) else None
        if decision == "exclude" and not normalized:
            raise ValueError("A justification is required for every exclusion")
        job = self._job(job_id, subject)
        if job.get("result_version") != result_version:
            raise ValueError("The supplied result_version is not current")
        recorded = self.store.record_subject_qc_decision(
            job_id,
            subject,
            result_version,
            subject_id,
            decision,
            normalized,
        )
        current_job = self._job(job_id, subject)
        review = self._review_state(subject, current_job)
        return _response(
            "set_subject_qc_decision",
            {"decision": recorded, "review": review},
            warnings=(
                ["The effective sample changed; existing second-level results are blocked until recalculated."]
                if review["second_level"]["blocked"]
                else []
            ),
        )

    def record_scientific_decision(
        self,
        subject: str,
        job_id: str,
        result_version: str,
        sample_version: str,
        decision: str,
        rationale: str,
    ) -> dict[str, Any]:
        if decision not in {"accept", "reject", "needs_review"}:
            raise ValueError("decision must be accept, reject, or needs_review")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("rationale is required")
        job = self._job(job_id, subject)
        if job.get("result_version") != result_version:
            raise ValueError("The supplied result_version is not current")
        review = self._review_state(subject, job)
        if review["sample"]["version"] != sample_version:
            raise ValueError("The supplied sample_version is not current")
        if decision == "accept" and not review["scientific_acceptance"]["eligible"]:
            raise ValueError(
                "Scientific acceptance is blocked until technical completeness, subject QC, "
                "and a current second-level result are all satisfied"
            )
        recorded = self.store.record_analysis_decision(
            job_id,
            subject,
            result_version,
            sample_version,
            decision,
            rationale.strip(),
        )
        return _response(
            "record_scientific_decision",
            {"decision": recorded, "review": self._review_state(subject, job)},
        )

    def request_second_level_recalculation(
        self,
        subject: str,
        job_id: str,
        result_version: str,
        sample_version: str,
    ) -> dict[str, Any]:
        job = self._job(job_id, subject)
        if job.get("result_version") != result_version:
            raise ValueError("The supplied result_version is not current")
        review = self._review_state(subject, job)
        if review["sample"]["version"] != sample_version:
            raise ValueError("The supplied sample_version is not current")
        if not review["technical_completeness"]["passed"]:
            raise ValueError("Technical completeness must pass before second-level recalculation")
        unresolved = review["subject_quality"]["unresolved_subject_ids"]
        if unresolved:
            raise ValueError("Subject QC must be complete before second-level recalculation")
        included = review["sample"]["included_subject_ids"]
        if len(included) < 2:
            raise ValueError("At least two accepted subjects are required for this group analysis")
        project = self._project(job["project_id"], subject)
        design = (project.get("spec") or {}).get("design", {})
        if design.get("type") == "two_independent_groups":
            accepted = set(map(str, included))
            empty_groups = [
                str(name) for name, members in design.get("groups", {}).items()
                if not accepted.intersection(map(str, members))
            ]
            if empty_groups:
                raise ValueError(
                    "Accepted sample must retain subjects in every group; empty: "
                    + ", ".join(empty_groups)
                )
        run = self.store.create_second_level_run(
            job_id, subject, result_version, sample_version, included, review
        )
        return _response(
            "request_second_level_recalculation",
            {"second_level_run": run, "review": self._review_state(subject, job)},
        )

    def get_second_level_recalculation(
        self, subject: str, run_id: str
    ) -> dict[str, Any]:
        run = self.store.get_second_level_run(run_id, subject)
        if not run:
            raise ValueError("Unknown second-level recalculation")
        return _response(
            "get_second_level_recalculation",
            {"second_level_run": run, "terminal": run["state"] in {"succeeded", "failed", "cancelled"}},
            ok=run["state"] != "failed",
            errors=[run["error"]] if run.get("error") else [],
        )

    def generate_reproducibility_package(
        self, subject: str, job_id: str, result_version: str, sample_version: str,
        storage: ArtifactStorage,
    ) -> dict[str, Any]:
        job = self._job(job_id, subject)
        if job.get("result_version") != result_version:
            raise ValueError("The supplied result_version is not current")
        review = self._review_state(subject, job)
        if review["sample"]["version"] != sample_version:
            raise ValueError("The supplied sample_version is not current")
        if not review["subject_quality"]["complete"]:
            raise ValueError("Subject QC must be complete before packaging")
        if review["second_level"]["blocked"]:
            raise ValueError("A current second-level result is required before packaging")
        project = self._project(job["project_id"], subject)
        artifacts = self.store.list_artifacts(job_id, subject)
        decisions = self.store.list_method_decisions(project["id"], subject)
        attachments, attachment_warnings = self._package_attachments(
            artifacts, review, storage
        )
        content, manifest = build_reproducibility_package(
            job=job, project=project, review=review, artifacts=artifacts,
            method_decisions=decisions,
            quality_report=build_experiment_quality_report(
                job=job, project=project, review=review
            ),
            attachments=attachments,
        )
        manifest["attachment_warnings"] = attachment_warnings
        digest = hashlib.sha256(content).hexdigest()
        name = f"conn-pilot-{job_id[:8]}-{sample_version.removeprefix('sha256:')[:8]}.zip"
        object_key = storage.put_bytes(job_id, name, "application/zip", content)
        artifact = self.store.add_generated_artifact(
            job_id, subject, kind="reproducibility_package", name=name,
            object_key=object_key, bytes_count=len(content), sha256=digest,
            content_type="application/zip", metadata=manifest,
        )
        return _response(
            "generate_reproducibility_package",
            {"artifact": artifact, "manifest": manifest,
             "download_url": storage.download_url(object_key), "expires_in": 3600},
            warnings=attachment_warnings,
        )

    @staticmethod
    def _package_attachments(
        artifacts: list[dict[str, Any]], review: dict[str, Any], storage: ArtifactStorage,
        *, max_total_bytes: int = 64 * 1024 * 1024,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        active = review["second_level"].get("active_recalculation") or {}
        active_run_id = active.get("id")
        selected: list[dict[str, Any]] = []
        for artifact in artifacts:
            kind = artifact.get("kind")
            if kind == "qc_images":
                selected.append(artifact)
            elif active_run_id and kind == "second_level_version":
                if artifact.get("second_level_run_id") == active_run_id:
                    selected.append(artifact)
            elif not active_run_id and kind == "second_level_maps":
                selected.append(artifact)
        selected.sort(key=lambda item: (
            0 if item.get("kind") == "qc_images" else 1,
            str(item.get("subject_id") or ""), str(item.get("name") or ""),
        ))
        attachments: list[dict[str, Any]] = []
        warnings: list[str] = []
        remaining = max_total_bytes
        for artifact in selected:
            size = int(artifact.get("bytes") or 0)
            if size and size > remaining:
                warnings.append(f"Skipped {artifact.get('name')}: package size limit reached")
                continue
            try:
                content = storage.get_bytes(str(artifact["object_key"]), max_bytes=remaining)
            except Exception:
                warnings.append(f"Could not embed {artifact.get('name')}: artifact could not be read")
                continue
            folder = "qc"
            if artifact.get("kind") != "qc_images":
                folder = "second-level"
            elif artifact.get("subject_id"):
                folder += "/" + _safe_package_name(str(artifact["subject_id"]))
            name = _safe_package_name(str(artifact.get("name") or "artifact"))
            unique = str(artifact.get("id") or hashlib.sha256(content).hexdigest())[:12]
            attachments.append({"path": f"{folder}/{unique}-{name}", "content": content})
            remaining -= len(content)
        return attachments, warnings

    def _review_state(self, subject: str, job: dict[str, Any]) -> dict[str, Any]:
        result_version = job.get("result_version")
        summary = job.get("result_summary") or {}
        qc = summary.get("qc", {})
        qc_subjects = qc.get("subjects", [])
        if isinstance(qc_subjects, dict):
            qc_subjects = [qc_subjects]
        artifacts = self.store.list_artifacts(job["id"], subject)
        qc_images: dict[str, list[dict[str, Any]]] = {}
        for artifact in artifacts:
            artifact_subject = artifact.get("subject_id")
            if artifact.get("kind") == "qc_images" and artifact_subject:
                qc_images.setdefault(str(artifact_subject), []).append(artifact)
        decisions = (
            self.store.list_subject_qc_decisions(job["id"], subject, result_version)
            if result_version
            else []
        )
        current: dict[str, dict[str, Any]] = {}
        for item in decisions:
            current[str(item["subject_id"])] = item
        subjects: list[dict[str, Any]] = []
        for item in qc_subjects:
            if not isinstance(item, dict) or not item.get("subject_id"):
                continue
            subject_id = str(item["subject_id"])
            subjects.append(
                {
                    "subject_id": subject_id,
                    "metrics": item.get("metrics", {}),
                    "artifact_counts": {
                        "qc_images": item.get("qc_images", 0),
                        "preprocessing_qc": item.get("preprocessing_qc", 0),
                    },
                    "art_images": qc_images.get(subject_id, []),
                    "decision": current.get(subject_id),
                }
            )
        original_ids = sorted(item["subject_id"] for item in subjects)
        excluded_ids = sorted(
            item["subject_id"]
            for item in subjects
            if item.get("decision") and item["decision"].get("decision") == "exclude"
        )
        included_ids = [value for value in original_ids if value not in set(excluded_ids)]
        sample_version = "sha256:" + hashlib.sha256(
            json.dumps(included_ids, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        unresolved_ids = [
            item["subject_id"]
            for item in subjects
            if not item.get("decision") or item["decision"].get("decision") == "needs_review"
        ]
        second_level_available = any(
            item.get("kind") == "second_level_maps" and not item.get("second_level_run_id")
            for item in artifacts
        )
        sample_changed = included_ids != original_ids
        recalculations = (
            self.store.list_second_level_runs(job["id"], subject, result_version)
            if result_version else []
        )
        active_recalculation = next(
            (item for item in reversed(recalculations)
             if item.get("sample_version") == sample_version and item.get("state") == "succeeded"),
            None,
        )
        pending_recalculation = next(
            (item for item in reversed(recalculations)
             if item.get("sample_version") == sample_version
             and item.get("state") in {"queued", "running"}),
            None,
        )
        second_level_current = bool(active_recalculation) or (second_level_available and not sample_changed)
        technical = qc.get("technical_completeness", {})
        technical_passed = bool(technical.get("passed"))
        eligible = bool(
            technical_passed
            and subjects
            and not unresolved_ids
            and second_level_current
            and included_ids
        )
        analysis_decisions = (
            self.store.list_analysis_decisions(job["id"], subject, result_version)
            if result_version
            else []
        )
        latest_subject_decision_at = max(
            (str(item.get("decided_at", "")) for item in current.values()),
            default="",
        )
        current_analysis = next(
            (
                item
                for item in reversed(analysis_decisions)
                if item.get("sample_version") == sample_version
                and str(item.get("decided_at", "")) >= latest_subject_decision_at
            ),
            None,
        )
        return {
            "technical_completeness": {
                "passed": technical_passed,
                "details": technical,
            },
            "subject_quality": {
                "complete": bool(subjects) and not unresolved_ids,
                "subjects": subjects,
                "unresolved_subject_ids": unresolved_ids,
            },
            "sample": {
                "version": sample_version,
                "original_subject_ids": original_ids,
                "included_subject_ids": included_ids,
                "excluded_subject_ids": excluded_ids,
                "changed_from_computed_second_level": sample_changed,
            },
            "second_level": {
                "status": (
                    "current" if second_level_current else
                    "recalculating" if pending_recalculation else
                    "stale" if sample_changed else "unavailable"
                ),
                "blocked": not second_level_current,
                "recalculation_required": sample_changed,
                "active_recalculation": active_recalculation,
                "pending_recalculation": pending_recalculation,
                "versions": recalculations,
                "reason": (
                    "The effective sample differs from the sample used to compute the second level."
                    if sample_changed
                    else None
                ),
            },
            "scientific_acceptance": {
                "eligible": eligible,
                "current_decision": current_analysis,
                "status": current_analysis.get("decision") if current_analysis else "needs_review",
            },
        }

    def list_guidance_topics(self) -> dict[str, Any]:
        return self.literature.list_guidance_topics()

    def get_parameter_guidance(
        self,
        component_id: str,
        parameter_name: str | None = None,
        *,
        context: dict[str, Any] | None = None,
        include_inferred: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        return self.literature.get_parameter_guidance(
            component_id,
            parameter_name,
            context=context,
            include_inferred=include_inferred,
            limit=limit,
        )

    def compare_method_options(
        self,
        component_id: str,
        parameter_name: str,
        *,
        context: dict[str, Any] | None = None,
        include_inferred: bool = False,
    ) -> dict[str, Any]:
        return self.literature.compare_method_options(
            component_id,
            parameter_name,
            context=context,
            include_inferred=include_inferred,
        )

    def get_evidence_record(self, pmid: str) -> dict[str, Any]:
        return self.literature.get_evidence_record(pmid)

    def validate_parameter_choice(
        self,
        component_id: str,
        parameter_name: str,
        selected_value: Any,
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        return self.literature.validate_parameter_choice(
            component_id,
            parameter_name,
            selected_value,
            evidence_ids,
        )

    def record_method_decision(
        self,
        subject: str,
        project_id: str,
        component_id: str,
        parameter_name: str,
        selected_value: Any,
        evidence_ids: list[str],
        rationale: str,
    ) -> dict[str, Any]:
        self._project(project_id, subject)
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("rationale is required")
        validation = self.literature.validate_parameter_choice(
            component_id,
            parameter_name,
            selected_value,
            evidence_ids,
        )
        decision = self.store.record_method_decision(
            subject,
            project_id,
            component_id,
            parameter_name,
            selected_value,
            evidence_ids,
            rationale.strip(),
            validation["corpus_version"],
            validation["data"]["evidence_snapshot"],
        )
        return _response(
            "record_method_decision",
            {
                "decision": decision,
                "evidence_alignment": validation["data"]["evidence_alignment"],
                "scientific_validity_determined": False,
            },
            warnings=validation["warnings"],
        )

    def list_method_decisions(self, subject: str, project_id: str) -> dict[str, Any]:
        self._project(project_id, subject)
        decisions = self.store.list_method_decisions(project_id, subject)
        return _response(
            "list_method_decisions",
            {"project_id": project_id, "decisions": decisions, "count": len(decisions)},
        )

    def list_unresolved_project_parameters(
        self, subject: str, project_id: str
    ) -> dict[str, Any]:
        project = self._project(project_id, subject)
        dataset = self._dataset(project["dataset_id"])
        pipeline = self.catalog.resolve(project["pipeline_id"], project["pipeline_version"])
        parameters = self._parameter_resolution_status(
            subject, project, dataset, pipeline
        )
        unresolved = [item for item in parameters if not item["resolved"]]
        return _response(
            "list_unresolved_project_parameters",
            {
                "project_id": project_id,
                "parameters": parameters,
                "required_count": len(parameters),
                "unresolved_count": len(unresolved),
                "ready": not unresolved,
            },
        )

    def get_project_parameter_guidance(
        self,
        subject: str,
        project_id: str,
        parameter_path: str,
        *,
        limit: int = 50,
    ) -> dict[str, Any]:
        project = self._project(project_id, subject)
        dataset = self._dataset(project["dataset_id"])
        pipeline = self.catalog.resolve(project["pipeline_id"], project["pipeline_version"])
        guidance = self.parameter_resolver.guidance(
            self._resolver_project(project, dataset), pipeline, parameter_path, limit=limit
        )
        return _response("get_project_parameter_guidance", guidance)

    def resolve_project_parameter(
        self,
        subject: str,
        project_id: str,
        parameter_path: str,
        selected_value: Any,
        evidence_ids: list[str],
        rationale: str,
    ) -> dict[str, Any]:
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("rationale is required")
        project = self._project(project_id, subject)
        dataset = self._dataset(project["dataset_id"])
        pipeline = self.catalog.resolve(project["pipeline_id"], project["pipeline_version"])
        validation = self.parameter_resolver.validate_choice(
            self._resolver_project(project, dataset),
            pipeline,
            parameter_path,
            selected_value,
            evidence_ids,
        )
        parameter_record = {
            "value": validation["selected_value"],
            "source": f"literature_guidance:{validation['corpus_version']}",
            "rationale": rationale.strip(),
            "confirmed_by_investigator": True,
            "evidence_ids": validation["exact_evidence_ids"],
            "corpus_version": validation["corpus_version"],
        }
        result = self.store.resolve_project_parameter(
            subject,
            project_id,
            parameter_path,
            parameter_record,
            "|".join(validation["literature_component_ids"]),
            "|".join(validation["literature_parameter_names"]),
            validation["selected_value"],
            validation["exact_evidence_ids"],
            rationale.strip(),
            validation["corpus_version"],
            validation["evidence_snapshot"],
        )
        updated = self._project(project_id, subject)
        remaining = [
            item
            for item in self._parameter_resolution_status(
                subject, updated, dataset, pipeline
            )
            if not item["resolved"]
        ]
        return _response(
            "resolve_project_parameter",
            {
                **result,
                "evidence_alignment": "exact_explicit_observation",
                "remaining_unresolved_count": len(remaining),
                "remaining_parameter_paths": [item["parameter_path"] for item in remaining],
                "scientific_validity_determined": False,
            },
            warnings=[
                "This confirms the investigator's documented choice; it does not establish scientific validity."
            ],
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

    def _parameter_resolution_status(
        self,
        subject: str,
        project: dict[str, Any],
        dataset: dict[str, Any],
        pipeline: Any,
        *,
        decisions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        statuses = self.parameter_resolver.unresolved_paths(
            self._resolver_project(project, dataset), pipeline
        )
        by_id = {
            str(decision["id"]): decision
            for decision in (
                decisions
                if decisions is not None
                else self.store.list_method_decisions(project["id"], subject)
            )
        }
        for status in statuses:
            if not status["resolved"]:
                status["resolution_integrity"] = "incomplete_parameter_record"
                continue
            record = nested_get(
                project["spec"], f"parameters.{status['parameter_path']}"
            )
            decision = by_id.get(str(record["method_decision_id"]))
            matches = bool(
                decision
                and decision.get("parameter_path") == status["parameter_path"]
                and decision.get("selected_value") == record.get("value")
                and decision.get("evidence_ids") == record.get("evidence_ids")
                and decision.get("corpus_version") == record.get("corpus_version")
            )
            status["resolved"] = matches
            status["resolution_integrity"] = (
                "verified" if matches else "missing_or_mismatched_decision"
            )
        return statuses

    @staticmethod
    def _resolver_project(project: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
        return {**project, "dataset_metadata": dataset.get("metadata", {})}


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
    value = {
        "schema_version": "conn_pilot_project_v2" if spec.get("composition") else "conn_pilot_project_v1",
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
    if spec.get("composition") is not None:
        value["composition"] = spec["composition"]
    if spec.get("hypothesis") is not None:
        value["hypothesis"] = spec["hypothesis"]
    return value


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
        auth0_issuer=os.environ.get("CONN_PILOT_AUTH0_ISSUER", ""),
        auth0_audience=os.environ.get("CONN_PILOT_AUTH0_AUDIENCE", ""),
    )
    if len(values.admin_token) < 32 or len(values.worker_token) < 32:
        raise ValueError("Admin and worker tokens must contain at least 32 characters")
    parsed = urlsplit(values.public_base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        raise ValueError("CONN_PILOT_PUBLIC_BASE_URL must be an HTTP(S) origin without a path")
    if bool(values.auth0_issuer) != bool(values.auth0_audience):
        raise ValueError("CONN_PILOT_AUTH0_ISSUER and CONN_PILOT_AUTH0_AUDIENCE must be configured together")
    if values.auth0_issuer:
        auth0 = urlsplit(values.auth0_issuer)
        if auth0.scheme != "https" or not auth0.netloc or auth0.path not in {"", "/"}:
            raise ValueError("CONN_PILOT_AUTH0_ISSUER must be an HTTPS origin")
        if values.auth0_audience.rstrip("/") != values.mcp_url.rstrip("/"):
            raise ValueError("CONN_PILOT_AUTH0_AUDIENCE must match the public MCP URL")
    return values


def build_control_plane_server(
    settings: ControlSettings,
    store: Store,
    *,
    artifact_storage: ArtifactStorage | None = None,
    require_mcp_auth: bool = True,
) -> MCPServer:
    storage = artifact_storage or ArtifactStorage()
    catalog_root = Path(os.environ.get("CONN_PILOT_CATALOG", REPO_ROOT / "catalog"))
    literature_root = Path(
        os.environ.get(
            "CONN_PILOT_LITERATURE_ROOT",
            Path.cwd() / "knowledge" / "pipeline_review",
        )
    )
    service = ControlPlaneService(
        store,
        catalog_root,
        literature_root,
        require_literature_decisions=True,
    )
    parsed = urlsplit(settings.public_base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    verifier = (
        HybridTokenVerifier(
            store,
            settings.mcp_url,
            auth0_issuer=settings.auth0_issuer,
            auth0_audience=settings.auth0_audience,
        )
        if require_mcp_auth
        else None
    )
    issuer_url = settings.auth0_issuer or f"{origin}/"
    auth = (
        AuthSettings(
            issuer_url=AnyHttpUrl(issuer_url),
            resource_server_url=AnyHttpUrl(settings.mcp_url),
            required_scopes=["conn-pilot:use"],
            validate_token_resource=True,
        )
        if require_mcp_auth
        else None
    )
    server = MCPServer(
        "CONN Pilot",
        version=__version__,
        instructions=(
            "When a researcher asks what the product can do or wants to run an available analysis, call "
            "get_product_capabilities first, then use start_available_flow and run_available_flow. "
            "Use dataset_id, project_id and job_id; never invent server paths. Submit long CONN analyses "
            "as jobs and poll get_job_status. Scientific QC decisions always require investigator review. "
            "For methodological questions, retrieve literature evidence, distinguish explicit from inferred "
            "observations, present alternatives with citations, and never turn frequency into an automatic default. "
            "Before submission, resolve every required project parameter through the project-specific guidance tools."
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
    def get_product_capabilities() -> dict[str, Any]:
        """Show what CONN Pilot can do and which guided flows are executable on available datasets."""
        return service.get_product_capabilities(storage.available)

    @server.tool(annotations=read_only)
    def list_available_seeds(
        query: str | None = None,
        collection: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search built-in CONN atlas, network, and Schaefer seed regions by name."""
        return service.list_available_seeds(query, collection, limit, offset)

    @server.tool(annotations=read_only)
    def get_pipeline_builder_capabilities() -> dict[str, Any]:
        """List validated modular templates, reusable nodes, and their compatibility contracts."""
        return service.get_pipeline_builder_capabilities()

    @server.tool(annotations=read_only)
    def get_project_pipeline_graph(project_id: str) -> dict[str, Any]:
        """Show the resolved node graph and immutable execution plan for an owned project."""
        return service.get_project_pipeline_graph(subject(), project_id)

    @server.tool(annotations=read_only)
    def preview_pipeline_change(project_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Validate proposed scientific changes and show reusable versus invalidated nodes without saving."""
        return service.preview_pipeline_change(subject(), project_id, changes)

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    def start_available_flow(
        flow_id: str,
        dataset_id: str,
        project_name: str,
        research_question: str,
        seed_ids: list[str],
        design_type: str = "one_sample",
        groups: dict[str, list[str]] | None = None,
        covariates: dict[str, dict[str, float]] | None = None,
        contrasts: list[dict[str, Any]] | None = None,
        hypothesis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a guided draft with chosen seeds, groups, covariates, and confirmed contrasts."""
        return service.start_available_flow(
            subject(), flow_id, dataset_id, project_name, research_question, seed_ids,
            storage.available, design_type, groups, covariates, contrasts, hypothesis,
        )

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    def compose_pipeline(
        flow_id: str,
        dataset_id: str,
        project_name: str,
        research_question: str,
        seed_ids: list[str],
        design_type: str = "one_sample",
        groups: dict[str, list[str]] | None = None,
        covariates: dict[str, dict[str, float]] | None = None,
        contrasts: list[dict[str, Any]] | None = None,
        hypothesis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compose an owned project from a validated modular template and scientific choices."""
        response = service.start_available_flow(
            subject(), flow_id, dataset_id, project_name, research_question, seed_ids,
            storage.available, design_type, groups, covariates, contrasts, hypothesis,
        )
        response["operation"] = "compose_pipeline"
        return response

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    def run_available_flow(project_id: str) -> dict[str, Any]:
        """Queue a guided flow, or return the exact unresolved investigator decision that blocks it."""
        return service.run_available_flow(subject(), project_id)

    @server.tool(annotations=read_only)
    def list_pipelines() -> dict[str, Any]:
        """List validated CONN pipelines available to remote projects."""
        return service.list_pipelines()

    @server.tool(annotations=read_only)
    def list_datasets() -> dict[str, Any]:
        """List sanitized metadata for datasets registered by an online local worker."""
        return service.list_datasets()

    @server.tool(annotations=read_only)
    def get_system_health() -> dict[str, Any]:
        """Show worker availability, storage readiness and execution queue counts."""
        return service.get_system_health(storage.available)

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

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False))
    def retry_job(job_id: str) -> dict[str, Any]:
        """Queue an owned failed job again after a recoverable worker or connectivity interruption."""
        return service.retry_job(subject(), job_id)

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
        """Read separate technical, subject-quality, sample, second-level and scientific-review states."""
        return service.get_qc_summary(subject(), job_id)

    @server.tool(annotations=read_only)
    def get_experiment_quality_report(job_id: str) -> dict[str, Any]:
        """Report whether quality permits inference and whether evidence supports the hypothesis."""
        return service.get_experiment_quality_report(subject(), job_id)

    @server.tool(annotations=read_only)
    def get_subject_qc(job_id: str, subject_id: str | None = None) -> dict[str, Any]:
        """Show ART metrics, current QC decisions and temporary image URLs per subject."""
        response = service.get_subject_qc_evidence(subject(), job_id, subject_id)
        for record in response["data"]["subjects"]:
            for artifact in record["art_images"]:
                artifact["download_url"] = storage.download_url(artifact["object_key"])
                artifact["expires_in"] = 3600
        return response

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    def set_subject_qc_decision(
        job_id: str,
        result_version: str,
        subject_id: str,
        decision: str,
        justification: str | None = None,
    ) -> dict[str, Any]:
        """Record accept, exclude, or needs_review for one subject; exclusions require justification."""
        return service.set_subject_qc_decision(
            subject(),
            job_id,
            result_version,
            subject_id,
            decision,
            justification,
        )

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    def record_scientific_decision(
        job_id: str,
        result_version: str,
        sample_version: str,
        decision: str,
        rationale: str,
    ) -> dict[str, Any]:
        """Record scientific acceptance separately; acceptance is blocked by incomplete QC or stale second level."""
        return service.record_scientific_decision(
            subject(),
            job_id,
            result_version,
            sample_version,
            decision,
            rationale,
        )

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    def request_second_level_recalculation(
        job_id: str,
        result_version: str,
        sample_version: str,
    ) -> dict[str, Any]:
        """Queue a versioned group analysis for the currently accepted one-sample cohort."""
        return service.request_second_level_recalculation(
            subject(), job_id, result_version, sample_version
        )

    @server.tool(annotations=read_only)
    def get_second_level_recalculation(run_id: str) -> dict[str, Any]:
        """Read state, version and output summary for a queued group recalculation."""
        return service.get_second_level_recalculation(subject(), run_id)

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    def generate_reproducibility_package(
        job_id: str, result_version: str, sample_version: str
    ) -> dict[str, Any]:
        """Create a downloadable ZIP with report, methods, parameters, QC decisions and provenance."""
        return service.generate_reproducibility_package(
            subject(), job_id, result_version, sample_version, storage
        )

    @server.tool(annotations=read_only)
    def list_guidance_topics() -> dict[str, Any]:
        """List literature-reviewed pipeline components and parameters available for client-side guidance."""
        return service.list_guidance_topics()

    @server.tool(annotations=read_only)
    def get_parameter_guidance(
        component_id: str,
        parameter_name: str | None = None,
        context: dict[str, Any] | None = None,
        include_inferred: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Retrieve cited parameter observations; compare applicability and never present frequency as a recommendation."""
        return service.get_parameter_guidance(
            component_id,
            parameter_name,
            context=context,
            include_inferred=include_inferred,
            limit=limit,
        )

    @server.tool(annotations=read_only)
    def compare_method_options(
        component_id: str,
        parameter_name: str,
        context: dict[str, Any] | None = None,
        include_inferred: bool = False,
    ) -> dict[str, Any]:
        """Group reported parameter values into cited options without selecting an automatic scientific default."""
        return service.compare_method_options(
            component_id,
            parameter_name,
            context=context,
            include_inferred=include_inferred,
        )

    @server.tool(annotations=read_only)
    def get_evidence_record(pmid: str) -> dict[str, Any]:
        """Read one structurally reviewed paper record, including methods, unresolved issues and parameter evidence."""
        return service.get_evidence_record(pmid)

    @server.tool(annotations=read_only)
    def validate_parameter_choice(
        component_id: str,
        parameter_name: str,
        selected_value: Any,
        evidence_ids: list[str],
    ) -> dict[str, Any]:
        """Check that cited evidence belongs to a parameter and whether the selected value was explicitly reported."""
        return service.validate_parameter_choice(
            component_id,
            parameter_name,
            selected_value,
            evidence_ids,
        )

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    def record_method_decision(
        project_id: str,
        component_id: str,
        parameter_name: str,
        selected_value: Any,
        evidence_ids: list[str],
        rationale: str,
    ) -> dict[str, Any]:
        """Persist an investigator-confirmed method decision with its exact evidence snapshot and rationale."""
        return service.record_method_decision(
            subject(),
            project_id,
            component_id,
            parameter_name,
            selected_value,
            evidence_ids,
            rationale,
        )

    @server.tool(annotations=read_only)
    def list_method_decisions(project_id: str) -> dict[str, Any]:
        """List the versioned methodological decisions recorded for one owned project."""
        return service.list_method_decisions(subject(), project_id)

    @server.tool(annotations=read_only)
    def list_unresolved_project_parameters(project_id: str) -> dict[str, Any]:
        """List the literature-guided executable parameters that still require investigator confirmation."""
        return service.list_unresolved_project_parameters(subject(), project_id)

    @server.tool(annotations=read_only)
    def get_project_parameter_guidance(
        project_id: str, parameter_path: str, limit: int = 50
    ) -> dict[str, Any]:
        """Return executable, dataset-compatible options and exact evidence for one project parameter."""
        return service.get_project_parameter_guidance(
            subject(), project_id, parameter_path, limit=limit
        )

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        )
    )
    def resolve_project_parameter(
        project_id: str,
        parameter_path: str,
        selected_value: Any,
        evidence_ids: list[str],
        rationale: str,
    ) -> dict[str, Any]:
        """Confirm a cited executable value and atomically bind its decision record to the project."""
        return service.resolve_project_parameter(
            subject(),
            project_id,
            parameter_path,
            selected_value,
            evidence_ids,
            rationale,
        )

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

    @server.custom_route("/worker/v1/second-level/claim", methods=["POST"])
    async def second_level_claim(request: Request) -> JSONResponse:
        body, error = await worker_json(request)
        if error:
            return error
        assert body is not None
        run = store.claim_second_level_run(
            str(body.get("worker_id", "")),
            [str(value) for value in body.get("dataset_ids", [])],
            settings.lease_seconds,
        )
        return JSONResponse({"ok": True, "second_level_run": run})

    @server.custom_route("/worker/v1/second-level/{run_id:str}/heartbeat", methods=["POST"])
    async def second_level_heartbeat(request: Request) -> JSONResponse:
        body, error = await worker_json(request)
        if error:
            return error
        assert body is not None
        updated = store.heartbeat_second_level_run(
            request.path_params["run_id"], str(body.get("worker_id", "")),
            str(body.get("phase", "running")), settings.lease_seconds,
        )
        return JSONResponse({"ok": updated}, status_code=200 if updated else 409)

    @server.custom_route("/worker/v1/second-level/{run_id:str}/complete", methods=["POST"])
    async def second_level_complete(request: Request) -> JSONResponse:
        body, error = await worker_json(request)
        if error:
            return error
        assert body is not None
        updated = store.complete_second_level_run(
            request.path_params["run_id"], str(body.get("worker_id", "")),
            str(body.get("state", "")), body.get("summary", {}), body.get("error"),
        )
        return JSONResponse({"ok": updated}, status_code=200 if updated else 409)

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
                subject_id=(str(body["subject_id"]) if body.get("subject_id") else None),
                metadata=body.get("metadata", {}),
                second_level_run_id=(
                    str(body["second_level_run_id"]) if body.get("second_level_run_id") else None
                ),
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


def _safe_package_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(value).name).strip("._") or "artifact"


def _deep_merge(original: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(original))
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _guided_flow_spec(
    project_name: str,
    research_question: str,
    design: dict[str, Any],
    seeds: list[dict[str, Any]],
    composition: dict[str, Any] | None = None,
    hypothesis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def fixed(value: Any, rationale: str, *, confirmed: bool = True) -> dict[str, Any]:
        return {
            "value": value,
            "source": "validated_guided_flow_scope",
            "rationale": rationale,
            "confirmed_by_investigator": confirmed,
        }

    def unresolved(rationale: str) -> dict[str, Any]:
        return {
            "value": None,
            "source": "awaiting_literature_guided_investigator_choice",
            "rationale": rationale,
            "confirmed_by_investigator": False,
        }

    value = {
        "project": {"name": project_name, "research_question": research_question},
        "design": design,
        "seeds": [
            {
                "name": seed["id"],
                "conn_source": seed["conn_source"],
                "rationale": "Seed selected by the investigator from the published flow capabilities.",
                "confirmed_by_investigator": True,
            }
            for seed in seeds
        ],
        "parameters": {
            "preprocessing": {
                "pipeline": fixed(
                    "default_mni", "Only preprocessing pipeline implemented by this guided flow."
                ),
                "smoothing_fwhm_mm": unresolved(
                    "Select a smoothing scale after reviewing the available evidence."
                ),
                "outlier_fd_threshold_mm": unresolved(
                    "Select the ART motion threshold after reviewing the available evidence."
                ),
                "global_signal_z_threshold": unresolved(
                    "Select the ART global-signal threshold after reviewing the available evidence."
                ),
            },
            "denoising": {
                "method": fixed(
                    "aCompCor", "Only denoising method implemented by this guided flow."
                ),
                "wm_components": unresolved(
                    "Select the white-matter component count after reviewing the available evidence."
                ),
                "csf_components": unresolved(
                    "Select the CSF component count after reviewing the available evidence."
                ),
                "bandpass_filter_hz": unresolved(
                    "Select the temporal filter after reviewing the available evidence."
                ),
                "detrending_order": fixed(1, "Linear detrending in the validated guided flow."),
                "despiking": fixed(0, "Despiking disabled in the validated guided flow."),
                "global_signal_regression": unresolved(
                    "Confirm the supported no-GSR choice after reviewing the available evidence."
                ),
            },
        },
    }
    if composition is not None:
        value["composition"] = composition
    if hypothesis is not None:
        value["hypothesis"] = hypothesis
    return value


def _guided_hypothesis(
    value: dict[str, Any] | None, design: dict[str, Any]
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("hypothesis must be an object")
    normalized = {
        "statement": value.get("statement"),
        "target_contrast": value.get("target_contrast"),
        "expected_direction": value.get("expected_direction"),
        "decision_rule": value.get("decision_rule"),
    }
    if value.get("sample_adequacy") is not None:
        normalized["sample_adequacy"] = value["sample_adequacy"]
    errors: list[str] = []
    _validate_hypothesis_for_guided_flow(normalized, design, errors)
    if errors:
        raise ValueError("; ".join(errors))
    return normalized


def _validate_hypothesis_for_guided_flow(
    value: dict[str, Any], design: dict[str, Any], errors: list[str]
) -> None:
    for field in ("statement", "target_contrast", "expected_direction", "decision_rule"):
        if not value.get(field):
            errors.append(f"hypothesis.{field} is required")
    if value.get("expected_direction") not in {"positive", "negative", "nonzero"}:
        errors.append("hypothesis.expected_direction must be positive, negative, or nonzero")
    contrast_names = {
        str(item.get("name"))
        for item in design.get("contrasts", [])
        if isinstance(item, dict) and item.get("name")
    }
    if value.get("target_contrast") and str(value["target_contrast"]) not in contrast_names:
        errors.append("hypothesis.target_contrast must name a design contrast")
    rule = value.get("decision_rule")
    if not isinstance(rule, dict):
        errors.append("hypothesis.decision_rule must be an object")
    else:
        alpha = rule.get("alpha")
        if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not 0 < float(alpha) <= 1:
            errors.append("hypothesis.decision_rule.alpha must be greater than 0 and at most 1")
        if not rule.get("multiplicity_method"):
            errors.append("hypothesis.decision_rule.multiplicity_method is required")
    adequacy = value.get("sample_adequacy")
    if adequacy is not None and (
        not isinstance(adequacy, dict) or not adequacy.get("basis")
    ):
        errors.append("hypothesis.sample_adequacy must document a basis")


def _guided_design(
    *,
    subject_ids: list[str],
    design_type: str,
    groups: dict[str, list[str]] | None,
    covariates: dict[str, dict[str, float]] | None,
    contrasts: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if design_type not in {"one_sample", "two_independent_groups"}:
        raise ValueError("design_type must be one_sample or two_independent_groups")
    normalized_groups = groups or ({"sample": list(subject_ids)} if design_type == "one_sample" else {})
    expected_group_count = 1 if design_type == "one_sample" else 2
    if not isinstance(normalized_groups, dict) or len(normalized_groups) != expected_group_count:
        raise ValueError(f"{design_type} requires exactly {expected_group_count} group(s)")
    subject_set = set(subject_ids)
    assigned: list[str] = []
    for name, members in normalized_groups.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(members, list) or not members:
            raise ValueError("Each group must have a non-empty name and at least one subject")
        assigned.extend(map(str, members))
    if len(assigned) != len(set(assigned)):
        raise ValueError("A subject cannot belong to more than one group")
    if set(assigned) != subject_set:
        missing = sorted(subject_set - set(assigned))
        unknown = sorted(set(assigned) - subject_set)
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unknown:
            details.append("unknown: " + ", ".join(unknown))
        raise ValueError("Groups must assign every dataset subject exactly once (" + "; ".join(details) + ")")

    normalized_covariates = covariates or {}
    if not isinstance(normalized_covariates, dict):
        raise ValueError("covariates must map names to subject-value mappings")
    for name, values in normalized_covariates.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(values, dict):
            raise ValueError("Each covariate must have a name and a subject-value mapping")
        if set(map(str, values)) != subject_set:
            raise ValueError(f"Covariate {name} must define every dataset subject exactly once")
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            for value in values.values()
        ):
            raise ValueError(f"Covariate {name} must contain only finite numbers")

    if contrasts is None:
        if design_type != "one_sample" or normalized_covariates:
            raise ValueError(
                "contrasts are required when using groups or covariates; the system will not infer the scientific hypothesis"
            )
        normalized_contrasts = [
            {
                "name": "sample_mean",
                "effects": ["AllSubjects"],
                "weights": [1],
                "rationale": "Estimate the one-sample mean selected through the guided flow.",
                "confirmed_by_investigator": True,
            }
        ]
    elif not isinstance(contrasts, list) or not contrasts:
        raise ValueError("contrasts must contain at least one investigator-defined contrast")
    else:
        effects = {"AllSubjects", *normalized_groups, *normalized_covariates}
        normalized_contrasts = []
        for index, contrast in enumerate(contrasts):
            if not isinstance(contrast, dict):
                raise ValueError(f"contrasts[{index}] must be a mapping")
            names = contrast.get("effects")
            weights = contrast.get("weights")
            if not contrast.get("name") or not contrast.get("rationale"):
                raise ValueError(f"contrasts[{index}] requires name and rationale")
            if not isinstance(names, list) or not names or not isinstance(weights, list) or len(names) != len(weights):
                raise ValueError(f"contrasts[{index}] effects and weights must be non-empty and have equal length")
            unknown = sorted(set(map(str, names)) - effects)
            if unknown:
                raise ValueError(f"contrasts[{index}] references unknown effects: {', '.join(unknown)}")
            if not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in weights
            ) or all(float(value) == 0 for value in weights):
                raise ValueError(f"contrasts[{index}] weights must be finite and not all zero")
            normalized_contrasts.append(
                {
                    "name": str(contrast["name"]),
                    "effects": list(map(str, names)),
                    "weights": list(weights),
                    "rationale": str(contrast["rationale"]),
                    "confirmed_by_investigator": True,
                }
            )
    return {
        "type": design_type,
        "groups": {str(name): list(map(str, members)) for name, members in normalized_groups.items()},
        "covariates": {
            str(name): {str(subject): float(value) for subject, value in values.items()}
            for name, values in normalized_covariates.items()
        },
        "contrasts": normalized_contrasts,
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
