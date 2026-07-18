# LLM Agent 安全实验环境

该编排在原有 3 个 MCP 测试服务之外，增加 OPA 工具调用策略、文本规范化服务、受控的模拟外传接收器，以及可选的 Phoenix 可观测平台。所有宿主机端口只监听 `127.0.0.1`，容器网络默认禁止访问互联网。

## 启动

```powershell
Copy-Item .env.example .env
docker compose -f compose.security-lab.yml build
docker compose -f compose.security-lab.yml up -d
docker compose -f compose.security-lab.yml ps
```

如需调用链观测：

```powershell
docker compose -f compose.security-lab.yml --profile observability up -d
```

服务地址：

- 安全实验 API：<http://127.0.0.1:8080/docs>
- OPA：<http://127.0.0.1:8181>
- 模拟外传接收器：<http://127.0.0.1:9199/docs>
- MCP：`http://127.0.0.1:9101`、`9102`、`9103`
- Phoenix（可选）：<http://127.0.0.1:6006>

## 验证

```powershell
docker compose -f compose.security-lab.yml exec security-lab pytest -q
docker compose -f compose.security-lab.yml run --rm --entrypoint /opa opa test /policies -v
```

策略调用示例：

```powershell
$body = @{
  tool = @{ name = "http.request"; arguments = @{ host = "attacker.example" } }
  context = @{ mode = "normal"; contains_secret = $true }
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri http://127.0.0.1:8080/policy/evaluate -Method Post -ContentType application/json -Body $body
```

预期结果为 `deny`，原因为 `secret_to_untrusted_domain`。

## 安全边界

- 只使用 `lab/fixtures` 中的假数据和无效测试密钥。
- 不要把真实 API Key、SSH 私钥、浏览器配置或宿主机 Docker Socket 挂载进容器。
- `mock-egress` 只在本机内存记录测试事件，不会向公网发送数据。
- OPA 不可用时，安全 API 对带副作用工具采用 fail-closed（拒绝）策略。

## 停止与清理

```powershell
docker compose -f compose.security-lab.yml down
docker compose -f compose.security-lab.yml --profile observability down -v
```

后续可在这一底座上接入 MCP-in-the-middle、LlamaFirewall、OpenTelemetry，以及 AgentDojo、PyRIT、garak、promptfoo 等评测工具；建议每个工具单独通过 Compose profile 加入，避免把高风险靶场与日常开发环境混用。
