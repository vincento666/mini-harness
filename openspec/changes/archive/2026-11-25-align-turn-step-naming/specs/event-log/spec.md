# Spec Delta: event-log

## MODIFIED Requirements

### Requirement: 事件类型只取自当前事件词表

系统 SHALL 只发出当前词表（v2）中的事件类型：`session/start`、`session/end`、`turn/start`、`turn/end`、`step/start`、`step/end`、`context/assembled`、`model/request`、`model/retry`、`model/response`、`user/message`、`tool/call`、`tool/result`、`tool/cancelled`、`approval/request`、`approval/response`、`compaction/summary`、`command/run`、`command/done`、`plan/mode`、`goal/updated`、`todo/updated`、`question/asked`、`question/answered`、`present/artifact`、`error/*`。`error/*` 用到的具体类型是 `error/model`、`error/internal`、`error/abort`、`error/fence`、`error/context`。词表外的事实 MUST NOT 通过临时新造类型表达。

旧名 MUST NOT 被新写入使用。`schema_version == 1` 的记录 MUST 以 `SchemaUnsupported` 拒绝：v1 上迁只在改造期充当验证工具，合入前随兼容层一起删除（design D4，tasks 5.3）。

#### Scenario: 一次带审批的写的事件序列

- **WHEN** 一次 run 的某步派发一次获批的 `edit`
- **THEN** 该 `tool_call_id` 的记录按 `tool/call`、`approval/request`、`approval/response`、`tool/result` 的相对顺序出现

#### Scenario: goal 事件可写入词表

- **WHEN** 会话写入一条 `goal/updated`
- **THEN** 该行通过事件校验，重放时不被记为词表外类型

#### Scenario: v1 日志被拒

- **WHEN** 读取一条 `schema_version == 1`、类型为 `segment/start` 的记录
- **THEN** 读取以 `SCHEMA_UNSUPPORTED` 失败，不尝试猜它的新名字

#### Scenario: 新日志不写旧名

- **WHEN** 检查一次新会话的日志
- **THEN** 不存在 `segment/start`、`segment/end`，也不存在 v1 语义的 `turn/start`（它只能是 turn 的开始，不是 step 的开始）

## ADDED Requirements

### Requirement: 日志 schema 版本

每条记录的信封 SHALL 携带 `schema_version`；当前版本是 `2`。写入 MUST 用当前版本。读取 MUST 只接受 `2`；其它版本 MUST 以 `SchemaUnsupported` 拒绝，MUST NOT 尝试迁移或猜测。上迁 MUST NOT 改写磁盘上的原始行（这条对任何将来版本同样成立）。

#### Scenario: 不认识的版本被拒

- **WHEN** 读取一份 `schema_version == 1` 的日志
- **THEN** 以 `SCHEMA_UNSUPPORTED` 失败，且文件字节与读取前完全相同
