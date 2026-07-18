# Windows 宿主 Ollama + AgentDojo 测试床

这是当前机器已经验证通过的推荐运行方式：

- 宿主机 Ollama：提供被测大模型，当前为 `qwen2.5:3b`。
- AgentDojo 容器：提供被测 AgentPipeline、模拟工具环境、攻击器和评分器。
- 本地 TCP 桥：把容器内 `127.0.0.1:8000` 转发到宿主机 `host.docker.internal:11434`。
- 尚未接入安全网关；此时测得的是无防护基线。

AgentDojo 不是一个独立聊天式“敌手 Agent”。其中的 attack 负责把恶意指令植入第三方工具数据，被测 AgentPipeline 读取这些数据后，评估器分别检查正常任务效用和攻击目标是否达成。

## 启动与检查

```powershell
ollama list

docker compose -f compose.testbed.yml -f compose.testbed.host-ollama.yml up -d agentdojo
docker compose -f compose.testbed.yml -f compose.testbed.host-ollama.yml ps
docker compose -f compose.testbed.yml -f compose.testbed.host-ollama.yml logs --tail 20 agentdojo
docker compose -f compose.testbed.yml -f compose.testbed.host-ollama.yml exec -T agentdojo python /usr/local/bin/verify_agentdojo.py
```

日志应包含：

```text
127.0.0.1:8000 -> host.docker.internal:11434
```

## 无攻击基线

稳定版 AgentDojo 0.1.35 的命令行枚举区分大小写。对 Ollama 应使用 `VLLM_PARSED`，它通过 OpenAI 兼容接口使用原生工具调用。

```powershell
docker compose -f compose.testbed.yml -f compose.testbed.host-ollama.yml exec -T agentdojo `
  python -m agentdojo.scripts.benchmark `
  --model VLLM_PARSED --model-id qwen2.5:3b `
  --suite workspace --user-task user_task_0 `
  --logdir /workspace/runs/baseline-native-tools
```

## 最小攻击闭环

```powershell
docker compose -f compose.testbed.yml -f compose.testbed.host-ollama.yml exec -T agentdojo `
  python -m agentdojo.scripts.benchmark `
  --model VLLM_PARSED --model-id qwen2.5:3b `
  --suite workspace --user-task user_task_0 `
  --injection-task injection_task_0 --attack tool_knowledge `
  --logdir /workspace/runs/tool-knowledge-native-tools
```

结果保存在 `testbed/runs`。先保证无攻击基线有足够高的正常任务效用，再比较攻击成功率和安全得分；否则安全指标没有解释价值。

## 当前限制

`qwen2.5:3b` 已足以验证容器、模型连接、工具调用、攻击注入、评分和日志落盘，但实测正常任务效用为 0%，不适合作为正式安全评测的被测模型。正式评测应换成工具调用能力更强的本地模型或云端模型，并先建立正常任务基线。

AgentDojo 主要覆盖模拟工具环境中的间接提示注入。赛题要求中的直接注入、记忆/向量库污染、真实 MCP 返回值投毒、子 Agent 传播和多语言 Unicode 绕过，需要后续增加独立测试集。

## 停止

```powershell
docker compose -f compose.testbed.yml -f compose.testbed.host-ollama.yml down
```

