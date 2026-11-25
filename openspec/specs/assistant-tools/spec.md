# assistant-tools Specification

## Purpose
TBD - created by archiving change m14c-personal-assistant-tools. Update Purpose after archive.
## Requirements
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

### Requirement: `plan` 模式与精确批准

系统 SHALL 支持 `/plan` 进入计划模式、`/plan off` 退出，并以 `plan/mode {active}` 记录状态；`plan/mode` MUST 是整值替换的日志事件，`--resume` 与 `replay` MUST 从日志恢复。

计划模式 active 时，`write` / `edit` / `bash` / `subagent` SHALL 在派发前被拒绝（`subagent` 的子会话会继承工具表，必须一并拦），结果词 `DENIED_BY_PLAN` 且内容以 `计划模式：` 开头；`exit_plan_mode(plan)` MUST 不受拦截。`exit_plan_mode` SHALL 触发一次 `approval/request`，带 `purpose: "plan-review"` 与计划正文；**只有批准** SHALL 把 `plan/mode` 置为 `false`。拒绝或问不到人时 SHALL 保持 active，并把原因作为工具结果返回。

#### Scenario: 进入计划模式

- **WHEN** 用户输入 `/plan`
- **THEN** 日志新增 `plan/mode {active: true}`，后续写类调用被拒

#### Scenario: 计划期写类工具被拒

- **WHEN** 计划模式 active，模型调用 `write`
- **THEN** 结果是 `DENIED_BY_PLAN`，文件未变

#### Scenario: `/plan off` 也写事件

- **WHEN** 计划模式 active，用户输入 `/plan off`
- **THEN** 日志新增 `plan/mode {active: false}`

#### Scenario: 计划期 subagent 被拒

- **WHEN** 计划模式 active，模型调用 `subagent`
- **THEN** 结果是 `DENIED_BY_PLAN`，且子会话未启动

#### Scenario: 复核请求带正文

- **WHEN** 模型调用 `exit_plan_mode`，提交计划正文 P
- **THEN** 日志里 `approval/request` 的 payload 含 `purpose: "plan-review"` 与 `plan == P`

#### Scenario: 批准后恢复

- **WHEN** `exit_plan_mode` 的复核被批准，随后模型调用 `write`
- **THEN** 日志出现 `plan/mode {active: false}`，`write` 成功

#### Scenario: 拒绝保持计划模式

- **WHEN** 复核被拒绝
- **THEN** `plan/mode` 仍为 active，`write` 仍返回 `DENIED_BY_PLAN`，工具结果说明未批准

#### Scenario: 问不到人保持计划模式

- **WHEN** `exit_plan_mode` 的复核返回 `UNAVAILABLE`
- **THEN** `plan/mode` 仍为 active，随后 `write` 仍返回 `DENIED_BY_PLAN`

#### Scenario: 回放相等

- **WHEN** 对含 `plan/mode` 的日志执行 `minihns replay`
- **THEN** 逐点相等

#### Scenario: 恢复后状态一致

- **WHEN** 计划模式 active 时会话中断，随后 `--resume`
- **THEN** 计划模式仍为 active

### Requirement: `ask_user` 提问

系统 SHALL 提供 `ask_user(question, options?)`；提问与回答 SHALL 分别写 `question/asked` 与 `question/answered`，答案 SHALL 作为工具结果返回。`ask_user` MUST NOT 改变任何审批状态。问不到人时 SHALL 返回 `QUESTION_UNAVAILABLE`，MUST NOT 伪造答案。任一记录写不进日志时 MUST 返回 `TOOL_IO_FAILED`：问题写不进就不问人，答案写不进就作废。

#### Scenario: 答案进日志并回给模型

- **WHEN** 模型提问「用 A 还是 B」，人回答「A」
- **THEN** 日志有配对事件，工具结果是「A」

#### Scenario: 超时

- **WHEN** 提问无人回答
- **THEN** 工具结果为 `QUESTION_UNAVAILABLE`

#### Scenario: 日志写不进

- **WHEN** `question/asked` 写入失败
- **THEN** 工具结果为 `TOOL_IO_FAILED`，且没有向人提问

### Requirement: `present` 交付产物

系统 SHALL 提供 `present(path, title)`；路径 MUST 在工作区内且存在，成功后 SHALL 写 `present/artifact {path, title}`，CLI SHALL 打印产物路径。越界或不存在 SHALL 返回 `PRESENT_INVALID_PATH`。

#### Scenario: 合法产物

- **WHEN** `present` 指向工作区内已存在的文件
- **THEN** 日志新增 `present/artifact`，终端打印路径

#### Scenario: 越界

- **WHEN** `present` 指向工作区外的路径
- **THEN** 结果为 `PRESENT_INVALID_PATH`，不写事件

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

### Requirement: CLI 与 host 共用命令面

`/todo`、`/plan`、`/plan off` SHALL 在 CLI 与 host 上语义一致；host 的命令列表 SHALL 包含它们。

#### Scenario: host 列出命令

- **WHEN** 客户端请求命令列表
- **THEN** 返回里有 `/todo`、`/plan`

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

