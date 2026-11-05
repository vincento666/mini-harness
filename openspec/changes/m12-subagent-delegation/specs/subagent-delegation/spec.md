# Spec Delta

## ADDED Requirements

### Requirement: subagent 是 spawn 工具

系统 SHALL 提供 `subagent` 工具，参数至少 `task`（非空、自足提示词）、可选 `max_turns` / `tools` / `sandbox`。它 SHALL 创建一个独立子会话；MUST NOT 把父会话历史作为 seed（fork 不做）。结果 SHALL 是子会话最终文本（可含产物路径），MUST NOT 是子日志或完整过程。

#### Scenario: 子会话独立起步

- **WHEN** 父段调用 `subagent(task="读 a.md 并总结")`
- **THEN** 子会话从空对话开始，有自己的 `session/start` 与日志

### Requirement: 父子日志只通过 tool 结果相连

父日志 SHALL 只有该调用的 `tool/call` 与 `tool/result`；MUST NOT 写入子会话的 `model/*`、`tool/*` 或 delta。子 `session/start` SHALL 带 `entry=subagent`、`parent_session_id`、`depth`；父结果 SHALL 能通过 `tool_call_id` 与子会话对上。

#### Scenario: 父日志没有子过程

- **WHEN** 子会话内部调用了两次工具并产生两条 `model/response`
- **THEN** 父日志仍只有一条 `subagent` 的 `tool/call` 和一条 `tool/result`

### Requirement: 深度与容量是结果词

`maxDepth` 默认 1（0 禁止委派）；`maxActiveSubagents` 默认每父会话 8。超限 SHALL 返回 `DEPTH_EXCEEDED` / `ACTIVATION_LIMIT_REACHED`，作为 `tool/result` 的结果，MUST NOT 抛异常打断父回合。

#### Scenario: 深度超限

- **WHEN** 子会话在 `maxDepth=1` 下再调 `subagent`
- **THEN** 结果是 `DEPTH_EXCEEDED`，父回合继续

### Requirement: 子会话不继承 approval 放行

子会话 SHALL 继承档位/边界；approval 问人时 MUST 返回 `UNAVAILABLE`，MUST NOT 由父代答或自动放行。结果词为 `DENIED_BY_APPROVAL` 或现有审批结果。

#### Scenario: 子会话问人不可用

- **WHEN** 子会话的工具需要 approval
- **THEN** 门返回 `UNAVAILABLE`，不阻塞等待父

### Requirement: subagent 同批真并发

`subagent` SHALL 标为 `parallel` 类别；同一批多个调用 SHALL 并发执行，结果按完成顺序落盘。子会话内部仍受自己的工具并发与 `max_turns` 约束。

#### Scenario: 两个子代理并发

- **WHEN** 同一批声明两个 `subagent`
- **THEN** 两者并行，wall-clock 小于串行基线；父日志两条结果

### Requirement: 取消传播到子会话

父段取消 SHALL 传播到该段派生且仍在跑的子会话；子会话 SHALL 按 ABORTED 收尾，已完成结果保留。父 MUST NOT 留下孤儿任务。

#### Scenario: 父取消子收尾

- **WHEN** 父段在子代理运行中取消
- **THEN** 子日志有 ABORTED 收尾，父取消照常返回

### Requirement: Host 视图带父子字段

Host 的 `GET /sessions` / `GET /sessions/{id}` 视图 SHALL 带 `parent_session_id`（根为空/null）与 `depth`；MUST NOT 转发子事件到父 SSE 流。
