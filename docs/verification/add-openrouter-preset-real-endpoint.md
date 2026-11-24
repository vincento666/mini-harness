# add-openrouter-preset 真实端点验收

**状态**：通过（2026-11-24）。端点 `https://openrouter.ai/api/v1`、模型 `qwen/qwen3.8-27b`、密钥变量 `OPENROUTER_API_KEY`（本机在 `~/.config/minihns/openrouter.env`，跑前 source）。

**口径**（ADR-0024）：不进 CI、不替代门禁，只回答「这个预设接上真端点跑不跑得动」。

## 场次

| # | 命令 | 要观察的值 | 结果 |
|---|---|---|---|
| 1 | 仓库根跑 `uv run minihns run -p "只回答一个词：ok" --max-steps 2 --yes --session-dir .tmp/verify/preset/sessions`（不给 provider/model 任何 flag） | `session/start` 的 `provider` / `model` / `base_url` / `api_key_env` | **通过**：退出码 0，会话 `e7ddeb0ccb504a72a96c251906d050b5`；四格分别是 `openrouter` / `qwen/qwen3.8-27b` / `https://openrouter.ai/api/v1` / `OPENROUTER_API_KEY` |
| 2 | 另开工作区跑 `uv run minihns run -p "只回答一个词：ok" --provider openrouter --max-steps 2 --yes --workspace .tmp/verify/preset/ws --session-dir .tmp/verify/preset/ws/sessions`（只给一个 flag） | 同上四格 | **通过**：退出码 0；四格与场次 1 完全相同，说明三项都由预设补齐 |

## 排除项

- 不测「没有 `OPENROUTER_API_KEY` 时」的形状：那条由 `test_config_presets` 与 `test_cli_provider` 的 `INVALID_ARGUMENT` 用例在 CI 里钉。
- 不测其它 provider：`openai` / `deepseek` / `mock` 的既有判据不受影响（全量跑过）。
