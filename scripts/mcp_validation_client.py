from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


DEFAULT_URL = "https://control-plane-production-0adf.up.railway.app/mcp"


def _credential() -> str:
    token = os.environ.get("CONN_PILOT_TOKEN") or os.environ.get(
        "CONN_PILOT_ADMIN_TOKEN"
    )
    if token:
        return token
    path = Path(__file__).resolve().parents[1] / ".env.distributed.local"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            if key.strip() in {"CONN_PILOT_TOKEN", "CONN_PILOT_ADMIN_TOKEN"}:
                return value.strip()
    raise RuntimeError("CONN Pilot credential is unavailable")


async def invoke(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {_credential()}"}
    url = os.environ.get("CONN_PILOT_MCP_URL", DEFAULT_URL)
    async with httpx2.AsyncClient(headers=headers, timeout=120.0) as client:
        async with streamable_http_client(url, http_client=client) as streams:
            read, write = streams
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments)
                text = "".join(
                    item.text
                    for item in result.content
                    if getattr(item, "type", None) == "text"
                )
                if not text:
                    return {"is_error": bool(result.is_error), "content": []}
                value = json.loads(text)
                if result.is_error:
                    raise RuntimeError(json.dumps(value, ensure_ascii=False))
                return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Invoke the deployed CONN Pilot MCP")
    parser.add_argument("tool")
    parser.add_argument("arguments", nargs="?", default="{}")
    args = parser.parse_args()
    arguments = json.loads(args.arguments)
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a JSON object")
    print(json.dumps(asyncio.run(invoke(args.tool, arguments)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
