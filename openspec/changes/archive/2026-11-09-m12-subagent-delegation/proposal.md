# Proposal

## Why

M11 之后，mini 还不会把一段可并行、可独立收尾的任务交给子会话。M12 加 `subagent` 工具（spawn 形状）：子会话有自己的日志与上下文，父会话只拿最终结果，从而不把子会话的过程塞进父上下文。

fork 暂不做（ADR-0035）。

## What Changes

- **`subagent` 工具**：参数 `task`（自足提示词）、可选 `max_turns` / `tools` / `sandbox`；返回最终文本 + 可选产物路径，不返回子日志。
- **子会话**：独立 `session/start`（`entry=subagent`、`parent_session_id`、`depth`）、独立日志、独立 env；不继承 approval 放行。
- **父日志**：只有 `tool/call` + `tool/result`；没有子会话的 `model/*`/工具过程。
- **限制**：`maxDepth` 默认 1；`maxActiveSubagents` 每父会话默认 8；超限是结果词 `DEPTH_EXCEEDED` / `ACTIVATION_LIMIT_REACHED`，不是异常。
- **并发**：`subagent` 属 `parallel`；同批多个真并发，结果按完成顺序落盘。
- **取消**：父段取消传播到该段派生的子会话；已完成结果保留。
- **Host**：`GET /sessions` 的会话视图加 `parent_session_id` / `depth`（可为空）。

## Capabilities

### New Capabilities

- `subagent-delegation`：spawn、深度/容量、子日志、并发、取消、审批不可用。

### Modified Capabilities

- `tool-pipeline`：`subagent` 的并发类别与结果词。
- `host-api`：会话视图的父子字段。

## Impact

- 代码：`tools/subagent.py`、`tools/registry.py`、`tools/dispatch.py`（每次调用带 `tool_call_id`）、`tools/fences.py`（派发上下文带会话运行时）、`loop/turn_loop.py`（`session/start` 父子字段、派发接会话、一次性会话形状）、`loop/settings.py`、`session/delegation.py`、`config/assembly.py`（内置工具表加 `subagent`）、`session/host.py`、`cli/host.py`。
- 测试：seam ⑦（父子日志配对、并发 wall-clock、取消）。
- 非目标：fork、跨进程子代理、父代答 approval。
