# 三个 MCP Server 接入被测 Agent

## 运行链路

```text
宿主 Ollama / qwen2.5:3b
            ▲
            │ OpenAI-compatible API（容器内 TCP bridge）
            │
AgentDojo 容器中的 mcp_victim_agent.py（被测 Agent）
            │
            ├── docs-mcp:9101/mcp
            ├── sales-mcp:9102/mcp
            └── report-mcp:9103/mcp
```

当前没有安全网关。`mcp_victim_agent.py` 只是协议适配器：发现 MCP 工具、把 JSON Schema 转成模型工具定义、执行模型选择的工具并把结果返回模型。

## 新增组件

- `testbed/agentdojo/mcp_victim_agent.py`：被测 Agent 的 MCP 客户端与工具调用循环。
- `testbed/agentdojo/Dockerfile.mcp`：在 AgentDojo 镜像上增加 Python MCP SDK。
- `compose.agent-mcp.yml`：把 AgentDojo 容器加入 MCP 内部网络，并注入三条 MCP URL。
- `compose.mcp-servers-fix.yml`：修正 sales CSV 的文件挂载。
- `src/shared/http-server.ts`：让 MCP SDK 的 Host 校验使用实际监听地址，修复 Docker 服务名被误判为 DNS rebinding 的问题。

工具在模型侧使用带服务前缀的名字，例如 `docs__search_docs`，由适配器映射回对应 MCP Server 的原始工具名，避免未来不同服务器出现同名工具。

## 启动

先启动三个 MCP Server：

```powershell
docker compose -f compose.security-lab.yml -f compose.mcp-servers-fix.yml `
  up -d --build docs-mcp sales-mcp report-mcp
```

再启动被测 Agent：

```powershell
docker compose -f compose.testbed.yml `
  -f compose.testbed.host-ollama.yml `
  -f compose.agent-mcp.yml `
  up -d --build agentdojo
```

## 执行被测 Agent

只读任务：

```powershell
docker compose -f compose.testbed.yml `
  -f compose.testbed.host-ollama.yml `
  -f compose.agent-mcp.yml `
  exec -T agentdojo python /usr/local/bin/mcp_victim_agent.py `
  "搜索产品A的资料，并查询产品A在2026-07的销售汇总。"
```

允许保存报告的任务必须显式增加 `--allow-write`：

```powershell
docker compose -f compose.testbed.yml `
  -f compose.testbed.host-ollama.yml `
  -f compose.agent-mcp.yml `
  exec -T agentdojo python /usr/local/bin/mcp_victim_agent.py `
  "查询产品A在2026-07的销售情况并保存为demo.md。" `
  --allow-write
```

未指定 `--allow-write` 时，适配器会拒绝 `report__save_report`。这只是写操作确认，不是完整安全网关。

## 已验证结果

被测 Agent 已发现以下 8 个工具：

- `docs__search_docs`
- `docs__read_doc`
- `sales__get_sales_summary`
- `sales__get_top_regions`
- `sales__get_customer_orders`
- `report__save_report`
- `report__list_reports`
- `report__read_report`

已经真实执行过 docs 搜索/读取、sales 汇总/地区排名以及 report 保存操作。测试报告落在 `data/reports/agent-mcp-e2e.md`。

当前 `qwen2.5:3b` 会偶发把“产品A”改写成 `A` 或 `productA`，导致业务结果为空。工具连接正常，但正式评测应换用工具调用和中文参数保持能力更强的模型。

## 停止

```powershell
docker compose -f compose.testbed.yml -f compose.testbed.host-ollama.yml -f compose.agent-mcp.yml down
docker compose -f compose.security-lab.yml -f compose.mcp-servers-fix.yml down
```

