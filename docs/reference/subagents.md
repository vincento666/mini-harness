# 子代理与并发（M12 底稿）

**定位**：M12 开工前的设计底稿，不是规格。DSH 的事实来自 `docs/dsh-reference/DSH运行时设计说明.html` 的委派章节（`maxDepth` / `maxActiveSubagents` / spawn vs fork）与 `d07` / `d08` 图。

## 1. DSH 的形状

- **两种后端**：`spawn`（空对话起步，提示词必须自足）与 `fork`（把父会话截至最后一个 `turn/end` 的已完成轮次作为 seed；KV cache 复用是硬约束）。mini 只做 spawn，fork 暂不做（ADR-0035）。
- **深度**：`depth = 父 + 1` 写进子级 header；`maxDepth` 默认 **1**，0 禁止委派。
- **并发**：第 9 个可续接子级撞 `maxActiveSubagents = 8`；容量耗尽报 `ACTIVATION_LIMIT_REACHED` / `subagent/delivery-unavailable`。
- **权限**：子级继承对话与 cwd，**不继承权限与工具作用域**；子级仍共享同一套围栏档位；approval 的 `never` 钉定会继承，但「放行」不继承（子代理问人只能得到不可用）。
- **父日志**：父会话只看到 `tool/call` + `tool/result`（子任务的最终结果），看不到子会话的 `model/*` 与工具过程——这正是省上下文的地方。

## 2. mini 的 M12 形状

**工具**：`subagent`（spawn）。参数至少：`task`（自足的提示词）、可选的 `max_turns` / `tools` / `sandbox`；返回子会话的最终结果（一段文本 + 可选的产物路径），不是子会话的完整日志。

**限制**：

| 限制 | 默认 | 超限结果 |
|---|---|---|
| 每个父会话同时活着的子代理 | 8（`maxActiveSubagents`） | `ACTIVATION_LIMIT_REACHED`（结果词） |
| 深度 | 1（`maxDepth`；0 禁止委派） | `DEPTH_EXCEEDED`（结果词） |
| 单个子代理的回合数 | 继承 `max_turns` 或参数 | `MAX_TURNS` |
| 子代理的审批 | 一律 `UNAVAILABLE` | `DENIED_BY_APPROVAL` |

**并发（重点）**：

- `subagent` 是 `parallel` 并发类别：同一批里声明多个 `subagent` 时**真并发**跑，结果按完成顺序落盘。
- 子会话内部仍有自己的 8 个工具并发上限与 `max_turns`；子会话之间不共享工具槽。
- 父会话的上下文只增长「每个子任务一条结果」，不随子任务内部回合数增长；这是省上下文的核心。
- host 的 `GET /sessions` 要能看出 `parent_session_id` / `depth`；UI 可以画任务树。子会话的事件流各自独立，父流不转发子流。
- 取消父段的 `subagent` 调用：取消传播到子会话（子会话写 `ABORTED`）；已完成的子结果保留。父会话取消是否级联取消所有子会话，M12 design 定。

**日志**：子会话有独立 `session/start`（`entry=subagent`、`parent_session_id`、`depth`）与独立日志；父日志只有 `tool/call` + `tool/result`。子会话的 `session/end` 要能对上父的 `tool/result`。

**资源**：H1 的 `max_sessions`（默认 4）与 M12 的 `maxActiveSubagents`（默认 8）要有明确关系——建议「根会话 4；每个根会话最多 8 个活子代理；总进程/任务上限另算」，不要让 4 把 8 无声压死。M12 design 写死。

## 3. 完成判据

- **seam ⑦**：子代理写自己的日志；子代理问人得到 `APPROVAL_UNAVAILABLE`；深度超限与容量耗尽都是结果词。
- 同一批两个 `subagent` 真并发：wall-clock 小于串行基线（E1 记录）；父日志只有两条 `tool/result`。
- 父子日志能按 `parent_session_id` / `tool_call_id` 对上；`replay` 两边都逐点相等。
- 取消父段时子会话收尾正确，没有孤儿任务。

## 4. 与其它里程碑的关系

- **H1**：host 的会话注册表要能容纳子会话；`GET /sessions` 加父子字段；`DELETE` / cancel 的级联语义在 M12 定。
- **H2**：子会话也可以流式；父 UI 可以订阅子会话的 `model/delta`，但父日志不记录它们。
- **M10**：`subagent` 的并发类别与工具并发上限在同一套调度里；子会话内部的工具并发独立。
- **M13**：目标轮次（goal）与子代理是两件事；goal 可以驱动一个子代理，但 M12 不依赖 M13。
- **MEM1**：子会话是否继承父的记忆？建议继承（同一工作区/用户），但 M12 design 要写清楚。

## 5. 开放问题

- `maxActiveSubagents` 是每父会话还是全局？DSH 的 8 是「可续接子级」的上限；mini 先按每父会话 8，全局另设硬上限。
- 子会话的 `max_turns` 默认继承还是独立？先独立默认 8，参数可覆盖。
- 父取消是否级联取消所有子会话？先「取消当前段 → 取消该段派生的子会话」，已完成结果保留。
- 子会话的 approval 一律 `UNAVAILABLE`，还是允许父会话代答？先一律不可用；父代答是提权通道，不做。
