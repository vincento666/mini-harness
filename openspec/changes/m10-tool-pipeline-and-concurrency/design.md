# Design

## Context

当前工具派发在 `tools/dispatch.py::dispatch_tool_call`：校验 → `judge_fence` → approval → `definition.run` → 结果。并发在 `turn_loop._dispatch_batch`：用「链 + 信号量 + 独占锁」实现「只读并发、改动串行」；`ToolDefinition.mutates: bool`。结果没有统一预算；`read` 只限行数；`bash` 在工具内部截 16 KB；`grep`/`glob` 只有条数上限。

本 change 把「一次调用」扩成六段管线，并把并发类别、命令 runner、结果预算/spill 放到可测试边界。压缩参数第一切片已完成，不重复做。

## Goals / Non-Goals

**Goals:**

- 一次调用六段可观察，失败是结果。
- `CommandRunner` 可注入；不可用时 `SANDBOX_UNAVAILABLE` / 退出码 3。
- `ConcurrencyClass` 替代 `mutates`；`parallel ≤ 8`，`exclusive` barrier。
- 结果预算 + spill；`read` 32 KiB 字节上限；`bash` 16 KiB；`grep`/`glob` 字节上限。
- `read`/`edit` 共用截断窗口；批内前缀只读一次。

**Non-Goals:**

- OS 级沙箱 / 进程收容（M15a）；单条结果剪枝（M14b）；spill GC；跨会话缓存；每工具并发数；DAG 调度；PTC；工具名/参数变化。

## Decisions

**D1 六段是派发内部的显式函数，不是插件框架。** 形如：

```python
pre_execute(call, definition)      # 名字/参数/能力预检
guard(args, definition, context)   # 现有 judge_fence + approval
execute(definition, args, context) # runner/工具执行
post_execute(result, context)      # outcome 归一
finalize_content(result, budget)   # 截断 + spill
emit_result(result)                # 写 tool/result
```

每段返回 `DispatchOutcome` 或继续；不在本 change 做可注册 stage/hook 表（那是插件容器，ADR-0035 暂不做）。这样判据能逐段注入失败，而不是只能黑盒。

**D2 `ConcurrencyClass` 是 `ToolDefinition` 的属性；`mutates` 保留为派生 bool。** 现有围栏/审批仍读 `mutates`；调度改读 `concurrency`。映射：`read/glob/grep = parallel`；`write/edit/bash = exclusive`。这样围栏语义不变，调度类别可扩展。

**D3 `CommandRunner` 是 `bash` 的构造依赖，不是全局单例。** 接口 `run(command, cwd, timeout) -> CommandResult`；win32/posix adapter 各自处理 shell 与进程树。runner 构造失败或 `SANDBOX_UNAVAILABLE` 由 bash 工具返回 `FenceCode` 结果；不静默 fallback 到 `subprocess`。具体 adapter 在后续实现任务里落。

**D4 结果预算集中在 `finalize_content`。** `read` 的字节上限在工具内部先算「行窗口 ∩ 字节窗口」，把被截断前缀交给 spill；`finalize_content` 只负责最终结果字符串的硬上限与 marker，避免每个工具各写一套截断。预算常量放 `tools/budgets.py`（或等价模块），不先做配置。

**D5 spill 位置固定在工作区 `.mini-harness/spill/`。** 按 `session_id` + `tool_call_id` 命名；路径必须经工作区边界解析。M10 不做 GC；M11 再回收。spill 文件本身不进日志，只在 `tool/result.content` 留 marker + 路径。

**D6 截断窗口抽成 `read_window` 函数，read/edit 共用。** 当前 `_numbered_window` 只做行窗口；新增字节上限后，`read` 返回截断窗口，`edit` 的 CAS 用同一函数算「模型实际看到的窗口」。这是本 change 最容易回归处，单独红绿切片。

**D7 并发实现保留「链 + 信号量 + 独占锁」，只换类别。** 现有 `_dispatch_batch` 已满足 barrier 与结果顺序；不重写成 DAG。类别映射与 `max_parallel` 常量保持 8。E1 量到长批次损失再讨论调度器。

## Risks / Trade-offs

- **截断与 CAS 错位** → `read`/`edit` 共用 `read_window`；判据先红在「截断后合法 edit 被拒」。
- **spill 越界** → 路径统一经工作区解析；越界是围栏结果，不是写文件。
- **并行结果顺序** → `tool/call` 声明顺序与 `tool/result` 完成顺序分开判；barrier 判据用真实 delay。
- **runner adapter 平台差异** → 先桩测不可用与选择，真进程只测 wall-clock/退出码；不承诺 OS 级隔离。
- **日志前缀复用** → 批内一次 `read_events`，每个工具拿到同一份 `DispatchContext`；不在每个工具内部重读。
- **预算常量硬编码** → 与 DSH 对齐的 32 KiB / 16 KiB 先写死；E1 量到误伤再配置化，不先加开关。

## Migration Plan

1. `ConcurrencyClass` 与 runner 接口先落，保留旧 `mutates` 语义。
2. 六段管线抽函数，现有 `dispatch_tool_call` 行为逐点不变。
3. `finalize_content` + spill + read 字节上限；read/edit 共用窗口。
4. 批调度改读 `concurrency`，验证 barrier 与结果顺序。
5. 门禁、真实端点、UAT、变异、Learning Gate。

## Open Questions

- spill 是按 `session_id` 还是 `tool_call_id` 分目录？先按 `session_id/tool_call_id`，M11 再谈回收。
- `grep`/`glob` 的字节上限具体值？先按 32 KiB，与 read 一致；E1 量到导航误伤再调。
- 六段是否需要一个 `stage` 枚举暴露给日志？先不新增事件类型；段内 inject 只用于测试，结果仍是 `tool/result`。
