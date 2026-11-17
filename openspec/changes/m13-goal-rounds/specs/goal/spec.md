# Spec Delta: goal

## ADDED Requirements

### Requirement: 目标是会话里的单值状态

系统 SHALL 以 `goal/updated` 事件记录当前目标，载荷为 `{goal: <快照> | null}`；快照 MUST 含 `id`、`revision`、`objective`、`phase`、`max_rounds`、`rounds_started`，`phase` 取 `active` / `paused` / `blocked` / `complete` 之一，`blocked` 时 MUST 另含 `blocked_reason {code, message}`（两者非空）。`null` SHALL 表示目标被清除。纯折叠 SHALL 取最后一条的载荷；`goal/updated` MUST NOT 改写历史事件。

同一会话 MUST 至多一个非 `complete` 的目标。

#### Scenario: 创建后可读回同一份快照

- **WHEN** 人类在会话里提出一个目标，模型调用 `create_goal`
- **THEN** 日志恰新增一条 `goal/updated`，其 `goal.revision == 1`、`phase == "active"`、`rounds_started == 0`；`get_goal()` 返回同一份快照

#### Scenario: 每次改动递增 revision

- **WHEN** 对同一目标连续执行 `edit` 与 `pause`
- **THEN** 两条 `goal/updated` 的 `revision` 依次为 2 与 3，折叠取第三条

#### Scenario: 清除留下 null

- **WHEN** `/goal clear` 执行
- **THEN** 日志新增 `goal/updated {goal: null}`；`get_goal()` 返回 `null`；之前的历史快照仍在日志里

### Requirement: goal 工具及其权威

系统 SHALL 提供 `get_goal()`、`create_goal(objective, max_rounds?)`、`update_goal(goal_id, revision, action, objective?, max_rounds?, blocked_reason?)` 三个工具，`action` 取 `edit` / `pause` / `resume` / `complete` / `blocked`。所有工具结果 SHALL 是同一份紧凑 JSON：无目标时 `{"goal": null}`，否则含快照与 `armed`。

`create`、`edit`、`pause`、`resume` MUST 只在本段由人类来源的 `user/message` 开启时成立；`entry == "subagent"` 的会话 MUST NOT 具备该权威。`create` 在存在非 `complete` 目标时 MUST 返回 `GOAL_ALREADY_ACTIVE` 且不落事件。`update_goal` 的 `goal_id` 或 `revision` 与当前值不符时 MUST 返回 `GOAL_REF_STALE` 且不落事件。`resume` 对 `phase == "paused"` 的目标 MUST 返回 `GOAL_RESUME_BY_TOOL_DENIED`；该转换只由 `/goal resume` 完成。

#### Scenario: 单目标约束

- **WHEN** 当前目标 `active`，模型再次调用 `create_goal`
- **THEN** 结果是 `GOAL_ALREADY_ACTIVE`，日志不新增 `goal/updated`

#### Scenario: 旧 revision 被拒

- **WHEN** 目标已到 `revision == 3`，调用方仍提交 `revision == 2`
- **THEN** 结果是 `GOAL_REF_STALE`，`phase` 与 `rounds_started` 不变

#### Scenario: 子会话没有创建权

- **WHEN** 子会话（`entry == "subagent"`）里的模型调用 `create_goal`
- **THEN** 结果是 `GOAL_AUTHORITY_REQUIRED`，日志不新增 `goal/updated`

#### Scenario: 工具不能恢复已暂停的目标

- **WHEN** `phase == "paused"`，模型调用 `update_goal(action="resume")`
- **THEN** 结果是 `GOAL_RESUME_BY_TOOL_DENIED`，`phase` 仍为 `paused`，`armed` 仍为 `false`

#### Scenario: 无目标时读取不报错

- **WHEN** 会话里从未创建目标，模型调用 `get_goal`
- **THEN** 结果是 `OK`，内容为 `{"goal": null}`

### Requirement: 轮次是 goal 来源的用户消息

`user/message` 的载荷 SHALL 含 `source`：`{kind: "user"}` 或 `{kind: "goal", goal_id, revision, round}`；缺该字段的旧日志 MUST 按 `{kind: "user"}` 读。

goal 来源消息的 `round` MUST 等于写入时目标快照的 `rounds_started + 1`，`revision` MUST 等于该快照的 `revision`。`replay` MUST 在遇到轮号非正、跳号、`revision` 落后于 `goal/updated` 的当前值、`phase` 已停、或轮号超过 `max_rounds` 时判日志不自洽。

#### Scenario: 轮号连续

- **WHEN** 一个上限为 3 的目标连跑三轮
- **THEN** 三条 goal 来源 `user/message` 的 `source.round` 依次为 1、2、3，`source.goal_id` 与 `goal/updated` 的 `id` 相同

#### Scenario: 跳号被拒

- **WHEN** 回放一份把第二条 goal 消息的 `round` 写成 3 的日志
- **THEN** `replay` 以日志不自洽结束，退出码非零

#### Scenario: 旧日志缺 source 仍可读

- **WHEN** 回放一份 `user/message` 不带 `source` 的旧日志
- **THEN** `replay` 成功，该消息按人类来源计入

### Requirement: 轮次驱动与上限

段结束且 `turn/end.stop_reason` 不是 `ABORTED` / `FENCE_DENIED` / `PROVIDER_ERROR` / `CONTEXT_WINDOW_EXCEEDED` 时，系统 SHALL 检查当前目标：`phase == active`、`armed` 为真、`rounds_started < max_rounds` 三者同时成立才 SHALL 开新段，并按顺序写 `segment/start`、goal 来源的 `user/message`、`goal/updated`（`rounds_started` 递增、`revision` 递增）。三者任一不成立 MUST NOT 开新段。

`rounds_started` 已达 `max_rounds` 时，系统 SHALL 写 `goal/updated` 把 `phase` 置 `blocked`、`blocked_reason.code` 为 `round-limit`，并 MUST NOT 再起轮次。

#### Scenario: 三轮后撞上限

- **WHEN** `max_rounds == 3` 的目标无人插话跑满三轮
- **THEN** 日志里 goal 来源 `user/message` 恰三条；最后一条 `goal/updated` 的 `phase == "blocked"`、`rounds_started == 3`、`blocked_reason.code == "round-limit"`

#### Scenario: 暂停不续跑

- **WHEN** `phase == "paused"`
- **THEN** 段结束后不出现新的 goal 来源消息

#### Scenario: 围栏拒绝的段不触发续跑

- **WHEN** 段以 `FENCE_DENIED` 收尾
- **THEN** 不出现新的 goal 来源消息，也不写 `goal/updated`

#### Scenario: 未武装不续跑

- **WHEN** `phase == "active"` 但 `armed` 为假
- **THEN** 段结束后不出现新的 goal 来源消息

### Requirement: 阻塞需要轮数门槛

`update_goal(action="blocked")` MUST 要求 `blocked_reason` 非空；`rounds_started` 小于 `blocked_after_consecutive_rounds` 时 MUST 返回 `GOAL_BLOCK_TOO_EARLY` 且不落事件。被接受时快照的 `blocked_reason.code` MUST 为 `model-reported`，`message` 为调用方给出的原文。

#### Scenario: 一轮就报阻塞被拒

- **WHEN** `rounds_started == 1`、门槛为 3，模型调用 `blocked`
- **THEN** 结果是 `GOAL_BLOCK_TOO_EARLY`，`phase` 仍为 `active`

#### Scenario: 三轮后可报阻塞

- **WHEN** `rounds_started == 3`，模型带 `blocked_reason` 调用 `blocked`
- **THEN** `phase == "blocked"`、`blocked_reason.code == "model-reported"`、`message` 与入参相同

#### Scenario: 空原因被拒

- **WHEN** `blocked_reason` 为空串
- **THEN** 结果是 `TOOL_ARGS_INVALID`，`phase` 不变

### Requirement: 武装是进程内状态

`armed` MUST NOT 出现在任何事件载荷里，只活在会话运行期。会话启动、`--resume` 恢复、以及从日志重建会话之后，`armed` MUST 为假；只有 `/goal resume` 或 `update_goal(action="resume")` 能把它置真。`pause`、`complete`、`blocked` 以及达到轮次上限 MUST 把 `armed` 置假。

#### Scenario: 恢复后不自动跑

- **WHEN** 用 `--resume` 恢复一个 `active` 目标的会话
- **THEN** 第一次模型调用之前日志里没有新的 goal 来源消息，`get_goal()` 的 `armed` 为 `false`

#### Scenario: 恢复后人工续跑

- **WHEN** 恢复后用户输入 `/goal resume`
- **THEN** 下一条 `goal/updated` 的 `revision` 递增、`phase` 仍 `active`，`armed` 为 `true`，随后出现 goal 来源消息
