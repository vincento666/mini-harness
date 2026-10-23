# 变异测试一轮：`fix-small-window-compaction-dead-zone`

基线：413 passed / 5 skipped，`TOTAL 1938 stmts / 93 missing = 95%`。跑法：改坏一处 → 全量
`uv run pytest -q -rf --tb=no` → 记下变红的测试 → `git checkout --` 还原并确认
`git status --short -- <file>` 为空。五条**串行**跑，脚本 `.tmp/reacc/mut_run.py`，原始结果
`.tmp/reacc/mutants.json`。每条变异都改变了可观察行为（不是语义等价的 dud）。

| # | 变异 / 改法 | 结果 | 变红的测试 |
| --- | --- | --- | --- |
| M1 | 溢出判据改回触发线：`if reading > pressure:` → `if reading > line:` | **被杀**（4 红） | `test_cli_run.py::test_a_window_with_a_zero_trigger_line_runs`、`test_cli_run.py::test_a_dead_zone_window_still_holds_a_conversation`、`test_turn_compaction.py::test_a_dead_zone_reading_that_fits_the_window_is_not_an_overflow`、`test_turn_compaction.py::test_a_shadowed_range_too_big_to_trim_sends_no_summary_request` |
| M2 | `pressure_budget` 写成 `window - reserve - CONTEXT_HEADROOM_TOKENS` | **被杀**（12 红） | `test_context_budget.py::test_the_pressure_budget_is_the_window_minus_the_reserve`；seam ① 四条溢出判据全红；seam ⑥ 七条（`test_cli_chat.py` 两条、`test_cli_run.py` 四条、`test_cli_serve.py` 一条） |
| M3 | `detail` 去掉压力预算那个数：三处 `压力预算 {pressure}` → `预算` | **被杀**（3 红） | `test_overflow_when_nothing_can_be_shadowed`、`test_a_shadowed_range_too_big_to_trim_sends_no_summary_request`、`test_one_compaction_then_overflow_when_the_context_still_does_not_fit` |
| M4 | 「发不出摘要调用」重新直接通向一个错误结果：`if not body: return None` → 返回 `ProviderFailure(PROVIDER_CONTEXT_OVERFLOW)` | **被杀**（2 红） | `test_a_shadowed_range_too_big_to_trim_sends_no_summary_request`（新）、`test_a_summary_request_that_cannot_be_made_to_fit_is_never_sent`（M5 既有） |
| M5 | 无可遮蔽时仍写一条 `compaction/summary`：`if rng is None: return None` → 写一条 `shadowed_range {start:1,end:1}` 的摘要再返回 | **被杀**（6 红） | `test_cli_run.py::test_a_dead_zone_window_still_holds_a_conversation`、`test_turn_compaction.py` 的 `test_overflow_when_nothing_can_be_shadowed`、`test_a_dead_zone_reading_that_fits_the_window_is_not_an_overflow`、`test_a_shadowed_range_too_big_to_trim_sends_no_summary_request`、`test_an_overflow_closes_the_segment_not_the_session`、`test_a_provider_reported_overflow_collapses_into_the_same_result` |

**没有存活的变异，不需要补判据。** 还原后 `git status --short -- src tests` 为空。

## 这一轮顺带回答的两件事

- **tasks 5.1 的「咬得住」**：M1 与 M2 各杀掉 seam ⑥ 的判据（M1 杀 2 条、M2 杀 6 条），说明本轮改判据对象的那批 CLI 黑盒判据不是「改完就绿」——它们钉的是压力预算这条判据本身。
- **M4 与 M5 各杀出一条旧判据**：M4 抓到 M5 时代的 `test_a_summary_request_that_cannot_be_made_to_fit_is_never_sent` 仍然守着「不发请求」；M5 抓到「无可遮蔽」那条路上有六条判据在守，其中两条（`test_an_overflow_closes_the_segment_not_the_session`、`test_a_provider_reported_overflow_collapses_into_the_same_result`）不在本 change 的改动面上，是既有守卫。

## 第二轮（`code-review` 两轴之后）

为什么要补：AGENTS.md 定的顺序是 apply → 两轴 → 变异 → Learning Gate，本轮变异跑在两轴之前（欠账记在 `docs/adr/0002`）；两轴之后代码又改了 tasks 10.1–10.3，第一轮那五条的**咬合面变了**，所以重跑 M2 与 M3、新增 M6。基线：414 passed / 5 skipped，`TOTAL 1943 stmts / 93 missing = 95%`。脚本 `.tmp/reacc/mut_run2.py`，原始结果 `.tmp/reacc/mutants2.json`，三条串行。

| # | 变异 / 改法 | 结果 | 变红的测试 |
| --- | --- | --- | --- |
| M2（重跑） | `pressure_budget` 写成 `window - reserve - CONTEXT_HEADROOM_TOKENS` | **被杀**（28 红，第一轮 12 红） | 第一轮那 12 条全在；新红的是 `test_context_budget.py` 的触发线两条（`test_the_trigger_line_is_the_formula_with_the_locked_constants`、`test_the_trigger_line_takes_the_smaller_of_the_two_branches`）、`test_turn_compaction.py` 的摘要请求预算那一族（`test_an_over_line_assembly_compacts_before_the_assembly_record`、`test_the_summary_call_is_marked_and_gets_no_tools`、`test_a_run_with_room_to_spare_never_compacts`、`test_a_failed_summary_call_is_a_provider_error`、`test_the_summary_request_carries_only_the_shadowed_range`、`test_the_summary_trim_drops_whole_round_trips`、`test_the_compaction_record_has_the_keys_the_real_run_wrote`、`test_a_provider_reported_overflow_detail_carries_the_three_numbers`、`test_the_request_level_retry_records_the_context_it_actually_sent`）、`test_cli_chat.py` 的遮蔽反馈与逐点重放三条、`test_cli_replay.py::test_a_log_that_went_through_compaction_replays_pointwise`、`test_vocabulary_reachability.py::test_the_new_event_types_are_reached_by_a_real_run` |
| M3（重跑） | `detail` 去掉压力预算那个数：四处 `压力预算 {pressure}` → `预算` | **被杀**（4 红，第一轮 3 红） | 第一轮那三条 + 新判据 `test_a_provider_reported_overflow_detail_carries_the_three_numbers` |
| M6（新增） | provider 报出的那条溢出不带那三个数：出口那一串 `（{_budget_triple(…)}）` 摘掉 | **被杀**（1 红） | `test_a_provider_reported_overflow_detail_carries_the_three_numbers` |

**没有存活的变异。** 每条还原后 `git status --short -- <file>` 为空，整轮跑完 `git status --short -- src tests` 为空。

**M2 从 12 红变 28 红说明「一处事实」是真的**：`trigger_line` 内部那一处 `W - O` 与 `_compact_if_over_line` 的 `summary_budget` 改调 `pressure_budget` 之后，写歪一处就打歪触发线那两条判据、摘要请求的预算那一族判据、以及依赖压缩发生的 chat / replay / 词表判据。第一轮只有 12 红，正因为那时那两处还各自手算 `W - O`——同一个错误要写三次才全红。
