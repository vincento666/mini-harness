# 验证契约

**日期**：2026-11-18（第四版：按第一轮「契约与对齐复核」的 4 blocker / 13 major 修完；复核记录见 `docs/verification/m13-goal-rounds-dsh-review.md`）。

## 目标

让一个目标在无人插话时按轮次自动推进、撞上限后还能由人放回跑道，并且同一段里多个任务可以并存。

## 可观察行为

1. **续跑成形**：轮号连续、`revision` 不因轮次变化、正文带目标与轮号、四个事件顺序固定、该轮真的进了 `turn/start` 与 `model/request`、段数与段编号配对都对（seam ①④⑦）。
2. **上限与出入**：轮数用尽落 `round-limit` 且不再起段；「同一阻碍」的硬门槛是轮数——三轮之前报阻塞一律被拒；**撞上限之后改大上限并 resume，目标能回到 active 继续跑**（seam ②⑦）。
3. **武装权在人手里**：`armed` 不进事件载荷；启动与 `--resume` 后为假、不自动续跑；`/goal resume` 后才续；`pause` / `complete` / `blocked` / 撞上限 / 取消 / 失败收尾之后一律为假（seam ⑥⑦）。
4. **多任务互不覆盖**：同一段里两个任务可同时 `in_progress`；把一条标完成不会把另一条降级；段首（含 goal 轮次）清空；关闭并行时第二个被拒（seam ②④⑥）。
5. **边角不静默**：七个新结果词各有可达走法；`[goal]` 三键的默认与非法值在会话开始前处理；回放对正常日志退 0、对五类坏日志非零；写不进日志就停（seam ②④⑥）。

## 判据（seam 映射）

| 行为 | 判据 |
|---|---|
| 1 | seam ⑦：3 轮上限、无人插话 → goal 来源 `user/message` 恰 3 条；`source.round` 为 1/2/3；三条 `source.revision` 全等于 `create` 写入的 `1`（轮次不改 revision）；`source.goal_id` 全等 |
| 1 | seam ⑦：按 seq 取子序列，每轮为 `segment/end` → `segment/start` → goal 来源 `user/message` → `turn/start` → `goal/updated` → `model/request`；每条 goal 消息之后至少一条 `turn/start` 与一条 `model/request`，且属同一新 `segment_id` |
| 1 | seam ④：第 2 轮 goal 消息的 `content` 含 `Objective: "修好失败的用例"` 与 `Round: 2/3`，且非空 |
| 1 | seam ①：一次 `run` 续两轮后撞上限 → `segment/start` 恰 3 条，`segment_id` 为 `s1`/`s2`/`s3`，各配一条 `segment/end` |
| 1 | seam ⑥：含三轮续跑的日志 `replay` 退出码 `0`；把一条 `goal/updated` 的 `rounds_started` 改掉再跑 → 非零 |
| 2 | seam ⑦：第 4 轮不出现 goal 消息；最后一条 `goal/updated` 为 `blocked`、`code == "round-limit"`、`rounds_started == 3`；其后无 `segment/start` |
| 2 | seam ②：夹具 `max_rounds = 5`、门槛 3；`rounds_started` 为 1 和 2 各调一次 `blocked` → 都 `GOAL_BLOCK_TOO_EARLY` 且无新事件；为 3 时成功（`code == "model-reported"`、`message` 同入参） |
| 2 | seam ⑦：目标因 `round-limit` 落 blocked 后，把 `max_rounds` 改大、`/goal resume` → `phase == "active"`、无 `blocked_reason`、`armed == true`，随后出现新的 goal 消息 |
| 3 | seam ⑦：`/goal pause` 后不起段；`--resume` 之后到第一次 `model/request` 之间无 goal 消息；`/goal resume` 之后的下一次续跑出现 goal 消息 |
| 3 | seam ②：每条 `goal/updated` 的快照里**没有** `armed` 键；`pause` / `complete` / `blocked` / 撞上限各一次之后 `armed` 均为 `false` |
| 3 | seam ⑦：第 2 轮进行中被取消、段以 `ABORTED` 收尾 → 新增 `goal/updated` 的 `phase == "paused"`，`armed == false` |
| 4 | seam ②：调用 1 标 A、B 都 `in_progress`；调用 2 只把 A 标 `completed` → 第二次整表里 B 仍 `in_progress` |
| 4 | seam ④：一段里写两条后 `segment/end` 仍保留；其后任何新段（人类或 goal 来源）的 `segment/start` 之后值为 `[]` |
| 4 | seam ②：`allow_parallel_in_progress = false` 时一次标两个 `in_progress` → `TODO_PARALLEL_DISABLED` 且无新 `todo/updated`；默认配置下同一调用成功 |
| 4 | seam ⑥：同一段提交两条后 `/todo` 的 stdout 含两条 `id`；`GET /projections/todos` 返回两条，下一段开始后返回 `[]` |
| 5 | seam ②：`GOAL_ALREADY_ACTIVE`（有非 complete 目标时 create）、`GOAL_REF_STALE`（旧 revision）、`GOAL_AUTHORITY_REQUIRED`（子会话 create）、`GOAL_RESUME_BY_TOOL_DENIED`（paused 时工具 resume）各一条走法，四条都不产生新 `goal/updated` |
| 5 | seam ②：`GOAL_INVALID_TRANSITION` 一条走法（`blocked` 时 `pause`）、`GOAL_BLOCK_TOO_EARLY` 两条（`rounds_started` 为 1 与 2，门槛 3）——都不产生新 `goal/updated` |
| 5 | seam ②：目标 A `complete` 后能再 `create_goal`——新 `id`、`revision == 1`、`rounds_started == 0`；`replay` 接受轮号重置 |
| 5 | seam ②：`edit` 只给 `max_rounds` → `objective` 不变、`phase` 不变；给空串 objective 与 `max_rounds: 0` → 视为省略、`TOOL_ARGS_INVALID` 或不变（二者取实现的一种，判据钉日志无新事件） |
| 5 | seam ④：五份坏日志（跳号、轮号 0、超 `max_rounds`、`revision` 落后、`phase` 已停）各跑一次 `replay` → 全部非零；一份缺 `source` 的旧日志 → 退出 0 且按人类来源计入 |
| 5 | seam ⑥：无 `[goal]` 段时 `create_goal` 得 `max_rounds == 32`；`max_rounds = 0`、`blocked_after_consecutive_rounds = 0`、`allow_parallel_in_progress = "yes"` 三种非法配置 → 参数错误退出且 `sessions/` 无新日志 |
| 5 | seam ⑦：`ABORTED` / `FENCE_DENIED` / `PROVIDER_ERROR` / `CONTEXT_WINDOW_EXCEEDED` / `MAX_TURNS` 五种收尾各一次 → 都不起新段、不出现 goal 消息 |
| 5 | seam ⑦：第 2 轮段刚写完 goal 消息，provider 在 `turn/start` 前失败 → `rounds_started` 仍为 `1`（不计），且不再自动续跑 |
| 5 | seam ⑦：续跑时日志不可写 → 不出现新段、留下 `error/*`、非零退出 |
| 5 | seam ⑥：`/goal` 之后日志条数不变；`/goal clear` 后 `get_goal()` 为 `null`；无目标时 `/goal resume` 退出码 `0` 且日志条数不变 |

## 坏法清单（变异种子）

1. **只写消息不驱动模型**：续跑只追加 `user/message` 与 `goal/updated`，不开段。→ 行为 1 第 2 行必红。
2. **轮次改 revision**：每轮 `revision` 也 +1。→ 行为 1 第 1 行必红。
3. **顺序写反**：先写 `goal/updated` 再写 `segment/start`。→ 行为 1 第 2 行必红。
4. **正文只写「继续」**：goal 消息正文为空或不带 objective / Round。→ 行为 1 第 3 行必红。
5. **门槛写成 ≥1**：两轮也允许报阻塞。→ 行为 2 第 2 行必红。
6. **blocked 不可恢复**：`resume` 只认 `active`。→ 行为 2 第 3 行必红。
7. **额度提前到写消息时计**：不等首条 `turn/start`。→ 行为 5 的早失败用例必红。
8. **恢复即武装**：`--resume` 直接把 `armed` 置真。→ 行为 3 第 1 行必红。
9. **取消不置暂停**：`ABORTED` 只解除武装、`phase` 留在 active。→ 行为 3 第 3 行必红。
10. **回调把别人降级**：`completed` 一条时把其它 `in_progress` 一并改成 `pending`。→ 行为 4 第 1 行必红。

## 不验什么

- 不做多 goal 并存、不做轮次调度与公平性（deferred 到 `parallel-goal-scheduler`，见 ADR-0042）。
- 不做 token / 金额 / 墙钟预算；`max_rounds` 不是资源上限。
- 不做独立 evaluator；「完成」与「同一阻碍」的语义判断归模型，运行时只证明轮数门槛。
- 不做模型面的 goal 政策段（DSH 的 `tool:goal` 系统提示）；`deferred`，触发条件：真实使用里出现「模型反复试错才知门槛」的记录。
- 不做 GoalBar、宿主 `goal` 投影与 `goal/activation-changed` 事件；不做 host 的 `/goal` 命令。
- 不做 DSH 的 `queue-failed` / `prompt-rejected` 两个出口——mini 没有排队与 pre-step 链。
- 不做 fork 后的武装（ADR-0035 不做 fork）。
- 不验被取消的轮次能自动重跑：取消即暂停，属已知缺口。

## 待裁决

- `[goal]` 三键默认 32 / 3 / true——已定（2026-11-17）。
- 门槛大于 `max_rounds` 由配置层直接拒（见 `config-layering` delta），不是运行期宽容。
- 早失败不消耗轮次：计数点在首条 `turn/start` 之后，对齐 DSH「预约未准入不计数」——`aligned`。
