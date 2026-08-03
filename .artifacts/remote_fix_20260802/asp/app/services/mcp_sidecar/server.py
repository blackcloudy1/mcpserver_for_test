from __future__ import annotations

from functools import partial
import re
from typing import Any
from uuid import uuid4

import anyio
import jsonschema
from mcp.server import Server
from mcp.types import CallToolResult, TextContent, Tool
from starlette.requests import Request

from app.security.principal import PrincipalContext
from app.services.agent_runtime.gateway_client import AgentGatewayError, GatewayClient
from app.services.mcp_sidecar.auth_context import (
    SidecarRequestError,
    request_credential,
    request_identity,
)
from app.services.mcp_sidecar.gateway_bridge import GatewayBridge, GatewayBridgeError
from app.services.mcp_sidecar.result_mapper import (
    call_tool_result,
    safe_error,
    safe_error_payload,
)
from app.services.mcp_sidecar.task_context import (
    TaskContext,
    TaskContextError,
    TaskContextStore,
    stable_hash,
)
from app.services.mcp_sidecar.tool_catalog import (
    SECURITY_CONTEXT_FIELD,
    CatalogSnapshot,
    InboundToolCatalog,
    SidecarCatalogError,
)


BEGIN_TASK_NAME = "security.begin_task"
CLINE_SERVER_TOOL_PREFIX = "agent_security_platform_sidecar__"
CLINE_HASHED_TOOL_RE = re.compile(r"^(?P<stem>[A-Za-z0-9_]+)_[0-9a-f]{8}$")
BEGIN_TASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "client_task_id": {
            "type": "string",
            "minLength": 8,
            "maxLength": 128,
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@-]{7,127}$",
            "description": "Client-generated non-secret idempotency identifier.",
        },
        "intent": {"type": "string", "minLength": 1, "maxLength": 8192},
        "plan_summary": {"type": "string", "minLength": 1, "maxLength": 512},
        "target_tool": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200,
            "description": "本任务计划调用的、由当前 tools/list 返回的入站工具名。",
        },
        "planned_arguments": {
            "type": "object",
            "description": "即将提交给目标工具的完整业务参数，不含安全上下文字段。",
        },
        "session_id": {
            "type": "string", "minLength": 1, "maxLength": 64,
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,63}$",
        },
        "agent_id": {
            "type": "string", "minLength": 1, "maxLength": 64,
            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,63}$",
        },
    },
    "required": ["intent", "plan_summary", "target_tool", "planned_arguments"],
    "additionalProperties": False,
}


class InboundMCPFacade:
    def __init__(
        self,
        *,
        gateway: GatewayClient,
        context_ttl_seconds: int,
        max_total_contexts: int = 1000,
        max_contexts_per_principal: int = 100,
        terminal_retention_seconds: int = 600,
        claimed_execution_timeout_seconds: float = 60.0,
    ) -> None:
        self.server: Server = Server(
            "agent-security-platform-inbound-sidecar",
            version="p1-d-1b-3a",
            instructions=(
                "Call security.begin_task before one proxied tool call. "
                "Gateway remains the sole security decision authority."
            ),
        )
        self.contexts = TaskContextStore(
            context_ttl_seconds,
            max_total_contexts=max_total_contexts,
            max_contexts_per_principal=max_contexts_per_principal,
            terminal_retention_seconds=terminal_retention_seconds,
            claimed_execution_timeout_seconds=claimed_execution_timeout_seconds,
        )
        self.catalog = InboundToolCatalog(gateway)
        self.bridge = GatewayBridge(gateway, self.contexts)
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            principal, credential = self._current_auth()
            try:
                snapshot = await self._refresh(principal, credential)
            except Exception as exc:
                raise RuntimeError(_stable_error_code(exc)) from None
            result = [
                Tool(
                    name=BEGIN_TASK_NAME,
                    title="Begin Security Task",
                    description=(
                        "Creates a real Session, Trace, Intent and Plan and returns "
                        "a one-call, identity-bound security context."
                    ),
                    inputSchema=BEGIN_TASK_SCHEMA,
                )
            ]
            result.extend(
                Tool(
                    name=tool.inbound_name,
                    title=tool.remote_name[:128],
                    description=tool.description,
                    inputSchema=tool.exposed_schema,
                )
                for tool in snapshot.tools
            )
            return sorted(result, key=lambda item: item.name)

        @self.server.call_tool(validate_input=False)
        async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
            try:
                principal, credential = self._current_auth()
                if name == BEGIN_TASK_NAME:
                    return await self._begin_task(principal, credential, arguments)
                return await self._proxy_call(
                    principal=principal,
                    credential=credential,
                    name=name,
                    arguments=arguments,
                )
            except (GatewayBridgeError, TaskContextError, SidecarCatalogError) as exc:
                return safe_error(
                    exc.code,
                    remote_io_performed=getattr(exc, "remote_io_performed", False),
                    tool_executed=(
                        None if getattr(exc, "remote_io_performed", False) is None else False
                    ),
                )
            except SidecarRequestError as exc:
                return safe_error(exc.code)
            except jsonschema.ValidationError:
                return safe_error("TOOL_ARGUMENT_SCHEMA_INVALID")
            except Exception:
                return safe_error(
                    "SIDECAR_INTERNAL_ERROR",
                    remote_io_performed=None,
                    tool_executed=None,
                )

    async def _begin_task(
        self,
        principal: PrincipalContext,
        credential: str,
        arguments: dict[str, Any],
    ) -> CallToolResult:
        if "client_task_id" not in arguments:
            arguments = {**arguments, "client_task_id": f"legacy_{uuid4().hex}"}
        try:
            jsonschema.validate(arguments, BEGIN_TASK_SCHEMA)
        except jsonschema.ValidationError as exc:
            raise GatewayBridgeError("BEGIN_TASK_SCHEMA_INVALID") from exc
        snapshot = await self._refresh(principal, credential)
        target = arguments.get("target_tool")
        if not isinstance(target, str):
            raise GatewayBridgeError("TARGET_TOOL_INVALID")
        if target.startswith(CLINE_SERVER_TOOL_PREFIX):
            target = target[len(CLINE_SERVER_TOOL_PREFIX):]
        try:
            snapshot.by_name(target)
        except SidecarCatalogError:
            match = CLINE_HASHED_TOOL_RE.fullmatch(target)
            candidates = []
            if match:
                stem = match.group("stem")
                candidates = [
                    item.inbound_name
                    for item in snapshot.tools
                    if re.sub(r"[^A-Za-z0-9_]", "_", item.inbound_name).startswith(stem)
                ]
            if len(candidates) != 1:
                raise
            target = candidates[0]
        arguments = {**arguments, "target_tool": target}
        tool = snapshot.by_name(target)
        request_hash = stable_hash({
            key: arguments.get(key)
            for key in (
                "intent", "plan_summary", "target_tool", "planned_arguments",
                "session_id", "agent_id", "parent_trace_id",
            )
        })
        reservation = self.contexts.reserve_begin(
            principal=principal,
            client_task_id=arguments["client_task_id"],
            request_hash=request_hash,
        )
        if reservation.owner:
            try:
                context = await self.bridge.begin_task(
                    principal=principal,
                    bearer_token=credential,
                    arguments=arguments,
                    tool=tool,
                )
                self.contexts.complete_begin(reservation.key_hash, context.context_id)
            except Exception as exc:
                self.contexts.fail_begin(reservation.key_hash, _stable_error_code(exc))
                raise
        else:
            completed = await anyio.to_thread.run_sync(
                partial(
                    reservation.event.wait,
                    self.contexts.claimed_execution_timeout_seconds,
                )
            )
            if not completed:
                raise TaskContextError("IDEMPOTENCY_REQUEST_IN_PROGRESS")
            context = self.contexts.resolve_begin(reservation.key_hash)
        return self._begin_task_result(context)

    def _begin_task_result(self, context: TaskContext) -> CallToolResult:
        safe = {
            "status": "task_context_created",
            "context_id": context.context_id,
            "session_id": context.session_id,
            "trace_id": context.trace_id,
            "target_tool": context.inbound_tool_name,
            "expires_in_seconds": self.contexts.ttl_seconds,
            "tool_executed": False,
            "safe_summary": "Security task context created; no downstream tool was executed.",
        }
        return CallToolResult(
            content=[TextContent(
                type="text",
                text="Security task context created; no downstream tool was executed.",
            )],
            structuredContent=safe,
            isError=False,
        )

    async def _proxy_call(
        self,
        *,
        principal: PrincipalContext,
        credential: str,
        name: str,
        arguments: dict[str, Any],
    ) -> CallToolResult:
        snapshot = await self._refresh(principal, credential)
        tool = snapshot.by_name(name)
        context_id = arguments.get(SECURITY_CONTEXT_FIELD)
        if not isinstance(context_id, str):
            raise TaskContextError("TASK_CONTEXT_REQUIRED")
        forwarded = {
            key: value for key, value in arguments.items()
            if key != SECURITY_CONTEXT_FIELD
        }
        jsonschema.validate(forwarded, tool.input_schema)
        claim = self.contexts.claim(
            context_id=context_id,
            principal=principal,
            tool=tool,
            arguments=forwarded,
        )
        if claim.cached_result is not None:
            return call_tool_result(claim.cached_result)
        try:
            safe = await self.bridge.call_gateway(
                context=claim.context,
                bearer_token=credential,
                arguments=forwarded,
            )
        except GatewayBridgeError as exc:
            safe = safe_error_payload(
                exc.code,
                remote_io_performed=exc.remote_io_performed,
                tool_executed=None if exc.remote_io_performed is None else False,
            )
            self.contexts.fail_safe(context_id, safe, uncertain=exc.terminal_uncertain)
            return call_tool_result(safe)
        except Exception:
            safe = safe_error_payload(
                "GATEWAY_RESULT_UNCERTAIN",
                remote_io_performed=None,
                tool_executed=None,
            )
            self.contexts.fail_safe(context_id, safe, uncertain=True)
            return call_tool_result(safe)
        self.contexts.complete(context_id, safe)
        return call_tool_result(safe)

    async def _refresh(
        self, principal: PrincipalContext, credential: str
    ) -> CatalogSnapshot:
        try:
            return await anyio.to_thread.run_sync(
                partial(self.catalog.refresh, credential, principal)
            )
        except AgentGatewayError as exc:
            raise SidecarCatalogError(exc.code) from exc

    def _current_auth(self) -> tuple[PrincipalContext, str]:
        request = self.server.request_context.request
        if not isinstance(request, Request):
            raise SidecarRequestError("AUTH_REQUIRED", 401)
        return request_identity(request.scope), request_credential(request.headers)


def _stable_error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str):
        return code[:128]
    return "TOOL_CATALOG_UNAVAILABLE"
