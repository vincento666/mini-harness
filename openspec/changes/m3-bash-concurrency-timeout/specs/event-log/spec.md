# Spec Delta

## MODIFIED Requirements

### Requirement: 事件类型只取自当前事件词表
系统 SHALL 只发出当前词表中的事件类型：`session/start`、`session/end`、`turn/start`、`turn/end`、`context/assembled`、`model/request`、`model/retry`、`model/response`、`tool/call`、`tool/result`、`tool/cancelled`、`approval/request`、`approval/response`、`error/*`。`error/*` 用到的具体类型是 `error/model`、`error/internal`、`error/abort`、`error/fence`。词表外的事实 MUST NOT 通过临时新造类型表达。`model/retry` 自 M4 起可达；`tool/cancelled` 自 M3 起可达。

#### Scenario: 一次带审批的写的事件序列
- **WHEN** 一次 run 的某回合派发一次获批的 `edit`
- **THEN** 该回合里事件类型按 `tool/call`、`approval/request`、`approval/response`、`tool/result` 的顺序成组出现

#### Scenario: 无法归类的内部故障仍走 error 命名空间
- **WHEN** 内核发生一个不属于任何既有 `namespace/method` 的故障
- **THEN** 日志写入 `error/internal` 记录，而不是新造事件类型

#### Scenario: 一次重试一条 model/retry
- **WHEN** 一次请求收到 429 并被重试
- **THEN** 日志里在配对的 `model/request` 与下一条 `model/response`（或 `error/model`）之间恰好有一条 `model/retry`，payload 含 `turn_id`、`attempt`、`status`

#### Scenario: 没有重试就没有该记录
- **WHEN** 跑完一次没有 429 与 5xx 的 run
- **THEN** 日志里没有任何 `model/retry` 记录

#### Scenario: tool/cancelled 自 M3 起在词表内
- **WHEN** 一次 `bash` 超时
- **THEN** 日志里有一条 `tool/cancelled` 记录，它不被记为 `unrecognized_type`

## ADDED Requirements

### Requirement: tool/cancelled 记录被打断的工具调用
系统 SHALL 为每一个被超时或被取消打断的工具调用写恰好一条 `tool/cancelled`，payload 含 `turn_id` 与 `tool_call_id`。它 MUST NOT 携带命令输出或文件内容；是超时还是取消由配对的 `tool/result.outcome` 区分。

#### Scenario: 一次超时一条记录
- **WHEN** 一个调用因超时被打断
- **THEN** 该 `tool_call_id` 有一条 `tool/cancelled` 与一条 `outcome: TOOL_TIMEOUT` 的 `tool/result`，且 `tool/cancelled` 的 payload 里没有命令输出

#### Scenario: 没有打断就没有该记录
- **WHEN** 跑完一次既没有超时也没有取消的 run
- **THEN** 日志里没有任何 `tool/cancelled` 记录
