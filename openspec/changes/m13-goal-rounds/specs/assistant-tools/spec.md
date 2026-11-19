# Spec Delta: assistant-tools

## MODIFIED Requirements

### Requirement: `todo` 工具维护会话待办

系统 SHALL 提供 `todo` 工具，支持新增、更新状态与完成；每次变更 SHALL 以整表替换写一条 `todo/updated`，条目形状为 `{id, text, status}`，`status` 取值 `pending` / `in_progress` / `completed`，缺省 SHALL 为 `pending`。纯折叠 SHALL 取最后一张表；投影的生命周期见「todos 投影」Requirement。

同一次调用里 SHALL 允许标记多个 `in_progress`；当配置 `allow_parallel_in_progress = false` 时，出现第二个 `in_progress` MUST 返回 `TODO_PARALLEL_DISABLED` 且整表 MUST NOT 落盘。

#### Scenario: 新增与完成

- **WHEN** 模型先新增两条待办，再把第一条标为完成
- **THEN** 日志里有两条 `todo/updated`，最后一张表的第一条 `status` 为 `completed`

#### Scenario: `/todo` 只打印不改表

- **WHEN** 用户输入 `/todo`
- **THEN** 终端打印当前表，日志里不新增 `todo/updated`

#### Scenario: 两个任务同时进行

- **WHEN** `allow_parallel_in_progress` 为 `true`，一次调用把两个条目都标为 `in_progress`
- **THEN** 结果是 `OK`，`todo/updated` 的整表里两条 `status` 都是 `in_progress`

#### Scenario: 关闭并行后拒绝第二个

- **WHEN** `allow_parallel_in_progress` 为 `false`，一次调用把两个条目都标为 `in_progress`
- **THEN** 结果是 `TODO_PARALLEL_DISABLED`，日志里不新增 `todo/updated`，之前那张表保持不变

### Requirement: `todos` 投影

系统 SHALL 提供 `todos` 投影：`todo/updated` 整表替换；`segment/start` SHALL 清空为 `[]`（**含 goal 来源的段**，照 DSH 的 `turn/start`）；`segment/end` SHALL 保留最后一张表；其它事件不改变状态。投影 SHALL 可从日志重建（`project(records, name)`），并通过 host 快照接口 `GET /sessions/{id}/projections/todos` 与 SSE `session/projection` 帧提供给 UI。

#### Scenario: 跨段清空

- **WHEN** 一段里有 `todo/updated`，下一段以 `segment/start` 开始
- **THEN** 投影值为 `[]`

#### Scenario: goal 轮次也清空

- **WHEN** 上一段留下两条待办，下一段由 goal 来源的 `user/message` 开启
- **THEN** 投影值为 `[]`——goal 轮次也是新段，与 DSH 的 `turn/start` 同一条规则

#### Scenario: 段内保留

- **WHEN** `segment/end` 之后再次投影
- **THEN** 仍是最后一张表

#### Scenario: 快照接口

- **WHEN** 客户端 GET `/sessions/{id}/projections/todos`
- **THEN** 返回 `{name, state_version, value}`；未知名字 404

## ADDED Requirements

### Requirement: `get_todos` 读回本段待办表

系统 SHALL 提供无入参的只读工具 `get_todos`，返回**本段**当前的待办表：内容取 `todos` 投影，与 `/todo`、`GET /sessions/{id}/projections/todos` MUST 同值；逐条形如 `- [status] id text`，并带一行计数（`pending` / `in_progress` / `completed`）。读回 MUST NOT 写 `todo/updated`、MUST NOT 改动任何状态。`segment/start` 之后读回 SHALL 是空表（投影在段首清空）；空表的结果 SHALL 说明「本段还没有提交过待办表」，MUST NOT 把上一段的表当成本段的。`get_todos` MUST NOT 被计划模式拦截，MUST NOT 触发审批，`meta` SHALL 带 `todo_read` 与 `todo_count`。

#### Scenario: 读回刚提交的表

- **WHEN** 模型在同一段里先 `todo(items=[t1, t2])`，再 `get_todos`
- **THEN** 结果是 `OK`，内容含 `- [in_progress] t1 …` 与 `- [pending] t2 …`，日志里 `todo/updated` 只有提交那一条

#### Scenario: 新段读回空表

- **WHEN** 上一段提交过表，新段的第一条调用是 `get_todos`
- **THEN** 结果是 `OK` 且说明当前待办为空；日志里不新增 `todo/updated`，上一段的表仍在日志里

#### Scenario: 计划模式与只读档位

- **WHEN** 计划模式 active（或 `--sandbox read-only`）时调用 `get_todos`
- **THEN** 结果是 `OK`，不是 `DENIED_BY_PLAN`，也没有审批请求

#### Scenario: 同批读回看到的是批首的表

- **WHEN** 同一批里既有一条 `todo` 又有一条 `get_todos`
- **THEN** `get_todos` 的内容是这一批开始之前的表——批首前缀只取样一次，与 `reads`、`goal` 同一条规则
