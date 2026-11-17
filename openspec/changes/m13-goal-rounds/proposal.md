# Proposal

## Why

今天的长任务只能靠人不断回车：一次输入收敛后会话就停，模型没有「继续做」的入口。待办表虽然在，但段边界一到就清空，跨轮的任务进度留不住——这正好卡住「多个任务各自推进」这件事。目标轮次解决前一半（不靠人续跑），任务并行解决后一半（状态跨轮保留），两者在 M13 合成一件事。

## What Changes

- **`goal` 域**：`goal/updated` 整值替换事件（`null` 表示清除），载荷含 `id`、`revision`、`objective`、`phase`、`max_rounds`、`rounds_started`、可选 `blocked_reason`；`phase ∈ active | paused | blocked | complete`；每次改动 `revision` 递增，用作比较交换。
- **三个工具**：`get_goal()`、`create_goal(objective, max_rounds?)`、`update_goal(goal_id, revision, action, ...)`；`action ∈ edit | pause | resume | complete | blocked`。**单 goal**：只在无目标或上一个已 `complete` 时才能创建。
- **轮次驱动**：`turn/end` 之后若目标 `active`、已武装、且还有轮次额度，则开新段并写一条 goal 来源的 `user/message`（`source.round` 连续递增），继续主循环；额度用尽则落 `phase = blocked`、`blocked_reason.code = "round-limit"`。
- **`user/message` 增 `source`**：`{kind: "user"}`（缺省）或 `{kind: "goal", goal_id, revision, round}`；旧日志缺字段按 `{kind: "user"}` 读。
- **任务并行**：`todo` 允许一次标多个 `in_progress`；`allow_parallel_in_progress = false` 时第二个 `in_progress` 被拒（`TODO_PARALLEL_DISABLED`）。
- **`todos` 投影清空条件**：只在**人类来源**消息开启的段首清空；goal 来源的段保留上一张表。
- **CLI `/goal`**：查看当前目标与剩余轮次、`pause`、`resume`、`clear`。
- **配置**：`[goal]` 段三键——`max_rounds`（默认 32）、`blocked_after_consecutive_rounds`（默认 3）、`allow_parallel_in_progress`（默认 `true`）。

## Capabilities

### New

- `goal`：目标的状态机、事件、工具、轮次归属与阻塞门槛。

### Modified

- `assistant-tools`：`todo` 的并行校验与 `todos` 投影的清空条件。
- `turn-loop`：段结束后按目标条件续跑。
- `cli`：`/goal` 命令面。
- `config-layering`：`[goal]` 段。

## Impact

- 事件词表 +1：`goal/updated`；`user/message` payload 增 `source` 字段。
- 结果词 +6：`GOAL_ALREADY_ACTIVE`、`GOAL_REF_STALE`、`GOAL_AUTHORITY_REQUIRED`、`GOAL_RESUME_BY_TOOL_DENIED`、`GOAL_BLOCK_TOO_EARLY`、`TODO_PARALLEL_DISABLED`。
- 工具注册表 +3；CLI 命令 +1；配置段 +1。
- 折叠：`goal/updated` 取最后值；`user/message` 的 `source` 参与轮次校验，不参与折叠。
- 回合主循环多一个出口：段结束后可能再开一段（显式条件，不引入隐式重试）。

## 人裁决

六问答案（2026-11-17，人给）：

1. **非目标**：先做到「状态并行」；多 goal 并存的调度后置到 `parallel-goal-scheduler`（不占 M 编号），本 change 不碰。不做同回合并发与公平性。
2. **最易被假过的判据**：原文是「两目标不覆盖」。本 change 收窄为单 goal，等价风险改落在「多任务互不覆盖」：只断言事件条数或两个 id 都在就能绿，所以判据钉投影值与 `/todo` 的实际输出。
3. **要补的一手调研**：按裁示补 `goal-round-driver` 的竞态——预约 → 准入、`agent/pre-step` 前后两次围栏、`sessions.flush()` 检查点；结论写在 design D3。
4. **是否动不变量与规格**：两者都加——新增 `goal/updated` 事件族，同时给 `user/message` 加来源字段；ADR-0042 记简化与代价。
5. **预授权简化**：任务并行做成状态并行（不引入任务级调度器）；多目标调度整体后置。
6. **范围上限**：单 goal + 多任务，≤12 个切片；撞到「多 goal 并存」就停并升级。

## 非目标

- 多 goal 并存、轮次调度、优先级与公平性（deferred，见 ADR-0042）。
- token / 金额 / 墙钟预算；`max_rounds` 不是资源上限。
- 独立 evaluator 或验收代理；完成与「同一阻碍」的判断权在模型。
- GoalBar、host 的 goal 回显与投影帧；只落事件与 CLI。
- 被取消轮次的自动重跑：取消即暂停。

## 验收

五种可观察行为全绿（见 `verification-contract.md`）；`replay` 逐点相等；四个门禁 + 真实端点一轮 + UAT 一轮 + 变异一轮。真实端点那一半只做一次「两轮小上限续跑」，不跑满 32 轮。
