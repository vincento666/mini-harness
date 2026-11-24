# align-turn-step-naming 变异测试（2026-11-24）

口径：每个变异改动一处实现 → 跑全量 `pytest` → 记录变红的测试 → 还原 → 复跑确认回到基线。基线是 **877 passed / 7 skipped**（2026-11-24，`e9c43a2`）。跑测试时 `TMPDIR` 与 `--basetemp` 都指向仓库内，避开沙箱对系统临时根的拦截（见 `CURRENT.md` 的环境条目）。

| # | 变异 | 改法与位置 | 变红的测试 | 结论 |
|---|---|---|---|---|
| 1 | 版本门放行 v1 | `events/reader.py`：`schema_version != SCHEMA_VERSION` 改成 `not in {SCHEMA_VERSION, 1}` | `test_a_v1_line_is_rejected_with_schema_unsupported`、`test_other_schema_versions_are_rejected[1]` | 杀死（2 红） |
| 2 | 词表判据恒真 | `events/vocabulary.py::is_known_type` 直接 `return True` | `test_the_vocabulary_holds_only_current_names`、`test_a_record_cannot_carry_an_unknown_type`、`test_writing_a_legacy_name_falls_back_to_error_internal`、`test_types_outside_the_vocabulary_are_written_as_error_internal`、`test_turn_and_step_types_are_current_while_segment_is_outside`、`test_a_record_type_outside_the_vocabulary_is_a_read_failure` | 杀死（6 红） |
| 3 | 重启扫描数步而非轮 | `session/host.py::_scan_session_index`：`record.type == "turn/start"` 改成 `"step/start"` | 首次全量 **45 passed，没有红** | **存活 → 补判据** |

## 缺口与补法（第 3 条）

活句柄的 `turns` 走 `_begin_turn` 的自增；重启后的列表走 `_scan_session_index` 从日志重建。原有判据 `test_the_session_view_counts_turns_not_steps` 只覆盖前者，所以「重建时数错事件」不会被发现。

补的判据是 `test_a_restarted_list_rebuilds_turns_from_turn_starts`：写一份「一轮两步」的 v2 日志（`turn/start` 一条 + `step/start` 两条 + `session/end`），再启动 host，断言 `GET /sessions` 里该会话的 `turns == 1`。它在变异下红（得到 2），还原后绿。

## 覆盖口径说明

- 三条变异都改变可观察行为（放行旧版本、接受任意类型名、数错事件），不是 dud mutant。
- 第 1 条的变异选取「恰好放行 v1」而不是「放行全部」，是为了让「v1 被拒」这条判据单独承压；如果选「放行全部」，同一个变异会撞红十几条测试，看不出哪条判据真正在守版本门。
- 本轮只跑三条；`host` 视图的两条路径（活句柄、重启重建）与日志读写两侧都被覆盖到。
