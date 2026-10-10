from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.types import ToolAnnotations

from . import __version__
from .operations import REQUEST_SCHEMA, OperationService


REPO_ROOT = Path(__file__).resolve().parents[2]


def build_operation_service() -> OperationService:
    """Build the local service from explicit environment overrides or repository defaults."""
    catalog_root = Path(os.environ.get("CONN_PILOT_CATALOG", REPO_ROOT / "catalog"))
    environment_path = Path(
        os.environ.get("CONN_PILOT_ENVIRONMENT", REPO_ROOT / "config" / "environment.local.yaml")
    )
    work_root = Path(os.environ.get("CONN_PILOT_WORK_ROOT", REPO_ROOT / "work"))
    return OperationService(
        catalog_root=catalog_root,
        environment_path=environment_path,
        work_root=work_root,
    )


def build_mcp_server(
    service: OperationService | None = None,
    *,
    token_verifier: TokenVerifier | None = None,
    auth: AuthSettings | None = None,
) -> MCPServer:
    """Expose the deterministic engine as MCP tools."""
    operation_service = service or build_operation_service()
    server = MCPServer(
        "CONN Pilot", version=__version__, token_verifier=token_verifier, auth=auth
    )
    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)

    def invoke(operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return operation_service.execute(
            {
                "schema_version": REQUEST_SCHEMA,
                "operation": operation,
                "arguments": arguments,
            }
        )

    @server.tool(
        title="List validated CONN pipelines",
        annotations=read_only,
    )
    def list_pipelines() -> dict[str, Any]:
        """List the CONN analysis pipelines available in the local versioned catalog."""
        return invoke("list_pipelines", {})

    @server.tool(
        title="Inspect a neuroimaging dataset",
        annotations=read_only,
    )
    def inspect_dataset(project_path: str) -> dict[str, Any]:
        """Inspect files, BIDS sidecars, repetition time, duplicates, and dataset boundaries for a project YAML."""
        return invoke("inspect_dataset", {"project_path": project_path})

    @server.tool(
        title="Validate a CONN project",
        annotations=read_only,
    )
    def validate_project(project_path: str, check_paths: bool = True) -> dict[str, Any]:
        """Validate a project YAML against its pipeline contract and optionally verify every local input path."""
        return invoke("validate_project", {"project_path": project_path, "check_paths": check_paths})

    @server.tool(
        title="Generate a CONN execution plan",
        annotations=read_only,
    )
    def generate_execution_plan(project_path: str) -> dict[str, Any]:
        """Resolve stages, parameters, design, dataset checks, and local environment before execution."""
        return invoke("generate_execution_plan", {"project_path": project_path})

    @server.tool(
        title="Submit a local CONN job",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    def submit_job(project_path: str) -> dict[str, Any]:
        """Validate and start one asynchronous MATLAB/SPM/CONN job on this computer using protected input copies."""
        return invoke("submit_job", {"project_path": project_path})

    @server.tool(
        title="Get CONN job status",
        annotations=read_only,
    )
    def get_job_status(job_id: str) -> dict[str, Any]:
        """Return persistent state, current phase, timestamps, and any execution error for a local job."""
        return invoke("get_job_status", {"job_id": job_id})

    @server.tool(
        title="Get detailed CONN job progress",
        annotations=read_only,
    )
    def get_job_progress(job_id: str) -> dict[str, Any]:
        """Return path-free stage, subject, activity, and approximate milestone progress for a local job."""
        return invoke("get_job_progress", {"job_id": job_id})

    @server.tool(
        title="Read CONN job logs",
        annotations=read_only,
    )
    def get_job_logs(
        job_id: str,
        stream: Literal["all", "stdout", "stderr", "worker"] = "all",
        tail: int = 200,
    ) -> dict[str, Any]:
        """Read the last lines of worker and MATLAB logs for a local job."""
        return invoke("get_job_logs", {"job_id": job_id, "stream": stream, "tail": tail})

    @server.tool(
        title="List CONN result artifacts",
        annotations=read_only,
    )
    def list_results(job_id: str) -> dict[str, Any]:
        """List indexed first-level, second-level, preprocessing, and QC artifacts for a job."""
        return invoke("list_results", {"job_id": job_id})

    @server.tool(
        title="Get CONN quality-control summary",
        annotations=read_only,
    )
    def get_qc_summary(job_id: str) -> dict[str, Any]:
        """Summarize technical completeness and per-subject QC evidence without making scientific exclusions."""
        return invoke("get_qc_summary", {"job_id": job_id})

    return server


mcp = build_mcp_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
