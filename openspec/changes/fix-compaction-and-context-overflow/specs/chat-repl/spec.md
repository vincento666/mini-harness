# Spec Delta

## ADDED Requirements

### Requirement: 段不以正常回复收尾时 stderr 看得见一行
当一个段以 `PROVIDER_ERROR`、`CONTEXT_WINDOW_EXCEEDED` 或 `MAX_TURNS` 收尾时，系统 SHALL 往 stderr 打印一行说明，含该段的停止理由与造成它的失败结果的 `code`（没有失败结果时只有停止理由）。stdout 的投影规则 MUST NOT 因此改变，这一行 MUST NOT 写进事件日志。段以 `MODEL_COMPLETED` 或 `ABORTED` 收尾时 MUST NOT 打印这一行。

#### Scenario: provider 失败的段在屏幕上有一行
- **WHEN** 一次 chat 的某段以 `error/model`（`code: PROVIDER_HTTP_STATUS`）收尾
- **THEN** stderr 里有一行含 `PROVIDER_ERROR` 与 `PROVIDER_HTTP_STATUS`，stdout 里没有出现这一行，日志里也没有

#### Scenario: 溢出的段在屏幕上有一行
- **WHEN** 一次 chat 的某段以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** stderr 里有一行含 `CONTEXT_WINDOW_EXCEEDED`，且会话继续接受下一条输入

#### Scenario: 用完回合数的段在屏幕上有一行
- **WHEN** 一次 chat 的某段用完 `--max-turns` 并以 `MAX_TURNS` 收尾
- **THEN** stderr 里有一行含 `MAX_TURNS`，会话继续接受下一条输入

#### Scenario: 正常收尾不打扰
- **WHEN** 一次 chat 的段以 `MODEL_COMPLETED` 收尾、另一段被人取消
- **THEN** stderr 里没有这一行
