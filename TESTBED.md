# Agent 安全测试床说明

当前 Windows 主机应使用 [TESTBED_HOST_OLLAMA.md](./TESTBED_HOST_OLLAMA.md) 中已经实测通过的宿主 Ollama 方案。

`compose.testbed.yml` 同时保留了全容器化 Ollama 服务，便于以后迁移到 Linux/CI。当前机器从 Docker Hub 拉取 Ollama 镜像时遇到 TLS 超时，因此本轮没有把该路径列为已验收方案，也不要使用旧命令中的 `--model openai-compatible`：PyPI 稳定版 AgentDojo 0.1.35 没有该模型枚举。

## 角色边界

- `agentdojo` 中的 AgentPipeline：被测 Agent。
- `agentdojo` 中的 attacks：敌手攻击逻辑。
- `agentdojo` 中的 suites/tools：模拟的工作区、Slack、旅行、银行等工具环境。
- `agentdojo` 中的 evaluators：正常任务与攻击目标评分。
- Ollama：被测 Agent 使用的底层 LLM。
- 未来安全网关：当前未接入，之后应插在 AgentPipeline 与模型、工具或 MCP 服务之间。

已有的 MCP Server 和 OPA 配置仍保留在代码中，供以后网关联调使用，但已从当前运行态停止，避免把未完成的防护误算为测试环境能力。

## 测试顺序

1. 冒烟：容器健康、Ollama `/v1/models` 可达、AgentDojo 安装可枚举。
2. 能力基线：不加攻击，测正常任务效用。
3. 攻击基线：加入一种 attack，确认攻击注入和双指标评分闭环。
4. 扩大矩阵：多个 suite、任务、攻击、模型，至少重复 3 次。
5. 接入网关：保持模型、任务和随机条件不变，做网关前后对照。

正式比较安全性前，被测 Agent 必须先达到可接受的正常任务效用。当前 `qwen2.5:3b` 只定位为冒烟模型。

