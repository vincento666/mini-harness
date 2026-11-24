# align-turn-step-naming 真实端点验收

**状态**：待跑（2026-11-24 立；同日改端点）。端点按 `docs/reference/verification-endpoint.md`：OpenRouter 的 `qwen/qwen3.8-27b`，密钥变量 `OPENROUTER_API_KEY`。

**为什么不是 `--provider deepseek`**：2026-11-24 人裁，功能验证与调优统一走 OpenRouter 这个模型；deepseek 预设留在代码里，不再当验收端点。历史验收记录（`m13-*`、`skill-*` 等）不追改——那是过去的事实。

**口径**（ADR-0024）：这一半不进 CI、不替代四道门禁，只回答「接真实端点时改名后的东西还跑不跑得动」。判据钉值不钉形状。

## 前置

```bash
export OPENROUTER_API_KEY=...   # 必须进当前进程；mini-harness 不读 .env
curl -N https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{"model":"qwen/qwen3.8-27b","stream":true,"messages":[{"role":"user","content":"Hello"}]}' | head -3
```

**本机现状（2026-11-24 实测）**：`OPENROUTER_API_KEY` 不在 agent 进程环境、不在交互式 zsh 导出列表、不在 `launchctl` 环境、项目与 `~/.config/` 也没有 `.env`——所以下面三场由人来跑，或者先把变量注入到能跑命令的那个 shell 里。

## 场次

| # | 命令 | 要观察的值 | 结果 |
|---|---|---|---|
| 1 | `uv run minihns run -p "读 README.md 第一段并总结一句" --provider openai --base-url https://openrouter.ai/api/v1 --model qwen/qwen3.8-27b --api-key-env OPENROUTER_API_KEY --max-steps 3 --yes --workspace .tmp/verify/naming --session-dir .tmp/verify/naming/sessions` | 退出码 0；`session/end.stop_reason` ∈ `{MODEL_COMPLETED, TOOL_CALLS, MAX_STEPS}`；日志事件名只含 v2（`turn/*` 是轮、`step/*` 是步，无 `segment/*`） | 待填 |
| 2 | `uv run minihns usage <session-id> --session-dir .tmp/verify/naming/sessions` | JSON 里有 `turns`（按步聚合的用量列表）与 `total`；数值与场次 1 的 `model/response.usage` 逐条相等 | 待填 |
| 3 | 同一份日志跑 `uv run minihns replay <session-id> --session-dir .tmp/verify/naming/sessions` | 每个装配点逐点相等；退出码 0 | 待填 |

场次 1 若想同时看工具循环，把提示词换成「读 README.md 前 5 行，把行数写进 .tmp/verify/naming/lines.txt，再读回确认」——`qwen/qwen3.8-27b` 的 `supported_parameters` 含 `tools`，能派发工具。

## 排除项与理由

- 不测 v1 日志：兼容层已按 design D4 删除，`sessions/` 下 14 份样本作废；`SCHEMA_UNSUPPORTED` 由 `test_a_v1_line_is_rejected_with_schema_unsupported` 在 CI 里钉。
- 不测旧 flag / 旧配置键：已删除，`test_cli_config.py` 的类型错用例与 argparse 的未知参数行为覆盖。
- 不测 `--provider deepseek` 路径：端点换成 OpenRouter 后那条预设不在本 change 的验收面内；它由既有的 `test_cli_provider.py` 负责形状。
