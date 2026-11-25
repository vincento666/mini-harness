# Spec Delta: event-log

## MODIFIED Requirements

### Requirement: 事件类型只取自当前事件词表

系统 SHALL 只发出当前词表中的事件类型：`session/start`、`session/end`、`segment/start`、`segment/end`、`turn/start`、`turn/end`、`context/assembled`、`model/request`、`model/retry`、`model/response`、`user/message`、`tool/call`、`tool/result`、`tool/cancelled`、`approval/request`、`approval/response`、`compaction/summary`、`command/run`、`command/done`、`plan/mode`、`goal/updated`、`todo/updated`、`question/asked`、`question/answered`、`present/artifact`、`error/*`。`error/*` 用到的具体类型是 `error/model`、`error/internal`、`error/abort`、`error/fence`、`error/context`。词表外的事实 MUST NOT 通过临时新造类型表达。

#### Scenario: 一次带审批的写的事件序列

- **WHEN** 一次 run 的某回合派发一次获批的 `edit`
- **THEN** 该 `tool_call_id` 的记录按 `tool/call`、`approval/request`、`approval/response`、`tool/result` 的相对顺序出现

#### Scenario: goal 事件可写入词表

- **WHEN** 会话写入一条 `goal/updated`
- **THEN** 该行通过事件校验，重放时不被记为词表外类型
