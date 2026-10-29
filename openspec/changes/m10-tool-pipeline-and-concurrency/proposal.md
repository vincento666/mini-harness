# Proposal

## Why

M10 的压缩参数第一切片已经完成；余下的工具管线仍把「校验 → 围栏 → 执行」写在一个函数里，`mutating: bool` 与并发上限藏在回合循环，超大工具结果没有统一预算与 spill，`read` 没有字节上限。结果是：并发类别无法扩展、runner 不可用没有可观察的结果、单条大结果能把上下文和日志一起撑大。

这一片把工具执行收成一条**六段管线**，并把并发、结果预算与 spill 放在同一个可测试的边界里；不改变模型工具面，也不做 OS 级沙箱。

## What Changes

- **六段管线**：`pre-execute → guard → execute → post-execute → finalizeContent → tools/result`；每段失败都是结果，不抛异常打断回合。
- **CommandRunner 缝**：`win32` / `posix` 两个 adapter；注入不可用的 runner 时产出 `FenceCode.SANDBOX_UNAVAILABLE`，退出码 3。
- **并发类别**：`ToolDefinition` 带 `ConcurrencyClass = parallel | exclusive`；`parallel` ≤ 8，`exclusive` 是 barrier（之前声明的先完成、之后声明的等它完成）；`tool/call` 按声明顺序、`tool/result` 按完成顺序落盘。
- **结果预算与 spill**：`read` 加 32 KiB 字节上限（行数与字节先到者），`bash` 保留 16 KiB，`grep` / `glob` 加字节上限；超出的完整内容落 `.mini-harness/spill/`，结果里留 marker。spill 路径必须仍在工作区边界内。
- **read/edit 共用截断窗口**：CAS 与 `read` 用同一份窗口判定，避免合法编辑被误报 `STALE_EDIT`。
- **前缀复用**：一批调用只读一次日志前缀；不把 `read_events` 散到每个工具。
- **明确不做**：OS 级沙箱 / 进程收容（M15a）、单条结果剪枝（M14b）、跨会话缓存、每工具可配并发数、通用 DAG 调度、PTC 工具面塌缩、spill GC。

## Capabilities

### New Capabilities

- `tool-pipeline`：六段派发、CommandRunner 缝、并发类别与 barrier、结果预算与 spill、一批共享前缀。它描述工具执行的**可观察行为**；模型工具面不变。

### Modified Capabilities

无。现有 `turn-loop` / `file-tools` / `bash-tool` 的约束仍然成立；本 change 是在它们上面加管线与预算，不改工具名或参数。

## Impact

- 代码：`tools/registry.py`（并发类别）、`tools/dispatch.py`（六段管线）、`tools/command_runner.py`（新 seam）、`tools/file_tools.py`（read 字节上限/spill/CAS 窗口）、`tools/bash_tools.py`（spill）、`loop/turn_loop.py`（批调度读类别、前缀复用）、`config`（若 spill 位置需设置，先固定为工作区内）。
- 测试：seam ②（管线/并发/runner）、seam ③（文件工具预算/spill/CAS）、seam ⑥（真实子进程 wall-clock 与 SANDBOX_UNAVAILABLE 退出码 3）。
- 规格：新 capability `tool-pipeline`。
- 验收：E1 量并行批次 wall-clock、最大并发数；真实端点一次；UAT（人跑）一张压力工作区表；变异一轮；Learning Gate。
