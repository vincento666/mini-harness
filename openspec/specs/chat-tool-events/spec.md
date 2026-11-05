# chat-tool-events Specification

## Purpose
定义 chat 在 stderr 显示工具调用/结果事件行，以及 observer 只收新事件的约束。

## Requirements

### Requirement: chat 在 stderr 显示工具事件行

`minihns chat` SHALL 在 stderr 按发生顺序显示新增的 `tool/call`、`tool/result`、`tool/cancelled`：

- `tool/call`：`[tool] <name> <arguments JSON>`；
- `tool/result`：`[tool] <name> -> <outcome>`，可带一行内容预览；
- `tool/cancelled`：`[tool] <name> cancelled`。

这些行 MUST NOT 写进 stdout，MUST NOT 写进日志；stdout 仍只放模型正文。chat SHALL 通过 `EventLog` 的 append observer 接收新事件，MUST NOT 靠扫描旧日志补打印；observer 在 append 落账后同步触发，退订后不再收到。

#### Scenario: 工具调用与结果

- **WHEN** 一个段先 `tool/call read` 再 `tool/result OK`
- **THEN** stderr 有 `[tool] read` 与 `-> OK`，stdout 只有最终正文

#### Scenario: 只收新事件

- **WHEN** 连续两段各跑工具
- **THEN** 第二段只打印第二段 append 的事件，不重复第一段

