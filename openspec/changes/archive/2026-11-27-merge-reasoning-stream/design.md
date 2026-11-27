# 设计：把两条未合入分支迁移到当前主线

## D1 为什么合分支而不是重做

`reasoning-mode-and-budget` 的 27/28 项任务已完成（blocks、fold、SSE delta、usage、interrupted 锚点）。重做要再走一遍 2841 行新增；合分支只需解决 17 处冲突。人裁（2026-11-26）选「合入两条分支并迁移」。

## D2 合并顺序

`shell ⊂ reasoning`（`git rev-list reasoning..shell == 0`），所以只合 `reasoning`：

```bash
git switch -c merge/reasoning main
git merge --no-ff origin/change/reasoning-mode-and-budget
```

冲突按「main 的现状优先、分支的能力补齐」处理：

| 冲突点 | 处置原则 |
|---|---|
| `cli/main.py`（5 处） | 保留 main 的 `_chat_session` / `_ChatStreamRenderer` / `prompt_due`；把分支的 `[thinking]` 标志与 `on_reasoning` 接进现有渲染器（思考走 stderr，不污染 stdout） |
| `turn_loop.py`（3 处） | 保留 main 的 `on_step_end` 与 `DeltaState`；把分支的 reasoning delta 回调并入同一 sink 契约 |
| `provider/{contract,openai_compat}.py` | 保留 main 的流式实现；补 `reasoning_content` / `reasoning_details` 解析与 blocks 组装 |
| `tests/test_cli_chat.py`（3 处） | 保留 main 的流式判据；补思考帧判据（`[thinking]` 恰一次、思考不进 stdout、取消时半句保留不回归） |
| `docs/*` | 以 main 的 CURRENT/roadmap 为准，把分支记录并进去 |

## D3 词表迁移（关键风险）

分支写在 `align-turn-step-naming` 之前：它用 `segment` 表示「轮」、用 `turn` 表示「步」。合入后必须：

- 事件名 `segment/*` → `turn/*`、旧 `turn/*` → `step/*`；
- 字段 `segment_id` → `turn_id`、`turn_id`（旧义）→ `step_id`；
- 中文「回合 / 段」→「轮」，「步」保持不变。

机械替换会造病句（`align-turn-step-naming` 已踩过），所以要**逐处判量词**，并在规格里保持与 19 份主规格一致。

## D4 与政策 v3 的关系

`goal-round-pacing` 之后政策是 v3、`GOAL_POLICY_VERSIONS` 是版本表；分支里若有旧政策文本，一律丢弃，用 main 的版本表。

## D5 验收

- `uv run openspec validate --all --strict` 全绿（`reasoning` 主规格新建）。
- 全量 pytest：分支自带的 reasoning/golden 测试 + main 的 924 条全绿。
- 真实 reasoner（OpenRouter `qwen/qwen3.8-27b`）一场：日志 `model/response.blocks` 含 reasoning 与 text 且保序；SSE 有 `reasoning/delta` 与 `model/delta` 分离；usage 不含重复计。
- tty 一场：`[thinking]` 恰一次、思考实时滚出但**不进 stdout 正文**、`[answer]` 在正文前恰一次（按 ADR-0025 人跑）。
