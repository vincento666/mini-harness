# M10 工具管线变异测试

**日期**：2026-10-29。每个变异改源码、跑指定判据、记录红，再用 `git checkout -- <file>` 还原。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | 改动不再 barrier | `turn_loop.py` 的 `exclusive.append(...)` 改成 `append(False)` | `test_exclusive_is_a_barrier` | 红：第三个 read 在 write 结束前开始 |
| M2 | spill 越出工作区 | `bash_tools.py` 的 spill 路径改成 `workspace.parent / ...` | `test_oversized_output_is_truncated_and_marked` | 红：spill 不在工作区，`relative_to` 抛 `ValueError` |
| M3 | read/edit 窗口不一致 | `file_tools.py` 的 edit CAS 比较串把 `line truncated` 改成 `line trunc` | `test_edit_in_a_truncated_read_window_is_not_stale` | 红：合法编辑被误报 `STALE_EDIT` |

**结论**：3 个有效变异全部被杀死；还原后回到基线。
