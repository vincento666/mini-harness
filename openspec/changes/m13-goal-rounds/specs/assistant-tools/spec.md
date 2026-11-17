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

系统 SHALL 提供 `todos` 投影：`todo/updated` 整表替换；段的驱动消息是**人类来源**（`user/message.source.kind == "user"`）时，该段首 SHALL 清空为 `[]`；驱动消息是 goal 来源（`kind == "goal"`）时 MUST 保留上一张表；`segment/end` SHALL 保留最后一张表；其它事件不改变状态。投影 SHALL 可从日志重建（`project(records, name)`），并通过 host 快照接口 `GET /sessions/{id}/projections/todos` 与 SSE `session/projection` 帧提供给 UI。

#### Scenario: 人类消息开启的段清空

- **WHEN** 上一段留下两条待办，用户输入新的一句话开启下一段
- **THEN** 投影值为 `[]`

#### Scenario: goal 轮次不清空

- **WHEN** 上一段留下两条待办，下一段由 goal 来源的 `user/message` 开启
- **THEN** 投影仍是那两条，`status` 不变

#### Scenario: 段内保留

- **WHEN** `segment/end` 之后再次投影
- **THEN** 仍是最后一张表

#### Scenario: 快照接口

- **WHEN** 客户端 GET `/sessions/{id}/projections/todos`
- **THEN** 返回 `{name, state_version, value}`；未知名字 404
