# M2 变异测试记录（tasks 15.1）

**基线**：分支 `change/m2-file-tools-and-fences`，commit `6e02284`，137 passed / 1 skipped，`uv run mypy --strict src` 干净，`coverage combine` 后 TOTAL 96%。
**做法**：一次只改 `src/mini_harness/` 一处实现 → 全量 `uv run pytest -q --tb=no -rf` → 记录「变异 / 改法 / 哪些测试变红」→ 先看 `git status` 再 `git checkout -- <file>` 还原 → 再跑全量确认回到基线。
**基线在轮内漂移**：M 与 N 两条存活各补了一条测试，所以后半程的「全绿」是 138 → 139 → 140 passed。下表里的计数是当次实测值。

## 变异与结果

| | 变异 | 改法 | 结果 | 判定 |
|---|---|---|---|---|
| A | 词表里加一个跑不到的取值 | `tools/registry.py`：`ToolOutcome` 的 Literal 里加 `"NOT_IMPLEMENTED"` | 2 failed：`test_the_outcome_vocabulary_has_twelve_values_and_no_not_implemented`、`test_every_tool_outcome_is_reachable` | 杀死 |
| B | 歧义目标的阈值抬高 | `tools/file_tools.py`：`matches > 1` → `matches > 2`（`EDIT_TARGET_AMBIGUOUS` 再也跑不出来） | 3 failed：`test_edit_replaces_only_the_first_match_unless_replace_all`、`test_missing_target_and_ambiguous_target_are_two_different_results`、`test_every_tool_outcome_is_reachable` | 杀死 |
| C | `read` 的默认窗口上限 | `DEFAULT_READ_LIMIT = 2000` → `100000` | 1 failed：`test_the_default_window_is_two_thousand_lines` | 杀死 |
| D | `glob` 的列表上限 | `GLOB_LIMIT = 100` → `100000` | 1 failed：`test_glob_lists_at_most_one_hundred_paths` | 杀死 |
| E | `grep` 的匹配上限 | `GREP_LIMIT = 250` → `100000` | 1 failed：`test_grep_lists_at_most_two_hundred_and_fifty_matches` | 杀死 |
| F | `grep` 的正则校验 | `GrepArgs.compile_pattern` 改成原样返回（不再 `re.compile`） | 1 failed：`test_an_invalid_pattern_is_an_argument_error` | 杀死 |
| G | 路径键的 Windows 大小写折叠 | `tools/fences.py`：删掉 `if os.name == "nt": resolved = os.path.normcase(resolved)` | 137 passed，**存活** | dud，见「dud 一节」 |
| H | 工作区边界在所有档位生效 | `judge_fence`：`if context.sandbox == "workspace-write" and not _is_inside_workspace(...)` → 去掉档位条件 | 2 failed：`test_danger_full_access_lifts_the_workspace_boundary`、`test_danger_full_access_still_requires_reading_first` | 杀死 |
| I | 档位段与边界段互换 | `judge_fence`：把边界整段挪到 `read-only` 段之前 | 140 passed，**存活** | dud，见「dud 一节」 |
| J | 校验段与围栏段互换 | `tools/dispatch.py`：`judge_fence` 加它的 `DENIED` 返回整段挪到 `model_validate` 之前 | 2 failed：`test_invalid_arguments_skip_both_the_fence_and_the_execution`、本轮新加的 `test_invalid_arguments_are_caught_before_the_fence_is_consulted` | 杀死 |
| J′ | 只把 `judge_fence` 调用提前 | 同上，但 `DENIED` 的返回仍留在校验之后 | 137 passed，**存活** | dud，见「dud 一节」 |
| K | 写前必读扩大到新文件 | `write_file`：`if target.exists() and ... not in context.reads` → 去掉 `target.exists() and` | 1 failed：`test_writing_a_new_file_creates_it_and_the_parent_dirs` | 杀死 |
| L | `replace_all` 被忽略 | `edit_file`：`if matches > 1 and not args.replace_all` → `if matches > 1` | 1 failed：`test_replace_all_replaces_every_match` | 杀死 |
| M | 后来的成功读不覆盖先前的 | `reads_from_records`：同一路径第二次成功读 `continue`（第一次读赢） | 138 passed，**存活** | 存活 → 覆盖缺口，见下节 |
| N | 一次 `write` 也算读过 | `reads_from_records`：`if name != "read"` → `if name not in {"read", "write"}` | 139 passed，**存活** | 存活 → 覆盖缺口，见下节 |
| O | 行号不跟着 `offset` | `_numbered_window`：`enumerate(window, start=offset)` → `start=1` | 1 failed：`test_offset_and_limit_select_one_line` | 杀死 |
| P | 非 0 退出的失败行写进 stdout | `cli/main.py`：`_report_failure` 的 `sys.stderr.write` → `sys.stdout.write` | 15 failed，含 `test_events_jsonl_stdout_equals_the_log_line_by_line`、`test_a_write_outside_the_workspace_ends_with_code_three`、`test_run_without_prompt_is_an_invalid_argument`、`test_replay_reports_a_mismatched_assembly_point_and_leaves_the_log_alone` | 杀死 |
| Q | `approval/*` 事件无条件写 | `loop/turn_loop.py`：`if dispatched.approval is not None:` → `if True:` | 6 failed：`test_read_like_tools_never_ask_a_human`、`test_auto_approval_writes_no_approval_records`、`test_yes_approves_every_edit_in_the_fixture_repo`、`test_a_write_with_no_human_to_ask_ends_with_code_three`、`test_yes_does_not_relax_the_read_only_level`、`test_a_fence_denial_ends_the_run_without_dispatching_the_rest` | 杀死 |
| R | CAS 比对永不触发 | `edit_file`：`if _numbered_window(body, prior.offset, prior.limit) != prior.content:` → `if False:` | 2 failed：`test_editing_a_file_changed_outside_the_session_is_stale`、`test_every_tool_outcome_is_reachable` | 杀死 |
| S | `FENCE_DENIED` 的退出码映射 | `cli/main.py`：`STOP_FENCE_DENIED: EXIT_FENCE_DENIED` → `EXIT_INTERNAL_ERROR`（3 变 1） | 6 failed：`test_a_write_outside_the_workspace_ends_with_code_three`、`test_a_write_with_no_human_to_ask_ends_with_code_three`、`test_yes_does_not_relax_the_read_only_level`、`test_no_run_exits_with_the_reserved_four`、`test_events_jsonl_stdout_equals_the_log_line_by_line`、`test_every_stop_reason_maps_to_an_exit_code` | 杀死 |

## 存活变异 M 与 N 的处理

两条都落在同一处：`reads_from_records` 从日志前缀重算「已读集合」的规则（不变量 E 的写前必读）。M 存活说明没有任何测试读同一路径两次；N 存活说明没有任何测试在 `write` 之后直接 `edit`。各补一条判据，先确认它们在变异下红。

M 下 `tests/test_file_edit.py::test_a_later_read_replaces_the_earlier_one` 红：

```
E   AssertionError: assert ['OK', 'OK', ... 'STALE_EDIT'] == ['OK', 'OK', 'OK', 'OK']
```

也就是「读 → 改 → 再读 → 再改」的第四次派发落到 `STALE_EDIT`：CAS 比的是第一次读到的旧原文，而不是刚读到的新原文。

N 下 `tests/test_file_edit.py::test_a_write_does_not_count_as_having_read_it` 红：

```
E   AssertionError: assert ['OK', 'STALE_EDIT'] == ['OK', 'WRITE_WITHOUT_READ']
```

也就是「写一个新文件 → 直接 `edit` 它」被当成读过：prior 来自那次 `write` 的 `tool/result` 内容（`写了 …（N 个字符）`），跟文件正文必然不一致，于是 CAS 报 `STALE_EDIT`。判据把这两种失败分开：没读过就是 `WRITE_WITHOUT_READ`，读过但正文变了才是 `STALE_EDIT`。

还原实现后基线 140 passed / 1 skipped、`mypy --strict src` 干净、TOTAL 96%。两条新测试都进了 seam ③ 与 seam ② 的既有文件，没有新开测试文件。

## dud 变异（G、I、J′）

**G（删掉 `normcase`）不是变异**：本机 `os.path.realpath` 走 `GetFinalPathNameByHandleW`，已经把**存在**的路径折叠成磁盘上的大小写。实测同一个目录里 `realpath(<dir>/PLAN.md)` → `…\plan.md`，而 `realpath(<dir>/NOPE.md)` → `…\NOPE.md`（不存在的路径保留给定的大小写）。键相等只在「文件已存在」时被消费——`write_file` 的先读检查带 `target.exists()` 前置，`edit_file` 的 prior 来自一次成功的 `read`——所以去掉 `normcase` 不改变任何可观察行为；Linux 上 `normcase` 本来就是 no-op。`normcase` 留着是给「不存在的路径」与大小写不敏感文件系统兜底，它不是这条判据的执行者。

**I（档位段与边界段互换）不是变异**：边界段自带 `context.sandbox == "workspace-write"` 前置条件，`read-only` 段自带 `context.sandbox == "read-only"` 前置条件，两段互斥、不可能同时命中，所以先后顺序不可观察。要让这条顺序可观察，必须先去掉档位条件——那正是 H，而 H 被两条测试杀死。换句话说：M2 里「档位先于边界」这条顺序目前**没有独立判据**，它靠「两段互斥」成立；如果以后边界改成对所有档位生效（除 `danger-full-access`），这条顺序就要补判据。

**J′（只把 `judge_fence` 调用提前）不是变异**：`DENIED` 的返回仍在校验之后，可观察顺序没变——第一次写这条变异时全绿，把 `DENIED` 返回一起挪上去（J）才让两条测试变红。

## 实现过程中就地跑过的变异（已记在 tasks.md 对应条目）

收尾轮之前的红绿循环里也各补过变异，集中列在这里免得只散在 tasks.md：

| 组 | 变异 | 杀死它的判据 |
|---|---|---|
| 3 | `session/start` 里 `sandbox` / `approval` 写死 | 3.3 的 payload 断言 |
| 5 | `approval="auto"` 也走 `NEEDS_APPROVAL` | `test_auto_approval_writes_no_approval_records`、`test_danger_full_access_lifts_the_workspace_boundary` |
| 5 | 非 tty 时门返回 `APPROVED` | `test_the_three_approval_decisions_are_each_reachable_through_the_real_gate` |
| 6 | `glob` 去掉 `entry.is_file()` | `test_glob_never_returns_a_directory` |
| 6 | `glob` 去掉 mtime 排序 | `test_glob_orders_by_modification_time_newest_first` |
| 6 | `grep` 去掉 250 上限 | `test_grep_lists_at_most_two_hundred_and_fifty_matches` |
| 7 | 去掉 `write` 的先读检查 | 四条判据（7.1–7.4） |
| 7 | 已读集合去掉 `outcome == "OK"` 过滤 | `test_the_same_log_prefix_yields_the_same_read_set`、`test_a_failed_read_does_not_count_as_reading` |
| 8 | 去掉 CAS 比对 | `test_editing_a_file_changed_outside_the_session_is_stale` |
| 8 | 歧义判定去掉 `not args.replace_all` | `test_replace_all_replaces_every_match` |
| 11 | replay 里折叠只取 `assembled[:2]` | 11.2 |
| 11 | replay 给日志追加一行 | 「replay 两次日志字节不变」与 11.3 |
| 11 | replay 往工作区落 marker | 11.3 的工作区快照 |
| 11 | replay 里打印 `model/request` | 既有判据与 11.3 的 stdout 断言 |
| 12 | 去掉围栏拒绝后的 `break` | 12.1 |
| 12 | `FENCE_DENIED → 0` | `test_every_stop_reason_maps_to_an_exit_code` |
| 12 | 往 `closing_events` 塞 `tool/cancelled` | 加强后的 12.3（见注 3） |
| 12 | 往 `closing_events` 塞 `model/retry` | seam ① 的事件序列判据与 12.3 |
| 13 | `approval` 恒为 `auto`（无视 `--yes`） | 13.3 / 13.5 / 13.6 与 11.2 |
| 13 | 边界只在 `danger-full-access` 下生效 | 13.2 / 13.5 |
| 13 | `--yes` 顺手把档位抬成 `workspace-write` | 13.4 / 13.5 |
| 13 | `EXIT_FENCE_DENIED = 4` | 13.5 与 `test_every_stop_reason_maps_to_an_exit_code` |
| 13 | 提问写进 stdout | 13.6 与 gate 的 `capsys` 判据 |
| 13 | 回答流 EOF 判成 `DENIED` | 13.3（Windows 的 NUL 也报 `isatty() == True`，所以 `stdin=DEVNULL` 会走到「问人」这一步） |

## 方法论注记

1. **dud mutant 的三种形态本轮都撞到了**：语义等价（G）、被前置条件挡住的顺序互换（I）、只挪调用不挪结论（J′）。判据只认「可观察行为变了」，所以这三条不算变异，也不当覆盖缺口——但值得写下来，因为它们各自暴露了一个「看起来在测、其实测不到」的写法。
2. **存活变异集中在同一个函数**：M 与 N 都在 `reads_from_records`。同一个函数被改坏两次都全绿，说明「已读集合」这条判据当时只测了「读过 / 没读过」两个端点，没测「读的顺序」和「什么算读过」。补完两条后端点变成四个。
3. **`EventLog.append` 会把词表外的事件类型塌成 `error/internal`**（payload 里记 `unrecognized_type`），所以「塞一个不该写的事件」这种变异必须同时断言类型与 `unrecognized_type`，否则测试会绿在错误的原因上。
4. **变异轮的还原纪律**：每次还原前先看 `git status --short src`，确认只有刚改坏的那一个文件是脏的；本轮补的两条测试是**测试文件**的改动，`git checkout -- src/mini_harness/...` 不会碰它们，这一点在 M1 注 7 里踩过。
5. **P 一次杀死 15 条测试**，是本轮最「贵」的变异：`--events jsonl` 的 stdout 逐行等价判据把 stdout 的独占性钉得很死。反过来看，这也说明「stdout 归会话 id 与日志」这条规格在 CLI 黑盒里覆盖最厚。
