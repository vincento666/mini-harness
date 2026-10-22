## MODIFIED Requirements

### Requirement: 事件类型只取自当前事件词表
系统 SHALL 只发出当前词表中的事件类型：`session/start`、`session/end`、`segment/start`、`segment/end`、`turn/start`、`turn/end`、`context/assembled`、`model/request`、`model/retry`、`model/response`、`user/message`、`tool/call`、`tool/result`、`tool/cancelled`、`approval/request`、`approval/response`、`compaction/summary`、`error/*`。`error/*` 用到的具体类型是 `error/model`、`error/internal`、`error/abort`、`error/fence`、`error/context`。词表外的事实 MUST NOT 通过临时新造类型表达。`model/retry` 自 M4 起可达；`tool/cancelled` 自 M3 起可达；`compaction/summary` 与 `error/context` 自 M5 起可达；`segment/start`、`segment/end` 与 `user/message` 自 M6 起可达——前两个在 `run` 与 `chat` 两种入口下都产生，`user/message` 只在 `entry` 为 `chat` 的会话里产生。

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

#### Scenario: 一次 REPL 输入一条 user/message
- **WHEN** 一次 chat 里人提交一条非空输入
- **THEN** 日志里恰有一条 `user/message`，payload 含 `segment_id` 与 `content`，它不被记为 `unrecognized_type`

#### Scenario: 段的边界不被记为 unrecognized_type
- **WHEN** 跑完一次 `minihns run`
- **THEN** 日志里恰有一条 `segment/start` 与一条 `segment/end`，两者都不被记为 `unrecognized_type`

#### Scenario: 一次性 run 不产生 user/message
- **WHEN** 跑完一次 `minihns run`
- **THEN** 日志里没有任何 `user/message` 记录
