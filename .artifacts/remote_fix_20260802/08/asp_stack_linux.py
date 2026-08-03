#!/usr/bin/env python3
"""Linux runtime adapter for the rule-only backend + MCP sidecar stack."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


BACKEND = Path("/home/fcx/agent-security-platform/backend")
RUNTIME = Path("/home/fcx/.local/state/agent-security-promptfoo")
CONFIG_DIR = Path("/home/fcx/.config/agent-security")
TOKEN_FILE = CONFIG_DIR / "cline.jwt"
SECRET_FILE = CONFIG_DIR / "promptfoo-jwt.secret"
STATE_FILE = RUNTIME / "processes.json"
MCP_CONFIG = Path("/home/fcx/.cline-promptfoo/settings/cline_mcp_settings.json")
PYTHON = BACKEND / ".venv-linux/bin/python"
SCOPES = [
    "traces:create", "traces:read", "reports:read", "tools:read", "tools:write",
    "sensitive:read", "approvals:resolve", "mcp:servers:read",
    "mcp:tools:discover", "mcp:tools:read", "mcp:tools:invoke", "docs:read",
    "sales:read", "sales:customer:read", "report:read", "report:write",
]


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _token(secret: str) -> str:
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({
        "sub": "promptfoo_cline_validator", "tenant_id": "tenant_alpha",
        "roles": ["business_operator"], "scopes": SCOPES, "iat": now,
        "exp": now + 43_200, "iss": "agent-security-platform",
        "aud": "agent-security-api", "jti": secrets.token_hex(16),
    }, separators=(",", ":")).encode())
    signature = _b64(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def _env(secret: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite:///{RUNTIME / 'security_events.db'}",
        "APP_ENV": "validation", "AUTH_ENABLED": "true", "AUTH_MODE": "jwt",
        "JWT_SECRET": secret, "JWT_ISSUER": "agent-security-platform",
        "JWT_AUDIENCE": "agent-security-api", "PYTHONUNBUFFERED": "1",
    })
    return env


def _json_request(url: str, token: str = "", method: str = "GET", payload=None):
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    request = urllib.request.Request(url, headers=headers, data=data, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def _wait(url: str, seconds: int = 45):
    deadline = time.time() + seconds
    error = None
    while time.time() < deadline:
        try:
            value = _json_request(url)
            if value.get("status") == "ok":
                return value
        except Exception as exc:
            error = exc
        time.sleep(0.25)
    raise RuntimeError(f"readiness timeout for {url}: {error}")


def _start(name: str, command: list[str], env: dict, log_name: str, cwd=BACKEND):
    log = open(RUNTIME / "logs" / log_name, "ab", buffering=0)
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    return {"name": name, "pid": process.pid}


def _tcp_available(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def start() -> None:
    if not PYTHON.is_file():
        raise RuntimeError(f"Linux virtualenv missing: {PYTHON}; run bootstrap first")
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        if any(Path(f"/proc/{item['pid']}").exists() for item in state):
            raise RuntimeError("stack already has live owned processes")
    for port in (9101, 9102, 9103, 18080, 8200):
        if _tcp_available("127.0.0.1", port):
            raise RuntimeError(f"required loopback port already in use: {port}")
    for remote in (19101, 19102, 19103):
        if not _tcp_available("192.168.204.1", remote):
            raise RuntimeError(f"downstream business MCP unavailable: 192.168.204.1:{remote}")

    (RUNTIME / "logs").mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_urlsafe(48))
        os.chmod(SECRET_FILE, 0o600)
    secret = SECRET_FILE.read_text().strip()
    token = _token(secret)
    TOKEN_FILE.write_text(token)
    os.chmod(TOKEN_FILE, 0o600)
    env = _env(secret)
    processes = []
    try:
        for local, remote, name in (
            (9101, 19101, "docs-forwarder"), (9102, 19102, "sales-forwarder"),
            (9103, 19103, "report-forwarder"),
        ):
            processes.append(_start(
                name, [sys.executable, str(Path(__file__).with_name("asp_tcp_forward.py")),
                       "127.0.0.1", str(local), "192.168.204.1", str(remote)],
                env, f"{name}.log", Path(__file__).parent,
            ))
        for port in (9101, 9102, 9103):
            deadline = time.time() + 10
            while time.time() < deadline and not _tcp_available("127.0.0.1", port):
                time.sleep(0.1)
            if not _tcp_available("127.0.0.1", port):
                raise RuntimeError(f"forwarder failed on {port}")

        for command in (
            [str(PYTHON), "-m", "alembic", "upgrade", "head"],
            [str(PYTHON), "scripts/bootstrap_mcp_registry.py"],
            [str(PYTHON), "scripts/audit_database_schema.py"],
        ):
            subprocess.run(command, cwd=BACKEND, env=env, check=True, timeout=120)
        processes.append(_start(
            "backend", [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host",
                        "127.0.0.1", "--port", "18080", "--workers", "1",
                        "--no-access-log"], env, "backend.log",
        ))
        _wait("http://127.0.0.1:18080/api/health")
        for server_id in ("business_docs", "business_sales", "business_report"):
            _json_request(
                f"http://127.0.0.1:18080/api/mcp/servers/{server_id}/discover",
                token, "POST", {"reason": "promptfoo_runtime_wiring", "force": False},
            )
        tools = _json_request("http://127.0.0.1:18080/api/mcp/tools", token)
        if not isinstance(tools, list) or len(tools) != 8:
            raise RuntimeError(f"expected 8 active MCP tools, got {len(tools) if isinstance(tools, list) else 'invalid'}")

        sidecar_env = env.copy()
        sidecar_env.update({
            "MCP_SIDECAR_BACKEND_BASE_URL": "http://127.0.0.1:18080",
            "MCP_SIDECAR_HOST": "127.0.0.1", "MCP_SIDECAR_PORT": "8200",
            "MCP_SIDECAR_CREATED_CONTEXT_TTL_SECONDS": "600",
            "MCP_SIDECAR_CLAIMED_EXECUTION_TIMEOUT_SECONDS": "300",
            "MCP_SIDECAR_TERMINAL_RETENTION_SECONDS": "600",
            "MCP_SIDECAR_HTTP_TIMEOUT_SECONDS": "120",
        })
        processes.append(_start(
            "sidecar", [str(PYTHON), "scripts/run_mcp_sidecar.py"],
            sidecar_env, "sidecar.log",
        ))
        health = _wait("http://127.0.0.1:8200/health")
        if not health.get("backend_reachable"):
            raise RuntimeError(f"sidecar dependency health failed: {health}")

        MCP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        MCP_CONFIG.write_text(json.dumps({"mcpServers": {
            "agent_security_platform_sidecar": {
                "type": "streamableHttp", "url": "http://127.0.0.1:8200/mcp",
                "headers": {"Authorization": f"Bearer {token}"},
                "disabled": False, "timeout": 300,
            }
        }}, indent=2) + "\n")
        STATE_FILE.write_text(json.dumps(processes, indent=2) + "\n")
        print(json.dumps({"status": "running", "processes": processes, "tool_count": 8}))
    except Exception:
        for item in reversed(processes):
            try:
                os.killpg(item["pid"], signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        raise


def stop() -> None:
    if not STATE_FILE.exists():
        print('{"status":"not_running"}')
        return
    state = json.loads(STATE_FILE.read_text())
    for item in reversed(state):
        try:
            os.killpg(item["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
    STATE_FILE.unlink()
    print('{"status":"stopped"}')


def status() -> None:
    values = {}
    for name, url in (
        ("backend", "http://127.0.0.1:18080/api/health"),
        ("sidecar", "http://127.0.0.1:8200/health"),
    ):
        try:
            values[name] = _json_request(url)
        except Exception as exc:
            values[name] = {"status": "unavailable", "error": str(exc)}
    print(json.dumps(values, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("start", "stop", "status"))
    args = parser.parse_args()
    {"start": start, "stop": stop, "status": status}[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
