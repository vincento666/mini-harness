# 验证契约

**日期**：2026-11-17（第三版：第二轮复核的 1 条 blocker + 6 条缺口已修；复核轮次已用尽，按 §0.4 交人裁）。

## 目标

让一个目标在无人插话时按轮次自动推进到上限，并且多个任务的状态在轮次之间各自保留、互不覆盖。

## 可观察行为

1. **续跑成形**：一轮续跑不只是「日志多一条消息」——轮号连续、`source.revision` 指向本轮之前那份快照、四个事件顺序固定、该轮真的进了 `turn/start` 与 `model/request`、段数与段编号配对都对（seam ①⑦）。
2. **上限与阻塞门槛**：轮数用尽落 `round-limit` 且不再起段；「同一阻碍」的硬门槛是轮数——三轮之前报阻塞一律被拒，三轮时才落 `model-reported`（seam ②⑦）。
3. **武装权在人手里**：`armed` 不进事件载荷；启动与 `--resume` 后为假、不自动续跑；`/goal resume` 后才续；`pause` / `complete` / `blocked` / 撞上限之后一律为假（seam ⑥⑦）。
4. **多任务互不覆盖**：同一段里两个任务可同时 `in_progress`；把一条标完成不会把另一条降级；段首（**含 goal 轮次**，对齐 DSH）清空；关闭并行时第二个 `in_progress` 被拒（seam ②④⑥）。
5. **边角不静默**：六个新结果词各有可达走法；`[goal]` 三键的默认与非法值在会话开始前处理；`/goal` 只读不写；回放既能对正常日志退出 0，也能对跳号日志非零退出（seam ②④⑥）。

## 判据（seam 映射）

| 行为 | 判据 |
|---|---|
| 1 | seam ⑦：3 轮上限、无人插话 → goal 来源 `user/message` 恰 3 条；`source.round` 为 1/2/3；第 n 条的 `source.revision` **等于它之前那条 `goal/updated` 的 `revision`**（第 1 轮即 `create` 写的 1），紧随其后的 `goal/updated` 的 `revision` 为该值 **+1**；三条的 `source.goal_id` 全等于该目标 `id` |
| 1 | seam ⑦：按 seq 取子序列，每轮必为 `segment/end` → `segment/start` → goal 来源 `user/message` → `goal/updated` → `turn/start` → `model/request`；每条 goal 消息之后至少一条 `turn/start` 与一条 `model/request`，且属同一个新 `segment_id` |
| 1 | seam ①：一次 `run` 续两轮、撞上限 → `segment/start` 恰 3 条，`segment_id` 为 `s1`/`s2`/`s3`，各有一条配对 `segment/end` |
| 1 | seam ⑥：含三轮续跑的日志跑 `replay` → 退出码 `0`；把其中一条 `goal/updated` 的 `rounds_started` 改掉再跑 → 非零（这一对合起来才证明「相等」不是自比自） |
| 2 | seam ⑦：第 4 轮不出现 goal 来源消息；最后一条 `goal/updated` 的 `phase == "blocked"`、`blocked_reason.code == "round-limit"`、`rounds_started == 3`；其后无 `segment/start` |
| 2 | seam ②：门槛 3 时，`rounds_started` 为 1 和 2 各调一次 `update_goal(blocked, reason="x")` → 两次都 `GOAL_BLOCK_TOO_EARLY`，日志无新 `goal/updated`；为 3 时同一调用成功，`blocked_reason.code == "model-reported"`、`message == "x"` |
| 3 | seam ⑦：`/goal pause` 之后不再起段；`--resume` 之后到第一次 `model/request` 之间无 goal 来源消息；`/goal resume` 之后的下一次续跑出现 goal 消息 |
| 3 | seam ②：每条 `goal/updated` 的 `goal` 快照里**没有** `armed` 键；`pause` / `complete` / `blocked` / 撞上限各一次之后，`get_goal()` 的 `armed` 均为 `false` |
| 4 | seam ④：一段里写两条后 `segment/end` 仍保留；其后任何新段（人类或 goal 来源）的 `segment/start` 之后值为 `[]`——两种来源同一条规则 |
| 4 | seam ②：调用 1 标 A、B 都 `in_progress`；调用 2 只把 A 标 `completed`、B 仍 `in_progress` → 第二次 `todo/updated` 的整表两条并存，B 仍 `in_progress` |
| 4 | seam ②：`allow_parallel_in_progress = false` 时一次调用标两个 `in_progress` → `TODO_PARALLEL_DISABLED`，日志无新 `todo/updated`；**默认配置**下同一调用成功（这就是该键默认 `true` 的可观察证据） |
| 4 | seam ⑥：同一段里提交两条后 `/todo` 的 stdout 含两条 `id`（期望值取自 `project`，比字符串包含） |
| 4 | seam ⑥：提交两条后 `GET /sessions/{id}/projections/todos` 返回两条；下一段开始后同一接口返回 `[]` |
| 5 | seam ②：四词各一条走法——存在非 `complete` 目标时 `create_goal` → `GOAL_ALREADY_ACTIVE`；提交旧 `revision` → `GOAL_REF_STALE`；子会话（`entry == "subagent"`）调 `create_goal` → `GOAL_AUTHORITY_REQUIRED`；`paused` 时 `update_goal(resume)` → `GOAL_RESUME_BY_TOOL_DENIED`；四条都不产生新 `goal/updated`（`TODO_PARALLEL_DISABLED` 见行为 4） |
| 5 | seam ④：跳号（第 2 条 `round` 写成 3）、轮号 0、`revision` 落后、`phase` 已停、轮号超上限——五份日志各跑一次 `replay`，全部非零 |
| 5 | seam ④：回放一份 `user/message` 不带 `source` 的旧日志 → `replay` 退出码 `0`，且该段按人类来源清空 `todos`（证明缺字段读成 `{kind:"user"}`） |
| 5 | seam ⑥：无 `[goal]` 段时 `create_goal` 得到 `max_rounds == 32`；`max_rounds = 0`、`blocked_after_consecutive_rounds = 0`、`allow_parallel_in_progress = "yes"` 三种非法配置各一次 → 参数错误退出且 `sessions/` 无新日志 |
| 5 | seam ⑦：四种失败收尾（`ABORTED`、`FENCE_DENIED`、`PROVIDER_ERROR`、`CONTEXT_WINDOW_EXCEEDED`）各一次 → 都不出现新段、不出现 goal 来源消息、不出现 `goal/updated` |
| 5 | seam ⑥：`/goal` 之后日志条数不变；`/goal clear` 之后 `get_goal()` 为 `null`；无目标时 `/goal resume` 退出码 `0` 且日志条数不变 |

## 坏法清单（变异种子）

1. **只写消息不驱动模型**：续跑只追加 `user/message` 与 `goal/updated`，不开段也不进 `turn/start`。→ 行为 1 第 2 行必红。
2. **`revision` 恒为 1**：快照每轮都写 `revision: 1`。→ 行为 1 第 1 行的「+1」必红。
3. **顺序写反**：先写 `goal/updated` 再写 `segment/start`。→ 行为 1 第 2 行的子序列必红。
4. **门槛写成 ≥1**：两轮也允许报阻塞。→ 行为 2 第 2 行的「`rounds_started == 2` 被拒」必红。
5. **段首不再清空**：把 `segment/start` 的清空删掉，改成只在人类消息上清。→ 行为 4 第 1 行（goal 段也清空）必红。
6. **恢复即武装**：`--resume` 直接把 `armed` 置真。→ 行为 3 第 1 行必红。
7. **回调把别人降级**：`completed` 一条时把其它 `in_progress` 一并改成 `pending`。→ 行为 4 第 2 行必红。

## 不验什么

- 不做多 goal 并存、不做轮次调度与公平性（deferred 到 `parallel-goal-scheduler`，见 ADR-0042）。
- 不做 token / 金额 / 墙钟预算；`max_rounds` 不是资源上限。
- 不做独立 evaluator；「完成」与「同一阻碍」的语义判断归模型，运行时只证明轮数门槛。
- 不做 GoalBar、不做 SSE `session/projection` 帧的 goal 语义、不做 host 的 `/goal` 命令。
- 不验被取消的轮次能自动重跑：取消即暂停，属已知缺口。

## 待裁决

- `[goal]` 三键默认 32 / 3 / true（DSH 服务默认 256 是无人值守长任务的量级）——已定。
- goal 轮次开新段（一轮一段）——已定；`todos` 每段清空，含 goal 轮，对齐 DSH（2026-11-18 裁）。
- CLI 只做查看 / `pause` / `resume` / `clear`；创建走模型工具。
