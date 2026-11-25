## MODIFIED Requirements

### Requirement: serve 的会话收尾就是进程退出

系统 SHALL 在会话收尾时结束 serve 进程：`session/end` 写完之后进程结束，退出码 SHALL 取自固定表（正常收尾 0、provider 失败 1、围栏拒绝 3、预算溢出 4、取消 5）。serve 是一次性入口：会话里可以有多个段（目标续跑时每轮一段），但 MUST NOT 出现「段级收尾而成进程空转等人」或「会话收尾之后进程继续」的形状。stdout SHALL 只打 session id 一行。

#### Scenario: 溢出在 serve 里就是进程退出

- **WHEN** 一次 serve 会话以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 日志里有 `error/context`、`turn/end`、`segment/end` 与 `session/end`，进程退出码为 4

#### Scenario: 取消在 serve 里就是进程退出

- **WHEN** serve 进程在会话进行中收到 Ctrl-C
- **THEN** 日志以 `error/abort`、`turn/end`（`stop_reason: ABORTED`）、`segment/end` 与 `session/end` 收尾，退出码为 5，且没有未捕获异常

#### Scenario: 目标续跑不改变进程生命周期

- **WHEN** 一次 serve 会话里的目标续了两轮
- **THEN** 日志里有三个段，`session/end` 只在最后一个段之后出现一次，进程在它写完即退出
