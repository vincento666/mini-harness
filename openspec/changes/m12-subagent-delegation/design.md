# Design

## Context

`subagent` 是工具，也是内核入口：工具层负责参数/结果词，内核负责子 `run_session`、日志、深度/容量、取消。父与子只共享工作区/围栏，不共享 approval 放行。

## Decisions

**D1 spawn，不 fork。** 子会话从空 `session/start` 开始，`task` 必须自足；不 seed 父消息。

**D2 子日志独立。** 子 session 走 `EventLog.start`；`session/start` 带 `entry=subagent`、`parent_session_id`、`depth`；父只写一对 `tool/call`/`tool/result`。

**D3 限制用结果词。** 深度 = 父 depth + 1；`depth > maxDepth` → `DEPTH_EXCEEDED`。每父会话活跃子数 ≥ `maxActiveSubagents` → `ACTIVATION_LIMIT_REACHED`。都不抛异常。

**D4 approval 一律不可用。** 子 env 注入 `UNAVAILABLE` gate；不继承父的一次性放行，也不等父代答。approval **模式**（`auto` 这个钉定）随会话继承——它是档位的一部分，不是一次放行；模式是 `ask` 时，子会话的每一次提问都得到 `UNAVAILABLE`，于是 `DENIED_BY_APPROVAL`。

**D5 并发类别 `parallel`。** 同批 `subagent` 由既有工具批调度并发；子会话内部工具并发独立。父结果按完成顺序写 `tool/result`。

**D6 取消级联。** 父段 cancel 传播到该段创建的子 session cancel；子按 ABORTED 收尾；已完成结果保留。子 session 句柄挂在父段调用上下文，不跨段复用。

**D7 Host 视图。** 会话视图加 `parent_session_id` / `depth`（根是 `null` / 0）；子会话收尾时登记进 `HostState.index`（只读一条、`GET /sessions/{id}` 回落到索引），父 SSE 不转发子流。

## Risks

- 子进程/任务泄漏：父 cancel 必须 await 子收尾；
- 容量计数并发：每父计数器在段开始时分配、结束时释放；
- 子结果太大：复用 M10 结果预算/剪枝；
- approval 提权：禁止父代答。
