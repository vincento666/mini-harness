# Spec Delta

## MODIFIED Requirements

### Requirement: 事件类型只取自当前事件词表
系统 SHALL 只发出当前词表中的事件类型：`session/start`、`session/end`、`turn/start`、`turn/end`、`context/assembled`、`model/request`、`model/retry`、`model/response`、`tool/call`、`tool/result`、`tool/cancelled`、`approval/request`、`approval/response`、`compaction/summary`、`error/*`。`error/*` 用到的具体类型是 `error/model`、`error/internal`、`error/abort`、`error/fence`、`error/context`。词表外的事实 MUST NOT 通过临时新造类型表达。`model/retry` 自 M4 起可达；`tool/cancelled` 自 M3 起可达；`compaction/summary` 与 `error/context` 自 M5 起可达。

#### Scenario: 一次带审批的写的事件序列
- **WHEN** 一次 run 的某回合派发一次获批的 `edit`
- **THEN** 该 `tool_call_id` 的记录按 `tool/call`、`approval/request`、`approval/response`、`tool/result` 的相对顺序出现

#### Scenario: 并发批次里不同调用的记录可以交错
- **WHEN** 同一回合里一个只读调用与一个获批的会改动调用同批派发
- **THEN** 每个 `tool_call_id` 自己的记录保持上面那个相对顺序，`tool/result` 之间按各自的完成顺序；不同调用的组可以交错，规格不要求它们连续

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

#### Scenario: 一次压缩一条 compaction/summary
- **WHEN** 一次装配越线并完成压缩
- **THEN** 日志里恰有一条 `compaction/summary`，它不被记为 `unrecognized_type`

## ADDED Requirements

### Requirement: compaction/summary 记录一次遮蔽式压缩
系统 SHALL 为每一次压缩写恰好一条 `compaction/summary`，payload 含 `turn_id`、`shadowed_range`（对象，字段 `start` 与 `end` 是同一 session 内的 `seq`，含两端）、`summary`（摘要文本）、`tokens_before` 与 `tokens_after`（压缩前后该次装配的预算读数）。该记录 MUST NOT 携带被遮蔽记录的原文副本，也 MUST NOT 改写或删除被遮蔽的记录。

#### Scenario: 字段齐全且原文还在盘上
- **WHEN** 一次压缩落进日志
- **THEN** 那条 `compaction/summary` 的五个 payload 字段都在，且被 `shadowed_range` 覆盖的那些记录仍逐条存在于日志里、内容不变

#### Scenario: 一次装配最多一条
- **WHEN** 一次 run 里发生了两次压缩（分属两个回合）
- **THEN** 日志里恰有两条 `compaction/summary`，各自 `turn_id` 不同

### Requirement: error/context 记录预算溢出
系统 SHALL 在预算溢出终止 run 时写一条 `error/context`，payload 含 `turn_id`、`code`（取值 `CONTEXT_WINDOW_EXCEEDED`）、`detail`。该记录 MUST 在该回合的 `turn/end` 之前、该回合的 `context/assembled` 之后写入（若该点有装配记录）。

#### Scenario: error/context 的位置可断言
- **WHEN** 一次 run 以预算溢出结束
- **THEN** 日志里 `error/context` 出现在该回合的 `turn/end` 之前，且 `session/end` 的 `stop_reason` 是 `CONTEXT_WINDOW_EXCEEDED`

#### Scenario: 词表每个新值可达
- **WHEN** 跑完 M5 的 seam ① 与 seam ⑥ 判据
- **THEN** `compaction/summary`、`error/context` 与 `StopReason` 里的 `CONTEXT_WINDOW_EXCEEDED` 各至少被一条测试断言到
