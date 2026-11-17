# M13 契约与对齐复核

**日期**：2026-11-18。位置按新流程（§0.4 第一道）：apply 之前。复核者是与撰写者不共享上下文的子代理；输入是 change 文件 + DSH 一手文件，不含实现叙事。

**结论**：第一轮 `GAPS`——4 blocker、13 major。本文记复核结论与处置；处置状态除 `aligned` 外都要人裁。

## A. 十项对齐

| 项 | DSH（一手） | mini（change 位置） | 结论 | 记账 |
|---|---|---|---|---|
| 1 形状 | `GoalSnapshot{id,revision,objective,phase,blockedReason?,maxGoalRounds}`，`roundsStarted` 是 `GoalView` 的派生值（`docs/subsystems/goal.md:44-70`）；`goal/change` 带 `operation` 与墓碑 | 快照把 `rounds_started` 写进载荷、`goal/updated{goal\|null}` | simplified | design D2；本轮修：轮次推进不再递增 `revision`，使轮内 ref 仍有效 |
| 2 机制 | 空闲 → `flush` 检查点 → 预约 → `followup` → `pre-step` 前后两次围栏（`driver_index.ts:106-221,372-452`） | 段后同协程判定 + 写三事件 | simplified | D3；丢 `competingQueued` 让位 |
| 3 语义 | `create` 可替换 `complete`；`resume` 接受已停目标（含 blocked）并清旧 blocker，且要有轮次余量（`goal README:68`） | 原稿只写 paused 拒绝、active 武装，blocked 无出口 | **blocker，本轮修** | 补 `blocked → active` 且清 `blocked_reason` |
| 4 不变量 | `roundsStarted` 只由进入模型历史的 goal 消息推进；activation 永不落盘 | 写作时即推进 | simplified（本轮显式记账） | 见 B4 |
| 5 面 | 模型面 = `<goal_round>`（objective + `Round: n/cap` + 指令，`prompt.ts:12-26`）+ `tool:goal` 政策段 | 无正文形状要求、无政策文本 | **blocker，本轮修正文；政策段记 deferred** | 正文补 Requirement；政策段触发条件：出现「模型反复试错才知门槛」的真实记录 |
| 6 失败 | `queue-failed` / `prompt-rejected` / `round-limit`；异常失败需人工 resume；`agent/error` 即 disarm | 只有 `round-limit`；失败收尾不续跑但未 disarm | simplified | 本轮把「失败收尾即 disarm」补进 Requirement 与判据 |
| 7 组合 | cap 属 goal、门槛属 tool-goal、并行属 todo 包，分属三处 | 全收进 `[goal]` 一段 | simplified | D7；代价：部署面分成三段变一段，语义归属变粗 |
| 8 资源 | cap 默认 256，只计 admitted rounds，不是资源预算 | 32 / 3 / true | simplified | 已记；`MAX_TURNS` 与轮次额度的关系见 major |
| 9 信任 | 精确 live agent + open turn；subagent 无权威，普通 fork 有 | 本段人类来源开机 + `entry=="subagent"` 拒绝 | aligned（等价，但 mini 无 live-agent 概念） | 复核者注：`entry` 判定与 DSH 的「运行时根 agent」不是同一层 |
| 10 回放 | 严格 fold 拒 malformed、revision 不连续、非法 phase 转换；损坏态 `GOAL_STATE_CORRUPT` | 只抄轮次五类 | simplified | 本轮补「按 `goal_id` 维度判跳号」；损坏态 deferred |

## B. 内部一致性缺口与处置

### Blocker（本轮已修）

| # | 缺口 | 处置 |
|---|---|---|
| B1 | 契约目标句仍写「在轮次之间各自保留」，与行为 4（每段清空）互斥 | 目标句改为「同一段里多个任务并存」，与 D8 一致 |
| B2 | goal 轮次消息**正文形状**无 Requirement；主规格 `context-projection` 只认「run prompt」与「REPL user/message」两个 user 来源 | 补 Requirement：正文是 `<goal_round>` 块，含 `Objective:` 与 `Round: n/cap`；补判据断言正文含 objective 与轮号；补 `context-projection` delta |
| B3 | `blocked` 无恢复路径：`round-limit` 落 blocked，driver 只推 `active`，resume 不认 blocked → 目标永久停摆 | `resume` 接受 `blocked`，置 `active` 并清 `blocked_reason`；补判据 |
| B4 | 额度在写 `goal/updated` 时即 +1，与 DSH 的「进历史才计数」不同；早失败的白烧无判据 | 保留简化（写日志即准入），但写成显式语义并加判据：provider 在 `turn/start` 前失败，该轮仍计入 `rounds_started` |

### Major（本轮修）

- 门槛 3 与 `max_rounds = 3` 冲突 → 阻塞门槛的判据改用 `max_rounds = 5` 的夹具。
- 写日志失败无判据 → 补一条：日志不可写时不起段、不写 `goal/updated`、以非零退出。
- 「取消即暂停」无 Requirement → 补：`ABORTED` 收尾把 `phase` 置 `paused`、`armed` 置假。
- `create` 替换 `complete` 无正向判据 → 补一条：complete 后能再 create，且轮号从 1 重启。
- 替换后轮号重启会被跳号校验误杀 → 校验按 `goal_id` 维度分组。
- `edit` 语义空白 → 补：部分替换、至少一个有效字段、空串/0 视为省略。
- 每轮递增 `revision` 使轮内 ref 立即 stale → 轮次推进**不**改 `revision`；只有控制面动作递增。
- `MAX_TURNS` 不在不续跑集合 → 加入集合（与 DSH 的 max-tokens 停止同向）。

### Major / Minor（记账，待人裁）

- **模型面政策段**（`tool:goal` 的系统提示）：mini 没有；`GOAL_BLOCK_TOO_EARLY` 只能靠试错。`deferred`，触发条件：真实使用里出现「模型反复试错才知门槛」的记录。
- **激活事件**（`goal/activation-changed`）与宿主 `goal` 投影：本 change 不做（非目标已列），结论 `deferred`，触发条件：壳需要实时显示武装状态。
- **损坏态 `GOAL_STATE_CORRUPT`**：mini 用 `replay` 非零退出代替专名；`simplified`，代价是错误分类粒度更粗。
- **`clear` 是否置假 `armed`**：mini 无观察后果（clear 后无目标），`aligned` by construction；不单列 Requirement。
- **门槛 > `max_rounds` 的配置组合**：不予校验，行为是「只能等 `round-limit`」；`simplified`，代价写在 config delta。
- **`fork` 后武装**：mini 无 fork（ADR-0035），`deferred`。
- **`queue-failed` / `prompt-rejected` 两个 DSH 出口**：mini 无排队与 pre-step 链，`deferred`，无对应实现面。

## C. 复核者的总评

> 判据能在「模型实际收到什么」和「轮次何时消耗额度」这两处全绿而实现是错的，且 `round-limit` 之后没有回到 active 的路径。

三条都指向同一件事：我把「状态机走通」当成够了，没检查「走完之后还能不能回来」。B3 是其中最贵的——一个只能进不能出的状态机。
