from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.security.authentication import verifier_for_settings
from app.services.mcp_sidecar.task_context import TaskContextError
from tests.p1d1b3a_support import FakeGateway, mcp_session, planned_call, running_sidecar


def test_context_is_single_use_and_retry_returns_cached_safe_result() -> None:
    async def scenario() -> None:
        gateway = FakeGateway()
        async with running_sidecar(gateway) as (base, _):
            async with mcp_session(base) as session:
                await session.initialize()
                begin, first = await planned_call(
                    session, "business_docs.search_docs", {"keyword": "Product B"}
                )
                context = begin.structuredContent["context_id"]
                second = await session.call_tool(
                    "business_docs.search_docs",
                    {"keyword": "Product B", "_security_context_id": context},
                )
                assert first.structuredContent == second.structuredContent
                assert len(gateway.tool_calls) == 1
    asyncio.run(scenario())


def test_context_rejects_argument_change_and_catalog_change() -> None:
    async def scenario() -> None:
        gateway = FakeGateway()
        async with running_sidecar(gateway) as (base, _):
            async with mcp_session(base) as session:
                await session.initialize()
                begin = await session.call_tool("security.begin_task", {
                    "intent": "Search docs",
                    "plan_summary": "Search Product B.",
                    "target_tool": "business_docs.search_docs",
                    "planned_arguments": {"keyword": "Product B"},
                })
                context = begin.structuredContent["context_id"]
                changed = await session.call_tool(
                    "business_docs.search_docs",
                    {"keyword": "Product C", "_security_context_id": context},
                )
                assert changed.isError
                assert not gateway.tool_calls
                gateway.schema_suffix = "-changed"
                stale = await session.call_tool(
                    "business_docs.search_docs",
                    {"keyword": "Product B", "_security_context_id": context},
                )
                assert stale.isError
                assert not gateway.tool_calls
    asyncio.run(scenario())


def test_begin_task_accepts_cline_hashed_target_aliases() -> None:
    async def scenario() -> None:
        gateway = FakeGateway()
        async with running_sidecar(gateway) as (base, _):
            async with mcp_session(base) as session:
                await session.initialize()
                aliases = (
                    "business_docs_search_d_fd9f65bf",
                    "agent_security_platform_sidecar__business_docs_search_d_fd9f65bf",
                )
                for alias in aliases:
                    begin = await session.call_tool("security.begin_task", {
                        "intent": "Search docs",
                        "plan_summary": "Search Product B.",
                        "target_tool": alias,
                        "planned_arguments": {"keyword": "Product B"},
                    })
                    assert not begin.isError
                    assert begin.structuredContent["target_tool"] == "business_docs.search_docs"
    asyncio.run(scenario())


def test_context_identity_binding_rejects_other_principal() -> None:
    settings = Settings(app_env="test", auth_mode="test")
    verifier = verifier_for_settings(settings)
    alice = verifier.verify("test-token-alice")
    bob = verifier.verify("test-token-business")
    gateway = FakeGateway()
    catalog = __import__(
        "app.services.mcp_sidecar.tool_catalog", fromlist=["InboundToolCatalog"]
    ).InboundToolCatalog(gateway)
    tool = catalog.refresh("token").tools[0]
    store = __import__(
        "app.services.mcp_sidecar.task_context", fromlist=["TaskContextStore"]
    ).TaskContextStore(300)
    context = store.create(
        principal=alice,
        session_id="session_1",
        trace_id="trace_1",
        intent_id="intent_1",
        plan_id="plan_1",
        plan_version=1,
        agent_id="agent",
        intent="search",
        plan_summary="search once",
        tool=tool,
        planned_arguments={"keyword": "Product B"},
    )
    try:
        store.claim(
            context_id=context.context_id,
            principal=bob,
            tool=tool,
            arguments={"keyword": "Product B"},
        )
    except TaskContextError as exc:
        assert exc.code in {
            "TASK_CONTEXT_CREDENTIAL_MISMATCH",
            "TASK_CONTEXT_PRINCIPAL_MISMATCH",
        }
    else:
        raise AssertionError("cross-principal context must fail closed")
