# Spec Delta

## ADDED Requirements

### Requirement: 未配对的工具调用由折叠派生闭合
当折叠遇到一条没有配对 `tool/result` 的 `tool/call` 时，系统 SHALL 在折叠结果里为该调用派生一条 `role` 为 `tool`、`content` 为 `TOOL_OUTCOME_UNKNOWN` 的工具结果消息，使每个 assistant 工具请求消息都有配平的工具结果消息。该派生 MUST NOT 写入日志、MUST NOT 新造事件类型、MUST NOT 触发对该调用的自动重试，且 MUST 是确定性的。

#### Scenario: 半截日志折叠补出闭合
- **WHEN** 一份日志以「有 `tool/call` 没 `tool/result`」结尾
- **THEN** 折叠结果里该 `tool_call_id` 有一条 `role` 为 `tool`、`content` 为 `TOOL_OUTCOME_UNKNOWN` 的消息，且该日志文件的字节数与内容都不变

#### Scenario: 闭合不被重放成事件
- **WHEN** 对同一份半截日志连续执行两次 `minihns replay`
- **THEN** 日志里没有任何新记录，也没有任何类型为 `TOOL_OUTCOME_UNKNOWN` 的事件

#### Scenario: 完整日志不派生闭合
- **WHEN** 对一次正常收尾的 run 的日志折叠
- **THEN** 折叠结果里没有任何 `TOOL_OUTCOME_UNKNOWN` 消息

#### Scenario: 派生闭合是确定性的
- **WHEN** 对同一份半截日志连续折叠两次
- **THEN** 两次折叠结果的消息序列与头部指纹完全相等

#### Scenario: 闭合不改变已有消息的顺序
- **WHEN** 一份日志里未配对的调用之前已有若干条对话消息
- **THEN** 派生出的工具结果消息出现在该调用的 assistant 请求消息之后、该点之后的既有消息之前
