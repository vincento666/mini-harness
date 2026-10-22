# `fix-compaction-and-context-overflow` 变异测试一轮

跑法：改坏一处实现 → 跑测试（1 与 4 跑全量，其余定点）→ 记「变异 / 改法 / 哪些测试变红」→ 还原。起点 `c7df1d1`（`change/fix-compaction-and-context-overflow`），2026-10-22 23:44 至 23:58。基线 **403 passed / 5 skipped**，`TOTAL 1921 / 92 / 95%`。

| # | 位置 | 改法 | 变红的测试 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | `loop/turn_loop.py:639` `_compact_if_over_line` | `body = fold_range(events, start=…, end=…)` 换成 `body = context.messages[1:]`——摘要请求改回发整份表层 | 全量 402 passed / 1 failed：`test_the_summary_request_carries_only_the_shadowed_range`（红在 `assert all(content in range_contents for content in body)`，`rng={'start': 1, 'end': 7}`） | 杀死 |
| 2 | `provider/openai_compat.py:180` `_reports_context_overflow` | `phrase in lowered` 换成 `phrase in message`（短语表改成大小写敏感） | 定点 31 passed / 1 failed：`test_every_context_overflow_phrase_is_reachable`（判据喂的正是每条短语的大写形状，四条里三条没被认出来） | 杀死 |
| 3 | `provider/openai_compat.py:156` `_failure_detail` | 去掉截断：`summary[: _DETAIL_MAX_CHARS - len(prefix) - 1]` 换成 `summary` | 定点 52 passed / 2 failed：`test_a_non_json_body_goes_into_the_detail_as_itself`、`test_the_provider_sentence_reaches_the_error_model_detail`（红在 `assert 1119 <= 200`） | 杀死 |
| 4 | `cli/main.py:515` 与 `:537` | 两处 `file=sys.stderr` 换成 `file=sys.stdout`——段注脚与遮蔽反馈改打 stdout | 定点 15 passed / 5 failed：`test_a_provider_failed_segment_says_so_on_stderr`、`test_a_max_turns_segment_says_so_on_stderr`、`test_an_overflowed_segment_says_so_on_stderr`、`test_a_compaction_shows_what_it_shadowed_on_stderr`，外加既有的 `test_a_segments_summary_never_appears_on_stdout`（stdout 的投影规则被这两行挤脏） | 杀死 |
| 5 | `cli/main.py:532-537` `_print_shadow_feedback` | 不读 `compaction/summary`，硬编码成 `[遮蔽] 折掉 seq 1 至 8：tokens 1 降至 2` | 定点 19 passed / 1 failed：`test_a_compaction_shows_what_it_shadowed_on_stderr`（那一行里四个数一个都对不上） | 杀死 |
| 6 | `cli/main.py:529` | 去掉 `event.seq <= through` 这条线——每段都重报整份日志里发生过的压缩 | `test_a_compaction_shows_what_it_shadowed_on_stderr` 红在 `assert 2 == 1`（同一行出现两遍） | 杀死 |

**第 6 条不是收尾轮才想到的。** apply 到 5.2 时真端点那一跑先跑出「同一压缩记录报两遍」，mock 判据抓不到——那些判据每段只喂一条输入，第二次不报也看不出来。修好后当场用它确认过红，这一轮把它一并记账。

**还原。** 还原前先看 `git status`：本轮开始时工作树里已有与本轮无关的 `docs/tools/` 与 `repowiki/` 改动，一处都没动。还原后 `git diff HEAD -- src tests` 是 0 行。过程中手滑过一次——第 2 条还原时把 `lowered = message.lower()` 写了两遍，靠这条 diff 查出来清掉；纪律「还原前先看 `git status`」就是为这种手滑写的。基线复现：403 passed / 5 skipped、`TOTAL 1921 / 92 / 95%`。

**结论：六个变异全部被杀死，没有存活的变异，没有 dud（每条都改变可观察行为）。**
