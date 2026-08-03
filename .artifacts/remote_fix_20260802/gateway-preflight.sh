#!/usr/bin/env bash
set -uo pipefail

mcp_settings="${1:?MCP settings path is required}"
token_file="${ASP_TOKEN_FILE:-/home/fcx/.config/agent-security/cline.jwt}"

if ! command -v jq >/dev/null 2>&1; then
  printf '%s\n' 'Preflight dependency missing: jq' >&2
  exit 2
fi

if ! jq -e '
  (.mcpServers | type) == "object"
  and (.mcpServers | keys) == ["agent_security_platform_sidecar"]
  and .mcpServers.agent_security_platform_sidecar.type == "streamableHttp"
  and .mcpServers.agent_security_platform_sidecar.url == "http://127.0.0.1:8200/mcp"
  and .mcpServers.agent_security_platform_sidecar.disabled == false
  and (.mcpServers.agent_security_platform_sidecar.headers.Authorization
       | type == "string" and startswith("Bearer "))
' "$mcp_settings" >/dev/null; then
  printf '%s\n' \
    'Invalid MCP topology: Cline must expose only the Agent Security Platform sidecar.' >&2
  exit 2
fi

if [[ ! -s "$token_file" ]]; then
  printf 'Agent Security Platform token is missing or empty: %s\n' "$token_file" >&2
  exit 2
fi

if ! backend_json="$(curl --noproxy '*' -fsS --max-time 3 \
  http://127.0.0.1:18080/api/health)"; then
  printf '%s\n' 'Agent Security Platform backend is unavailable.' >&2
  exit 2
fi
if ! jq -e '.status == "ok"' <<<"$backend_json" >/dev/null; then
  printf '%s\n' 'Agent Security Platform backend is not healthy.' >&2
  exit 2
fi

if ! sidecar_json="$(curl --noproxy '*' -fsS --max-time 3 \
  http://127.0.0.1:8200/health)"; then
  printf '%s\n' 'Agent Security Platform sidecar is unavailable.' >&2
  exit 2
fi
if ! jq -e '
  .status == "ok"
  and .backend_reachable == true
' <<<"$sidecar_json" >/dev/null; then
  printf '%s\n' 'Agent Security Platform sidecar dependencies are not healthy.' >&2
  exit 2
fi

if [[ ! -x /home/fcx/.local/bin/cline ]]; then
  printf '%s\n' 'Cline executable is missing.' >&2
  exit 2
fi
