# M5 变异测试一轮：`m5-context-budget-compaction`

跑法：改坏一处实现 → 跑全量测试（`uv run pytest -q`）→ 记下哪些测试变红 → 还原并确认回到基线。
还原前先看 `git status`：这一轮工作区里还有未提交的改动（尾部预算那处修复与新测试），
所以只 `git checkout --` 被变异的那一个文件。基线 = 282 passed, 2 skipped。

| # | 变异点 | 改法 | 变红的测试 | 结论 |
| --- | --- | --- | --- | --- |
| 1 | 触发线公式 | `trigger_line` 里 `min(...)` 改成 `max(...)` | `test_the_trigger_line_is_the_formula_with_the_locked_constants`、`test_the_trigger_line_takes_the_smaller_of_the_two_branches`、`test_the_trigger_line_is_never_negative`、`test_an_over_line_assembly_compacts_before_the_assembly_record`、`test_the_summary_call_is_marked_and_gets_no_tools`、`test_overflow_when_nothing_can_be_shadowed`、`test_one_compaction_then_overflow_when_the_context_still_does_not_fit`、`test_every_stop_reason_is_reachable`、`test_the_new_event_types_are_reached_by_a_real_run`、`test_a_log_that_went_through_compaction_replays_pointwise`、`test_a_run_that_cannot_fit_its_window_exits_four_with_an_error_context`（11 红） | 杀死 |
| 2 | 尾部保留的记账单位 | 尾部累加器 `total = _tokens(_record_chars(last))` 改回 `total = _record_chars(last)`（把字符数当 token 数） | `test_the_tail_budget_is_counted_in_tokens_not_characters`（1 红） | 杀死（见下「一处存活的变异变成一处真 bug」） |
| 3 | 语法边界：切点不拆散工具往返 | `_round_end` 开头直接 `return None`（整组一起遮蔽的规则失效） | `test_the_cut_never_splits_an_assistant_request_from_its_tool_round`、`test_a_lone_tool_round_that_does_not_fit_returns_none`（2 红） | 杀死 |
| 4 | 遮蔽是一条替换记录 | `fold` 里 `if event.seq in shadowed and ...: continue` 加 `and False`（读方不再跳过被遮蔽的记录） | `test_shadowed_records_produce_no_messages`、`test_the_summary_sits_after_the_user_prompt`、`test_two_summaries_are_ordered_by_their_seq`、`test_a_compaction_purpose_response_produces_no_assistant_message`、`test_the_fold_at_each_point_sees_only_its_prefix`、`test_an_over_line_assembly_compacts_before_the_assembly_record`、`test_a_log_that_went_through_compaction_replays_pointwise`（7 红） | 杀死 |
| 5 | 预算读数的校准来源 | `budget_reading` 里去掉「被遮蔽的读数不参与校准」那半条判据 | `test_a_shadowed_measurement_stops_calibrating`（1 红） | 杀死 |
| 6 | 溢出判定（provider 侧） | `_reports_context_overflow` 直接 `return True`（任何 400 都算上下文超限） | `test_a_400_with_any_other_error_code_is_still_an_http_status_result`、`test_a_400_is_not_retried`、`test_an_unset_key_env_still_sends_the_request`（3 红） | 杀死 |
| 7 | 窗口参数的校验 | CLI 里 `if value < 1` 改成 `if value < 0` | `test_a_budget_argument_below_one_is_a_parameter_error_with_no_log[--window]` 与 `[--reserve]`（2 红） | 杀死 |

七个变异全部被杀死，没有存活的。

## 一处「存活的变异」变成一处真 bug

变异 2 不是先写出来的，是反过来撞上的：做变异 2 的准备时读到

```python
keep_from = candidates[-1].seq
total = _record_chars(candidates[-1])      # 字符
for event in reversed(candidates[:-1]):
    cost = _tokens(_record_chars(event))   # token
```

累加器第一行是**字符**、后续加的是 **token**：尾部第一条记录的成本被放大了 4 倍，
于是切点会停得太靠前（遮蔽得比保留预算允许的更多）。把它改对之后跑全量测试——
**282 条全绿**，没有任何一条测试注意到这个差别。按纪律这就是覆盖缺口：
补一条能区分两种记账的判据 `test_the_tail_budget_is_counted_in_tokens_not_characters`
（窗口 9375 → 保留预算 1500 token；尾部两条 4000 字符 + 100 字符 = 1025 token 装得下 →
没有可遮蔽的内容），再把它放回变异下确认变红，然后还原。

这条判据写出来时实现已经是对的，所以它不是红绿对，是把「已经成立」钉成判据。

## 还原后的基线

`git status` 只剩这两处本轮改动：`src/mini_harness/context/budget.py`（1 行修复）与
`tests/test_context_budget.py`（+20 行新判据）。全量门禁回到 282 passed, 2 skipped。
