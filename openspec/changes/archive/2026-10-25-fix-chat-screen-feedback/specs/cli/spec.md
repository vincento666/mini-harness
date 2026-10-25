## ADDED Requirements

### Requirement: 非零退出在 stderr 说清楚
一次性入口（`minihns run` 与 `minihns serve --http`）以非 0 退出时，系统 SHALL 往 stderr 打印一行，含造成这次退出的失败码。当该失败结果带非空 `detail` 时那一行 SHALL 含那句 `detail`；当 `detail` 为空时那一行 MUST NOT 以冒号结尾、MUST NOT 带空说明（只有失败码本身）。这一行 MUST NOT 写进事件日志，也 MUST NOT 出现在 stdout。`minihns chat` 的段级收尾不适用这一条（会话收尾退出码是 0，见 `chat-repl`）。

#### Scenario: 取消收尾的 serve 那一行不是悬空冒号
- **WHEN** `minihns serve --http` 的会话进行中收到取消信号，进程以退出码 5 结束
- **THEN** stderr 里有一行含 `ABORTED`，该行不以冒号结尾，日志以 `error/abort` 收尾

#### Scenario: 有 detail 时带上那句说明
- **WHEN** `minihns run` 以 `stop_reason: CONTEXT_WINDOW_EXCEEDED` 结束、造成它的失败结果带着「无可遮蔽的内容，预算读数 <n> 已超过触发线 <m>」
- **THEN** stderr 那一行含 `CONTEXT_WINDOW_EXCEEDED` 与那句非空 `detail`，退出码为 4

#### Scenario: 那一行不是日志的投影
- **WHEN** 一次性入口以非 0 退出
- **THEN** stdout 上没有那一行，该会话的日志里也没有为打印它而存在的记录
