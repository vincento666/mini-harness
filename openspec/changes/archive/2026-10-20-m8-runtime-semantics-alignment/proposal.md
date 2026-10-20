# Proposal

## Why

M3 收尾时留下的两处形状与 DSH 相反：取消是「掀翻整个会话」的终止事件，工具结果缓冲到批次结束才落盘。后者是 `docs/CURRENT.md` 里唯一带「缺口」标签、没有判据的一条——硬杀落在批次中间会留下「有 `tool/call` 没 `tool/result`」的半截前缀。M5 的压缩判据（「原文事件仍在日志里」+ replay 逐点相等）与 M11 的 resume 都建在「日志前缀在任何时刻都是完整事实」之上，所以这两处要在 M5 之前改掉。方向已由 ADR-0011 / ADR-0012 裁决：以 DSH 为真理转向。

## What Changes

- **BREAKING** 取消不再掀翻批次。取消置位时，已派发的调用照常被打断并落结果（`TOOL_CANCELLED`）；**未派发的每一个声明调用也写一条 `tool/call` 与配对的 `tool/result`（`outcome: ABORTED_BEFORE_DISPATCH`）**。既有判据「未派发的调用不出现在日志里」被推翻。
- **BREAKING** `tool/result` 在产生时落盘。落盘顺序从「模型声明顺序」变成「实际完成顺序」。Requirement「工具调用与结果按声明顺序落盘」与它的判据被推翻；并发只读的结果顺序判据改成按集合断言。
- 新增两个工具结果词：`ABORTED_BEFORE_DISPATCH`（派发前被取消）与 `TOOL_OUTCOME_UNKNOWN`（读方闭合）。每个配一条「可达」判据。
- 读方闭合：折叠遇到未配对的 `tool/call` 时派生一条 `TOOL_OUTCOME_UNKNOWN` 的工具结果消息并闭合该回合。**不落盘、不新增事件类型、MUST NOT 自动重试。**
- 取消的语义从「会话终止」改成「回合终止」：内核停止当前回合并返回 `ABORTED`，**会话是否结束由入口决定**。一次性 `minihns run` 仍以退出码 5 结束，这条不变。

**M8 明确不做**：派生信号换入工具体与工具管线加段（M10）、`CommandRunner` 缝与 `SANDBOX_UNAVAILABLE`（M10）、`--resume` 与折叠缓存（M11）、REPL / SSE 里的会话续跑（M6 / M7）、OS 级拦截（M15）、把 `TOOL_CANCELLED` 改名成 DSH 的 `ABORTED`（用 `GLOSSARY.md` 的术语对齐代替改名）。

## Capabilities

### New Capabilities

- 无。三处改动都落在既有能力上，不新开能力。

### Modified Capabilities

- `turn-loop`：取消 Requirement 改成回合级协作式；落盘顺序 Requirement 改成完成顺序；工具结果词表加 `ABORTED_BEFORE_DISPATCH` 与 `TOOL_OUTCOME_UNKNOWN`。
- `event-log`：`tool/cancelled` 只覆盖**被打断**的调用（未派发的不算被打断）；并发批次场景里「`tool/result` 按声明顺序」改成按完成顺序。
- `context-projection`：新增「未配对的 `tool/call` 由折叠派生闭合」Requirement，并保住折叠的确定性（同一日志两次折叠仍逐字段相等）。

## Impact

- **代码**：`loop/turn_loop.py`（`_dispatch_batch` 的取消分支与落盘时机）、`events/fold.py`（读方闭合）、`tools/registry.py`（`ToolOutcome` 两个新值）、`cli/main.py`（入口决定会话终止，退出码 5 不变）。
- **测试**：seam ① 的取消与落盘顺序判据重写；seam ④ 新增「构造一份半截日志喂折叠」的闭合判据；seam ⑥ 新增一条真硬杀判据（Linux `SIGKILL` 可靠，Windows 用 `Popen.kill()`）；M3 变异记录里守落盘顺序的那条要跟着重写。
- **规格与账本**：三条主规格 Requirement 改写、一条新增；`docs/adr/0002` 第 10 条作废（已标被取代）；`docs/verification/m3-…-mutation.md` 加一条「该变异在 M8 后不再适用」的注记。
- **不变量**：A（只追加不改写）不变——闭合是读方派生；B（失败也是结果）扩展成「没开始也是结果」。
