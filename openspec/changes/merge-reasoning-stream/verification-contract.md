# 验收契约：merge-reasoning-stream

## 范围

把 `origin/change/reasoning-mode-and-budget`（含祖先 `chat-streaming-shell`）迁移合入 main，使 chat 能显示 `[thinking]` 与 `[reasoning]` 增量；不改 `[轮]` 计数、不改政策内容、不改正文流式的既有判据。

## 必验

1. **无残留旧词**：`git grep` 在 `src/` 与 `openspec/specs/` 里搜 `segment`、`segment_id`、`回合` 命中为 0（`align-turn-step-naming` 的两类有意保留除外：旧名必须被拒的映射表、v1→v2 迁移说明）。
2. **正文流式不回归**：main 的 924 条测试全绿，尤其 `test_cli_chat.py` 的默认流式、`on_step_end` 回退、取消分叉、`prompt_due` 提示符判据。
3. **思考与正文分离**：真实 reasoner 一场，SSE 里 `reasoning/delta` 与 `model/delta` 各自出现、不混流；stdout 只有正文，思考走 stderr。
4. **日志形状**：`model/response.blocks` 保序（reasoning/text/tool-call）；`fold` 重放与实时一致；`reasoning_tokens` 不重复计入 usage。
5. **interrupted 锚点**：有已交付内容的取消写一条 `interrupted: true` 的 `model/response`；无内容只写 `model/attempt`，二者互斥。
6. **tty（人跑，ADR-0025）**：`[thinking]` 恰一次、思考实时滚出、`[answer]` 恰一次且位于正文前、轮边界分行正确。2026-11-27 人跑三轮通过后追加人裁：两个标记统一为「独占一行的头、内容另起」，`[answer]` 头行自带换行（`chat-streaming` delta MODIFIED 了主规格那一处形状——这是 UAT 反馈，不是「不改正文流式判据」边界的破坏：被改的只是标记行的形状，增量写 stdout、每轮恰一次、空 delta 不触发、去重回退全部不动）。

## 不验

- 不验「思考质量」：只验可达性与分离性。
- 不重做 VAD/预算策略：沿用分支既有 `reasoning_tokens` 计法，除非与 main 的 usage 计量冲突（冲突时以 main 的 `usage-metering` 规格为准，并在 design 记偏离）。

## 变异（至少两条）

- M1：把 `reasoning/delta` 也写进日志 → 判据 3/4 必须失败（日志出现 reasoning delta 记录）。
- M2：把 reasoning 增量接进正文 sink（`on_delta`）→ 判据 3 必须失败（stdout 出现思考文本）。
