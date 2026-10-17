# Spec Delta

## ADDED Requirements

### Requirement: 事件类型只取自当前事件词表
系统 SHALL 只发出当前词表中的事件类型：`session/start`、`session/end`、`turn/start`、`turn/end`、`context/assembled`、`model/request`、`model/response`、`tool/call`、`tool/result`、`approval/request`、`approval/response`、`error/*`。`error/*` 在 M2 用到的具体类型是 `error/model`、`error/internal`、`error/abort`、`error/fence`。词表外的事实 MUST NOT 通过临时新造类型表达；`tool/cancelled` 与 `model/retry` 在 M2 MUST NOT 被写出。

#### Scenario: 一次带审批的写的事件序列
- **WHEN** 一次 run 的某回合派发一次获批的 `edit`
- **THEN** 该回合里事件类型按 `tool/call`、`approval/request`、`approval/response`、`tool/result` 的顺序成组出现

#### Scenario: 无法归类的内部故障仍走 error 命名空间
- **WHEN** 内核发生一个不属于任何既有 `namespace/method` 的故障
- **THEN** 日志写入 `error/internal` 记录，而不是新造事件类型

### Requirement: approval 事件记录问与答
系统 SHALL 在每次向人请求批准时写一条 `approval/request`（含 `turn_id`、`tool_call_id`、工具名、关键参数），并在得到结论时写一条 `approval/response`（含同样的 `turn_id` 与 `tool_call_id`，`decision` 取 `APPROVED`、`DENIED`、`UNAVAILABLE`）。每条 `approval/request` MUST 有且只有一条配对的 `approval/response`。

#### Scenario: 获批的一对记录
- **WHEN** 一次提问得到批准
- **THEN** 日志里该 `tool_call_id` 有一条 `approval/request` 与一条 `decision: APPROVED` 的 `approval/response`

#### Scenario: 词表每个 decision 值可达
- **WHEN** 跑完 M2 的 approval 场景（批准、拒绝、不可问人）
- **THEN** 三个 `decision` 取值各至少被一条测试断言到

### Requirement: 围栏拒绝写 error/fence
系统 SHALL 在围栏或审批拒绝终止 run 时写一条 `error/fence`，payload 含 `turn_id`、`code`、被拒的路径或工具名；该记录 MUST 在配对的 `tool/result` 之后、`turn/end` 之前写入。

#### Scenario: error/fence 的位置可断言
- **WHEN** 一次 run 因越界写终止
- **THEN** 日志里 `error/fence` 出现在该调用的 `tool/result` 之后、该回合的 `turn/end` 之前

## REMOVED Requirements

### Requirement: 事件类型只取自 M1 词表
**Reason**: M2 引入 `approval/request`、`approval/response` 与 `error/fence`，M1 的词表已经不能覆盖可观察行为；把里程碑写进词表要求本身会让每次扩词表都要改名。
**Migration**: 由本 delta 的「事件类型只取自当前事件词表」接替，M1 词表里的全部类型仍然有效，只是新增了三个类型。
