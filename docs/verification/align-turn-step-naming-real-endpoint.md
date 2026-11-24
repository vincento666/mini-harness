# align-turn-step-naming 真实端点验收

**状态**：待跑（2026-11-24 立）。本机环境里没有 `DEEPSEEK_API_KEY`，agent 未代跑。

**口径**（ADR-0024）：这一半不进 CI、不替代四道门禁，只回答「接真实端点时改名后的东西还跑不跑得动」。判据钉值不钉形状。

## 场次

| # | 命令 | 要观察的值 | 结果 |
|---|---|---|---|
| 1 | `uv run minihns run -p "读 README.md 第一段并总结一句" --provider deepseek --model deepseek-chat --max-steps 3 --yes --workspace .tmp/verify/naming --session-dir .tmp/verify/naming/sessions` | 退出码 0；`session/end.stop_reason` ∈ `{MODEL_COMPLETED, TOOL_CALLS}`；日志事件名只含 v2 | 待填 |
| 2 | `uv run minihns usage <session-id> --session-dir .tmp/verify/naming/sessions` | JSON 里有 `turns`（步的用量列表）与 `total`；数值与场次 1 的 `model/response.usage` 逐条相等 | 待填 |
| 3 | 同一份日志跑 `uv run minihns replay <session-id> --session-dir .tmp/verify/naming/sessions` | 每个装配点逐点相等；退出码 0 | 待填 |

## 排除项与理由

- 不测 v1 日志：兼容层已按 design D4 删除，`sessions/` 下 14 份样本作废；`SCHEMA_UNSUPPORTED` 由 `test_a_v1_line_is_rejected_with_schema_unsupported` 在 CI 里钉。
- 不测旧 flag / 旧配置键：已删除，`test_cli_config.py` 的类型错用例与 argparse 的未知参数行为覆盖。
