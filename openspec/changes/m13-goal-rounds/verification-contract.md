# 验证契约

**日期**：2026-11-17。这是人审的那一页；通过后进入 apply。

## 目标

让一个目标在无人插话时按轮次自动推进到上限，并且多个任务的状态在轮次之间各自保留、互不覆盖。

## 可观察行为

1. **目标续跑**：`/goal` 之后无人插话，日志按轮次出现 goal 来源的 `user/message`，轮号从 1 连续递增，每轮一条（seam ⑦）。
2. **轮次上限**：轮数用尽后不再起新一轮，同一个 goal 落 `blocked`，`blocked_reason.code == "round-limit"`（seam ⑦）。
3. **人握着武装权**：`/goal pause` 之后不再续跑；`--resume` 恢复会话后也不自动续跑，要 `/goal resume` 才续（seam ⑥⑦）。
4. **多任务互不覆盖**：两个任务同时 `in_progress`，完成其一之后另一个仍是 `in_progress`；跨 goal 轮次 `/todo` 看到的仍是同一张表（seam ②④⑥）。
5. **并行关闭即拒绝**：`allow_parallel_in_progress = false` 时，同一次调用里标两个 `in_progress` 得 `TODO_PARALLEL_DISABLED`，表不变（seam ②）。

## 判据（seam 映射）

| 行为 | 判据 |
|---|---|
| 1 | seam ⑦：3 轮上限的日志里恰有 3 条 goal 来源的 `user/message`，`source.round` 为 1/2/3，`source.goal_id` 与 `goal/updated` 的 id 相同；`replay` 逐点相等 |
| 2 | seam ⑦：第 4 轮不出现 goal 来源消息；`goal/updated` 最后一条 `phase == "blocked"`、`blocked_reason.code == "round-limit"`、`rounds_started == 3` |
| 3 | seam ⑥：`/goal pause` 后跑一轮不再出现新段；`--resume` 后第一次模型调用前无 goal 消息，`/goal resume` 之后才出现；`get_goal` 的 `armed` 前后为 `false` / `true` |
| 4 | seam ④：`project(records, "todos")` 在 goal 来源段之后条目数不变、两个 `status` 各自正确；seam ②：一次调用标 A 完成、B 仍 `in_progress`，投影里两条并存；seam ⑥：第 2 轮 `/todo` 打印同一张表 |
| 5 | seam ②：同一条 `todo/updated` 不落盘，结果是 `TODO_PARALLEL_DISABLED`；开启时同一入参成功且表里两条都 `in_progress` |

## 坏法清单（变异种子）

1. **轮次只记内存**：`rounds_started` 留在内存里自增、不写 goal 来源的 `user/message`，日志只多 `goal/updated`。→ 行为 1 的 `source.round` 断言必红。
2. **一条消息反复推进**：每轮改写同一条 `user/message`（seq 不增）。→ 行为 1 的「恰有 3 条」必红。
3. **门槛写成 ≥1 轮**：`blocked_after_consecutive_rounds` 当成 1。→ 判据「第 1 轮调用 `update_goal`(blocked) 得 `GOAL_BLOCK_TOO_EARLY`」必红。
4. **并行只改校验不改投影**：允许两个 `in_progress`，但 `segment/start` 仍无条件清空。→ 行为 4 的「第 2 轮 `/todo` 同一张表」必红。
5. **恢复即武装**：`--resume` 直接把 `armed` 置 true。→ 行为 3 的「恢复后无 goal 消息」必红。

## 不验什么

- 不做多 goal 并存、不做轮次调度与公平性（deferred 到 `parallel-goal-scheduler`，见 ADR-0042）。
- 不做 token / 金额 / 墙钟预算；轮次上限不解释为资源上限。
- 不做独立 evaluator；「完成」与「同一阻碍」的语义判断归模型，运行时只证明轮数门槛。
- 不做 GoalBar 与 host 的 goal 回显；本 change 只落事件、`get_goal` 与 CLI。
- 不验证被取消的轮次能自动重跑：取消即暂停，属已知缺口。

## 待裁决

- `[goal] max_rounds` 默认 32 轮（DSH 的服务默认是 256）。
- goal 轮次开新段（一次驱动一段），`todos` 投影只在**人类来源**的段首清空。
- CLI 只做查看 / `pause` / `resume` / `clear`；创建走模型工具，不另开命令参数语法。
