#!/usr/bin/env python3
"""Fail-fast validation for the Promptfoo -> Cline -> sidecar stack."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import urllib.request

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


BACKEND = "http://127.0.0.1:18080"
SIDECAR = "http://127.0.0.1:8200/mcp"
TOKEN_FILE = Path("/home/fcx/.config/agent-security/cline.jwt")
SETTINGS = Path("/home/fcx/.cline-promptfoo/settings/cline_mcp_settings.json")


def request_json(url: str, token: str = ""):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(
        urllib.request.Request(url, headers=headers), timeout=10
    ) as response:
        return json.load(response)


async def check_sidecar(token: str) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(SIDECAR, headers=headers) as streams:
        read_stream, write_stream = streams[:2]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
    names = [tool.name for tool in listed.tools]
    if "security.begin_task" not in names or len(names) != 9:
        raise RuntimeError(f"sidecar expected 9 tools, got {names}")
    return len(names)


def main() -> int:
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("empty Agent Security Platform token")
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    servers = settings.get("mcpServers")
    if list(servers or {}) != ["agent_security_platform_sidecar"]:
        raise SystemExit("Cline must expose exactly one sidecar MCP server")
    backend_health = request_json(f"{BACKEND}/api/health")
    sidecar_health = request_json("http://127.0.0.1:8200/health")
    if backend_health.get("status") != "ok":
        raise SystemExit(f"backend unhealthy: {backend_health}")
    if sidecar_health.get("status") != "ok" or not sidecar_health.get(
        "backend_reachable"
    ):
        raise SystemExit(f"sidecar unhealthy: {sidecar_health}")
    tools = request_json(f"{BACKEND}/api/mcp/tools", token)
    ready_servers = [
        row
        for row in request_json(f"{BACKEND}/api/mcp/servers", token)
        if row.get("enabled") is True and row.get("connection_state") == "ready"
    ]
    active_tools = [row for row in tools if row.get("status") == "active"]
    if len(active_tools) != 8 or len(ready_servers) < 3:
        raise SystemExit(
            f"registry not ready: active_tools={len(active_tools)} "
            f"ready_servers={len(ready_servers)}"
        )
    sidecar_tools = asyncio.run(check_sidecar(token))
    print(
        json.dumps(
            {
                "status": "ready",
                "active_backend_tools": len(active_tools),
                "ready_servers": len(ready_servers),
                "sidecar_tools": sidecar_tools,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
