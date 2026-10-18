# Proposal

## Why

M2 有五个文件工具，但派发是逐个串行的、没有任何超时；M4 之后模型真的会一次返回多个工具调用（真实 smoke 里第一个回合就发了两个并行 `read`），harness 却把它们排成队。M3 补上六个工具里缺的最后一个 `bash`，并让派发段第一次可被打断——超时与取消必须在这里有确定的日志形状，否则不变量 B「失败也是结果」在第一个能跑 30 秒的工具面前不成立：`dispatch_tool_call` 现在只 `except OSError`，而 `asyncio.TimeoutError` 不是 `OSError` 子类、`CancelledError` 是 `BaseException`。

## What Changes

- 新增 `bash` 工具：cwd 固定为工作区根，默认超时 30 s、上限 600 s（决策 15），输出有上限并标记截断。
- 同一回合内的派发不再串行：只读工具（`read` / `glob` / `grep`）并发、上限 8；会改动的工具（`write` / `edit` / `bash`）串行（决策 14）。
- **超时写 `tool/cancelled` 且回合继续**；**Ctrl-C 取消整个 session**：被打断的那个调用写 `tool/cancelled`，随后 `error/abort` + `turn/end(ABORTED)` + 退出码 5。**BREAKING**：决策 15 的「Ctrl-C 并继续回合」作废，见 `docs/adr/0007-ctrl-c-cancels-the-session.md`。
- 事件词表加 `tool/cancelled`；工具结果词表加 `TOOL_TIMEOUT` 与 `TOOL_CANCELLED`。
- 平台差异第一次成为规格对象：路径规范化与大小写敏感性、tty 检测、进程树终止、Ctrl-C 接线。同一套判据在 Windows 与 Linux 各跑一遍。
- 门禁由 CI 跑：Windows + Linux 矩阵，不持 API key（ADR-0005 第 3 条），真实 Provider 的 smoke 走人手验收。
- 模型调用超时从实现的 30 s 改回决策 15 锁定的 120 s，并把数值写进 provider 规格。

**M3 明确不做**：窗口预算与 `CONTEXT_WINDOW_EXCEEDED`（M5）、OS 级沙箱与提权、流式与「一个回合多次模型请求」、`--bash-timeout` 这类没被要求过的可配置性、REPL 里「打断但不退出」（M6）、`_replay` 的扫描逻辑下沉（ADR-0002 第 3 条，改判推到 M6）。

## Capabilities

### New Capabilities

- `bash-tool`：shell 命令工具的执行契约——命令形状、cwd、超时与输出上限、命令退出码到结果词的映射、超时之后进程树怎么收。

### Modified Capabilities

- `turn-loop`：派发段的并发调度（只读并发上限 8、会改动的串行、落盘顺序确定、同一批次共享同一份日志前缀）；超时与取消作为结果词；MODIFIED「用户取消是 ABORTED 结果」按 ADR-0007 的形状。
- `event-log`：MODIFIED「事件类型只取自当前事件词表」，把 `tool/cancelled` 收进词表。
- `fences`：MODIFIED「工作区边界只约束会改动的操作」与「read-only 档位拒绝一切会改动的工具」，写明 bash 只受档位轴约束（ADR-0008）；MODIFIED「围栏拒绝是终止结果」在并发批次里的含义。
- `provider`：模型调用超时数值进规格。

## Impact

`src/mini_harness/`：`tools/`（新 `bash_tools.py`、`dispatch.py` 的执行段与 `DispatchOutcome`、`registry.py` 的 `ToolOutcome`）、`loop/turn_loop.py`（派发段调度）、`events/vocabulary.py`、`provider/openai_compat.py`（超时数值）、`cli/main.py`（信号接线）。`tests/`：seam ①②③⑥ 各加判据；`tests/tool_harness.py` 的 helper 必须收 `registry` / `gate`（ADR-0002 第 1 条剩的一半与第 12、16 条的兑现——这是判据①的前置，不是可选项）。CI：新 `.github/workflows/`。无新依赖（`asyncio` 与 `subprocess` 是标准库）。

判据「两端全绿、门禁由 CI 跑」有一半是人要做的动作：`origin/main` 落后 52 个提交，要先推送并选 runner。覆盖率地板 95% 与实测 96% 只剩 1 个点余量，而平台分支在两个 runner 上各覆盖不到另一半——地板策略要在 design 里定。
