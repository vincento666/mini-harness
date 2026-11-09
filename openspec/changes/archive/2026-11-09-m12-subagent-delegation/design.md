# Design

## Context

`subagent` 是工具，也是内核入口：工具层负责参数/结果词，内核负责子 `run_session`、日志、深度/容量、取消。父与子只共享工作区/围栏，不共享 approval 放行。

## Decisions

**D1 spawn，不 fork。** 子会话从空 `session/start` 开始，`task` 必须自足；不 seed 父消息。

**D2 子日志独立。** 子 session 走 `EventLog.start`；`session/start` 带 `entry=subagent`、`parent_session_id`、`depth`；父只写一对 `tool/call`/`tool/result`。

**D3 限制用结果词。** 深度 = 父 depth + 1；`depth > maxDepth` → `DEPTH_EXCEEDED`。每父会话活跃子数 ≥ `maxActiveSubagents` → `ACTIVATION_LIMIT_REACHED`。都不抛异常。

**D4 approval 一律不可用。** 子 env 注入 `UNAVAILABLE` gate；不继承父的一次性放行，也不等父代答。approval **模式**（`auto` 这个钉定）随会话继承——它是档位的一部分，不是一次放行；模式是 `ask` 时，子会话的每一次提问都得到 `UNAVAILABLE`，于是 `DENIED_BY_APPROVAL`。子会话的受保护头部带一条委派声明（照 DSH `subagent:delegation`）：权限固定、被拒的操作不要重试、把限制写进回复——否则模型会像真实端点 S4 那样反复换措辞重试。

**D5 并发类别 `parallel`。** 同批 `subagent` 由既有工具批调度并发；子会话内部工具并发独立。父结果按完成顺序写 `tool/result`。

**D6 取消级联。** 父段 cancel 传播到该段创建的子 session cancel；子按 ABORTED 收尾；已完成结果保留。子 session 句柄挂在父段调用上下文，不跨段复用。

**D8 会话额度与子代理额度分开。** 根会话上限 `MAX_SESSIONS = 4` 不变；每个根会话最多 8 个活跃子代理；子会话不占根会话额度，M12 也不设全局池上限（上界 4×8=32，单进程可接受）。注意：工具并发上限也是 8，所以**同一批 9 个 `subagent` 不会撞额度**（第 9 个等前 8 个之一完成就能跑）；额度今天是防御性的，真实触发要等 M13 的目标轮次或并发上限变化，判据用预置计数。

**D9 档位只能收窄。** `subagent.sandbox` 只能比父会话窄（`read-only` < `workspace-write` < `danger-full-access`）；请求更宽是 `TOOL_ARGS_INVALID`——否则子会话会绕过服务器级的 `--allow-danger-full-access` 许可。

**D10 子会话的失败是失败。** 子会话的模型失败与内核失败以 `TOOL_IO_FAILED` 回到父（带失败码与 detail）；围栏拒绝以 `DENIED_BY_APPROVAL` / `DENIED_BY_FENCE` 回到父（带围栏码、detail 与子会话最后的文本），父自己的回合不因此终止；取消是 `TOOL_CANCELLED`；`MODEL_COMPLETED` / `MAX_TURNS` / `CONTEXT_WINDOW_EXCEEDED` 带上子会话的最终文本。

**D7 Host 视图。** 会话视图加 `parent_session_id` / `depth`（根是 `null` / 0）；子会话收尾时登记进 `HostState.index`（只读一条、`GET /sessions/{id}` 回落到索引），父 SSE 不转发子流。

## Risks

- 子进程/任务泄漏：父 cancel 必须 await 子收尾；
- 容量计数并发：每父计数器在段开始时分配、结束时释放；
- 子结果太大：复用 M10 结果预算/剪枝；
- approval 提权：禁止父代答。
