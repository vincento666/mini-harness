# Tasks

## 1. 并发类别与调度

- [x] 1.1 seam ②：红判据 `test_concurrency_class_maps_by_tool`——`read/glob/grep=parallel`、`write/edit/bash=exclusive`；实现 `ConcurrencyClass` 与 `ToolDefinition.concurrency`
- [x] 1.2 seam ②：红判据 `test_parallel_batch_runs_concurrently_with_8_cap`——4 个 0.1 s 的 parallel 调用 wall-clock 明显小于串行；同时最多 8
- [x] 1.3 seam ②：红判据 `test_exclusive_is_a_barrier`——`read → write → read` 的第一个 read 在 write 前完成，第三个在 write 后开始
- [x] 1.4 seam ②：守卫——`tool/call` 仍按声明顺序、`tool/result` 按完成顺序；现有取消/围栏行为不变

## 2. 六段管线

- [x] 2.1 seam ②：红判据 `test_dispatch_walks_six_stages_in_order`——成功调用按 `pre-execute → guard → execute → post-execute → finalizeContent` 执行；实现阶段函数（不引入插件注册表）
- [x] 2.2 seam ②：红判据 `test_execute_failure_skips_post_stage`——execute 返回 `TOOL_IO_FAILED`，post/finalize 不执行，结果仍是 `tool/result`
- [x] 2.3 seam ②：守卫——`UNKNOWN_TOOL` / `TOOL_ARGS_INVALID` / `DENIED_BY_FENCE` / `DENIED_BY_APPROVAL` 的判定与落账逐点不变

## 3. CommandRunner 与 SANDBOX_UNAVAILABLE

- [x] 3.1 seam ②：红判据 `test_bash_uses_the_injected_command_runner`——注入 spy runner，`bash` 只经它执行；实现 `CommandRunner` 缝
- [x] 3.2 seam ②：红判据 `test_an_unavailable_runner_is_sandbox_unavailable`——runner 构造/执行报不可用 → `error/fence(code: SANDBOX_UNAVAILABLE)`，退出码 3，命令未执行
- [x] 3.3 seam ②：红判据 `test_win32_and_posix_adapters_are_selected`——平台选择对应 adapter；不静默回退 subprocess
- [x] 3.4 seam ⑥：黑盒——真实子进程跑一次 runner 不可用的桩，验证退出码 3 与 `SANDBOX_UNAVAILABLE` 记录

## 4. 结果预算与 spill

- [x] 4.1 seam ③：红判据 `test_read_has_a_50_kib_window_and_no_spill`——超长单行被 2000 字符截断，总字节不超过 51200，结果带 `offset=<next>` 且没有 spill 路径
- [x] 4.2 seam ③：红判据 `test_bash_keeps_the_tail_and_spills`——16 KiB 上限、保留尾部、marker 与完整内容可从 spill 读回
- [x] 4.3 seam ③：红判据 `test_grep_and_glob_have_inline_caps`——250/100 条、2000 字符/行、20 MB raw 上限；超限有 marker 与缩小范围提示
- [x] 4.4 seam ③：红判据 `test_spill_stays_inside_the_workspace`——解析后路径仍在工作区根内；越界是围栏结果
- [x] 4.5 seam ②：守卫——`finalizeContent` 只硬截断 bash/搜索；`read` 的结果不带 spill；无超限时逐字节不变

## 5. read/edit 共用窗口

- [x] 5.1 seam ③：红判据 `test_edit_cas_uses_the_same_read_window`——超长文件 read 被行/字节/单行上限截断后，在窗口内 edit 不被误报 `STALE_EDIT`
- [x] 5.2 seam ③：守卫——窗口外 edit 仍报 `STALE_EDIT`；正常文件行为不变

## 6. 批内前缀复用

- [x] 6.1 seam ②：红判据 `test_a_batch_reads_the_log_prefix_once`——4 个调用的批只读一次日志前缀；实现批调度共享 `DispatchContext`
- [x] 6.2 seam ②：守卫——围栏「已读过」判定仍来自同一份前缀，不来自进程内第二真源

## 7. 文档与 UAT

- [x] 7.1 文档：在 `docs/reference/tool-concurrency-and-context-economy.md` 写清六段、类别、预算与 spill 位置
- [x] 7.2 UAT 骨架：`docs/verification/m10-tool-pipeline-and-concurrency-uat.md`（propose 时立；人跑）

## 8. 收尾四项

- [x] 8.1 真实端点验收：真实 deepseek 跑一次「读大文件 → 写 → 读」，记录 wall-clock、spill marker 与最终回答，写进 `docs/verification/m10-tool-pipeline-and-concurrency-real-endpoint.md`
- [ ] 8.2 UAT 验收（人跑）：按 `docs/verification/m10-tool-pipeline-and-concurrency-uat.md` 填观察表
- [x] 8.3 变异测试一轮：改坏「barrier 顺序」「spill 越界仍写」「read/edit 窗口不一致」各一处，记进 `docs/verification/m10-tool-pipeline-and-concurrency-mutation.md`
- [x] 8.4 Learning Gate：扫证据写 `docs/lessons.md` 收件箱；无可复用信号写 `NO-PROMOTION`

## Workflow follow-up

- 归档后跑 `agents-md-slim`；M10 全里程碑完成后更新 `docs/CURRENT.md` 与 roadmap。
