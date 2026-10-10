from __future__ import annotations

import sys
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp import Client, StdioServerParameters  # noqa: E402

from conn_pilot.mcp_server import build_mcp_server  # noqa: E402
from conn_pilot.operations import OPERATION_NAMES, REQUEST_SCHEMA, RESPONSE_SCHEMA  # noqa: E402


class StubOperationService:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        return {
            "schema_version": RESPONSE_SCHEMA,
            "operation": request["operation"],
            "ok": True,
            "generated_at": "2026-09-16T00:00:00+00:00",
            "data": {"received_arguments": request["arguments"]},
            "errors": [],
            "warnings": [],
        }


class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_lists_and_invokes_all_engine_operations(self) -> None:
        service = StubOperationService()
        server = build_mcp_server(service)  # type: ignore[arg-type]
        arguments = {
            "list_pipelines": {},
            "inspect_dataset": {"project_path": "project.yaml"},
            "validate_project": {"project_path": "project.yaml", "check_paths": False},
            "generate_execution_plan": {"project_path": "project.yaml"},
            "submit_job": {"project_path": "project.yaml"},
            "get_job_status": {"job_id": "job-1"},
            "get_job_progress": {"job_id": "job-1"},
            "get_job_logs": {"job_id": "job-1", "stream": "stderr", "tail": 25},
            "list_results": {"job_id": "job-1"},
            "get_qc_summary": {"job_id": "job-1"},
        }
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            self.assertEqual({tool.name for tool in tools}, set(OPERATION_NAMES))
            submit = next(tool for tool in tools if tool.name == "submit_job")
            self.assertFalse(submit.annotations.read_only_hint)
            for operation in OPERATION_NAMES:
                result = await client.call_tool(operation, arguments[operation])
                self.assertFalse(result.is_error, operation)
                self.assertEqual(result.structured_content["operation"], operation)
                self.assertTrue(result.structured_content["ok"])

        self.assertEqual([request["operation"] for request in service.requests], list(OPERATION_NAMES))
        self.assertTrue(all(request["schema_version"] == REQUEST_SCHEMA for request in service.requests))

    async def test_stdio_transport_exposes_real_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ)
            environment.update(
                {
                    "CONN_PILOT_CATALOG": str(ROOT / "catalog"),
                    "CONN_PILOT_ENVIRONMENT": str(ROOT / "config" / "environment.local.yaml"),
                    "CONN_PILOT_WORK_ROOT": str(Path(directory) / "work"),
                }
            )
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "conn_pilot.mcp_server"],
                env=environment,
                cwd=ROOT,
            )
            async with Client(parameters) as client:
                tools = (await client.list_tools()).tools
                result = await client.call_tool("list_pipelines", {})
        self.assertEqual({tool.name for tool in tools}, set(OPERATION_NAMES))
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["data"]["count"], 2)


if __name__ == "__main__":
    unittest.main()
