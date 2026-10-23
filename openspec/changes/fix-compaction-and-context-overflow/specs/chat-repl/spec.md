# Spec Delta

## ADDED Requirements

### Requirement: 段不以正常回复收尾时 stderr 看得见一行
当一个段**不以** `MODEL_COMPLETED` 或 `ABORTED` 收尾时（`PROVIDER_ERROR`、`CONTEXT_WINDOW_EXCEEDED`、`MAX_TURNS`、`FENCE_DENIED` 都在其中），系统 SHALL 往 stderr 打印一行说明，含该段的停止理由与造成它的失败结果的 `code`（没有失败结果时只有停止理由）。stdout 的投影规则 MUST NOT 因此改变，这一行 MUST NOT 写进事件日志。段以 `MODEL_COMPLETED` 或 `ABORTED` 收尾时 MUST NOT 打印这一行。

#### Scenario: provider 失败的段在屏幕上有一行
- **WHEN** 一次 chat 的某段以 `error/model`（`code: PROVIDER_HTTP_STATUS`）收尾
- **THEN** stderr 里有一行含 `PROVIDER_ERROR` 与 `PROVIDER_HTTP_STATUS`，stdout 里没有出现这一行，日志里也没有

#### Scenario: 溢出的段在屏幕上有一行
- **WHEN** 一次 chat 的某段以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** stderr 里有一行含 `CONTEXT_WINDOW_EXCEEDED`，且会话继续接受下一条输入

#### Scenario: 用完回合数的段在屏幕上有一行
- **WHEN** 一次 chat 的某段用完 `--max-turns` 并以 `MAX_TURNS` 收尾
- **THEN** stderr 里有一行含 `MAX_TURNS`，会话继续接受下一条输入

#### Scenario: 围栏拒绝收尾的段在屏幕上有一行
- **WHEN** 一次 chat 的某段以 `FENCE_DENIED` 收尾（stdin 不是终端，审批问不到人）
- **THEN** stderr 里有一行含 `FENCE_DENIED` 与造成它的失败结果的 `code`，stdout 里没有出现这一行，日志里也没有，会话继续接受下一条输入

#### Scenario: 正常收尾不打扰
- **WHEN** 一次 chat 的段以 `MODEL_COMPLETED` 收尾、另一段被人取消
- **THEN** stderr 里没有这一行

### Requirement: 压缩与遮蔽在屏幕上看得见
当一个段里写出了 `compaction/summary` 时，系统 SHALL 往 stderr 打印一行遮蔽反馈，含该条记录的 `shadowed_range`（起点与终点的 `seq`）、`tokens_before` 与 `tokens_after`。这一行 MUST NOT 出现在 stdout，也 MUST NOT 写进事件日志。段里没有压缩时 MUST NOT 打印这一行。同一条 `compaction/summary` MUST NOT 被打印第二次：每个段只报该段里新写出的那些记录。

#### Scenario: 压缩发生的那一段有一行遮蔽反馈
- **WHEN** 一次 chat 的某段里写出了一条 `compaction/summary`
- **THEN** stderr 里有一行含该条记录的 `shadowed_range` 起点与终点、`tokens_before` 与 `tokens_after`

#### Scenario: 同一条压缩记录只报一次
- **WHEN** 一次 chat 有两条输入开两个段，压缩只发生在第一个段里
- **THEN** 那条记录的遮蔽反馈在 stderr 里恰出现一次

#### Scenario: 没有压缩就没有遮蔽反馈
- **WHEN** 一次 chat 的段跑完且日志里没有 `compaction/summary`
- **THEN** stderr 里没有遮蔽反馈那一行

#### Scenario: 遮蔽反馈不是日志的投影
- **WHEN** 一次 chat 的某段发生了压缩
- **THEN** stdout 里没有那一行，事件日志里也没有；`minihns replay` 对同一份日志的输出不因这一行改变
