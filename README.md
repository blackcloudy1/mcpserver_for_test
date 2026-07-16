# 局域网经营简报 MCP 工具链

这是一个由三个 MCP Server 组成的简单示例：

1. `docs-mcp`：搜索、读取产品文档。
2. `sales-mcp`：查询 CSV 销售数据。
3. `report-mcp`：保存、列出、读取 Markdown 经营简报。

此外包含一套供 Agent 安全网关验证的正常/攻击业务资料和敏感测试工具，详见 `GATEWAY_INTEGRATION.md`。

三个服务都使用无状态 Streamable HTTP：

| 服务 | MCP 地址 | 健康检查 |
|---|---|---|
| 文档 | `http://服务器IP:9101/mcp` | `http://服务器IP:9101/health` |
| 销售 | `http://服务器IP:9102/mcp` | `http://服务器IP:9102/health` |
| 报告 | `http://服务器IP:9103/mcp` | `http://服务器IP:9103/health` |

## 本机启动

需要 Node.js 20 或更高版本。

```powershell
npm.cmd install
npm.cmd run build
```

打开三个 PowerShell 窗口，分别运行：

```powershell
npm.cmd run start:docs
npm.cmd run start:sales
npm.cmd run start:report
```

服务默认监听 `0.0.0.0`，因此同一局域网的其他设备可以通过本机局域网 IP 访问。

运行自带的固定流程演示：

```powershell
npm.cmd run demo
```

生成的文件位于 `data/reports/产品A-2026-07.md`。

也可以用一个命令临时启动三个服务、运行演示并自动关闭：

```powershell
npm.cmd run test:smoke
```

查看三个服务实际暴露的工具和输入 Schema：

```powershell
npm.cmd run inspect:tools
```

## Docker Compose 启动

```powershell
docker compose up --build -d
docker compose ps
```

## Codex 客户端配置

以下配置仅用于验证三个业务服务本身。验证安全网关时不要让 Codex 直连这三个地址；Codex 应只配置网关的 `/mcp` 地址。

在客户端项目的 `.codex/config.toml` 中加入以下配置，把 `192.168.1.100` 换成运行服务的电脑 IP：

```toml
[mcp_servers.business_docs]
url = "http://192.168.1.100:9101/mcp"
bearer_token_env_var = "BUSINESS_MCP_TOKEN"

[mcp_servers.business_sales]
url = "http://192.168.1.100:9102/mcp"
bearer_token_env_var = "BUSINESS_MCP_TOKEN"

[mcp_servers.business_report]
url = "http://192.168.1.100:9103/mcp"
bearer_token_env_var = "BUSINESS_MCP_TOKEN"
```

重启客户端后，可以提出：

> 查找产品A的产品资料，查询2026年7月的销售汇总和销售区域排名，生成一份经营简报，并保存为 Markdown。

## 数据修改

- 产品资料：修改 `data/docs/*.md`。
- 销售数据：修改 `data/sales.csv`。
- 合成客户订单：`data/customer-orders.csv`，仅用于网关权限测试。
- 生成报告：保存在 `data/reports/`。

## 局域网访问

在服务端执行 `ipconfig` 找到 IPv4 地址，并确认 Windows 防火墙允许 TCP 9101、9102、9103 入站访问。

本项目默认不启用认证，只适合可信测试网络。服务端设置 `MCP_API_TOKEN` 后会启用 Bearer Token 校验；客户端或网关应从环境变量读取同一个值，不要把 Token 写入 Git。上面的 Codex 示例从 `BUSINESS_MCP_TOKEN` 读取客户端 Token。
