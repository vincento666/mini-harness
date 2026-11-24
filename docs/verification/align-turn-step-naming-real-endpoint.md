# align-turn-step-naming 真实端点验收

**状态**：**通过（2026-11-24）**。端点按 `docs/reference/verification-endpoint.md`：OpenRouter 的 `qwen/qwen3.8-27b`，密钥变量 `OPENROUTER_API_KEY`。三场会话 `1ef237b3d66f4da98a002a80eda2f7b9`，工作区 `.tmp/verify/naming`。

**为什么不是 `--provider deepseek`**：2026-11-24 人裁，功能验证与调优统一走 OpenRouter 这个模型；deepseek 预设留在代码里，不再当验收端点。历史验收记录（`m13-*`、`skill-*` 等）不追改——那是过去的事实。

**口径**（ADR-0024）：这一半不进 CI、不替代四道门禁，只回答「接真实端点时改名后的东西还跑不跑得动」。判据钉值不钉形状。

## 前置

```bash
export OPENROUTER_API_KEY=...   # 必须进当前进程；mini-harness 不读 .env
curl -N https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{"model":"qwen/qwen3.8-27b","stream":true,"messages":[{"role":"user","content":"Hello"}]}' | head -3
```

**密钥怎么进进程（2026-11-24 起可行）**：本机把 key 放在 `~/.config/minihns/openrouter.env`（`chmod 600`，仓库外），跑命令前 `set -a && . ~/.config/minihns/openrouter.env && set +a`。裸 curl 拿到 200 与 `finish_reason: stop` 即端点通；401 且 message 写着 `No API key in the Authorization header` 是变量没进这个进程，不是模型名或端点的问题。

## 场次

| # | 命令 | 要观察的值 | 结果 |
|---|---|---|---|
| 1 | `uv run minihns run -p "读 README.md 第一段并总结一句" --provider openai --base-url https://openrouter.ai/api/v1 --model qwen/qwen3.8-27b --api-key-env OPENROUTER_API_KEY --max-steps 3 --yes --workspace .tmp/verify/naming --session-dir .tmp/verify/naming/sessions` | 退出码 0；`session/end.stop_reason` ∈ `{MODEL_COMPLETED, TOOL_CALLS, MAX_STEPS}`；日志事件名只含 v2（`turn/*` 是轮、`step/*` 是步，无 `segment/*`） | **通过**：退出码 0、stderr 空；16 行全 `schema_version=2`；事件计数 `turn/start 1`、`step/start 2`、`turn/end 1`、`session/end 1`，无 `segment/*`；`session/end = {stop_reason: MODEL_COMPLETED, steps: 2}`；模型确实派发了 `read`（`tool/call 1`、`tool/result 1`） |
| 2 | `uv run minihns usage 1ef237b3… --session-dir .tmp/verify/naming/sessions` | JSON 里有 `steps`（按步聚合的用量列表）与 `total`；数值与场次 1 的 `model/response.usage` 逐条相等 | **通过（修过一处，见下）**：`steps = [{step_id t1, 203/2816/0/70}, {step_id t2, 297/2816/0/59}]`，与日志两条 `model/response` 逐字段相等；`total = 500/5632/0/129` 正是两行之和；`cost` 为 `null`（配置里没有这个模型的 `[pricing]`）。**两行的 `cache_read` 都是 2816**，说明 OpenRouter 侧命中了前缀缓存 |
| 3 | 同一份日志跑 `uv run minihns replay 1ef237b3… --session-dir .tmp/verify/naming/sessions` | 每个装配点逐点相等；退出码 0 | **通过**：`verified seq=3: OK`、`verified seq=10: OK`；`step t1: TOOL_CALLS`、`step t2: MODEL_COMPLETED`；退出码 0 |

## 场次 2 暴露的一处键名残留（同批修掉）

第一次跑场次 2 时输出是 `{"turns": [{"turn_id": "t1", …}, {"turn_id": "t2", …}], …}`——**列表里两项、而这份会话只有一轮**。原因不是计量错，是键名错：`usage` 的单位是步（`metering.collect_usage` 返回 `step_id`），JSON 却沿用了 v1 的 `turns[] / turn_id`。同样的错还有一处：SSE 的 `model/delta` 帧把步 id 装在 `turn_id` 键里。

两处都在 `tasks.md` 3.6 一起改：`usage` 输出 `steps[] / step_id`、`model/delta` 帧 `{step_id, index, text}`；补了 `host-api` 与 `usage-metering` 两份 delta 规格，判据是「一轮两步 → `steps[]` 两项」与「delta 帧的 `step_id` 与同一步 `model/response` 对得上」。改完复跑：三场全绿。

场次 1 若想同时看工具循环，把提示词换成「读 README.md 前 5 行，把行数写进 .tmp/verify/naming/lines.txt，再读回确认」——`qwen/qwen3.8-27b` 的 `supported_parameters` 含 `tools`，能派发工具。

## 排除项与理由

- 不测 v1 日志：兼容层已按 design D4 删除，`sessions/` 下 14 份样本作废；`SCHEMA_UNSUPPORTED` 由 `test_a_v1_line_is_rejected_with_schema_unsupported` 在 CI 里钉。
- 不测旧 flag / 旧配置键：已删除，`test_cli_config.py` 的类型错用例与 argparse 的未知参数行为覆盖。
- 不测 `--provider deepseek` 路径：端点换成 OpenRouter 后那条预设不在本 change 的验收面内；它由既有的 `test_cli_provider.py` 负责形状。
