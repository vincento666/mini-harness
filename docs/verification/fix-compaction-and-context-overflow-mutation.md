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

## 第二轮（2026-10-23 09:51 至 10:42，tasks 8.7）

跑法：改坏一处实现 → **跑全量测试** → 记「变异 / 改法 / 哪些测试变红」→ 还原。起点 `e5ad72f` 加上本轮四条裁决（8.1–8.4）的未提交改动。基线 **408 passed / 5 skipped**（第一轮之后新增五条判据）。这一轮全部跑全量：上一轮 1 与 4 跑全量、其余定点，人裁决定「六条全部跑全量」，并把变异 4 拆成两处单点。

| # | 位置 | 改法 | 变红的测试（全量） | 结果 |
| --- | --- | --- | --- | --- |
| 1 | `loop/turn_loop.py:655` | `body = fold_range(events, start=…, end=…)` 换成 `body = context.messages[1:]`——摘要请求改回发整份表层 | 407 passed / 1 failed：`test_the_summary_request_carries_only_the_shadowed_range`（红在 `assert all(content in range_contents for content in body)`，`rng={'start': 1, 'end': 7}`） | 杀死 |
| 2 | `provider/openai_compat.py:180` | `phrase in lowered` 换成 `phrase in message`（短语表改成大小写敏感） | 407 passed / 1 failed：`test_every_context_overflow_phrase_is_reachable`（判据喂的正是每条短语的大写形状） | 杀死 |
| 3 | `provider/openai_compat.py:156` | 去掉截断：`summary[: _DETAIL_MAX_CHARS - len(prefix) - 1]` 换成 `summary` | 406 passed / 2 failed：`test_a_non_json_body_goes_into_the_detail_as_itself`、`test_the_provider_sentence_reaches_the_error_model_detail`（都红在 `assert 1119 <= 200`） | 杀死 |
| 4a | `cli/main.py:513` | 段注脚那一行 `file=sys.stderr` 换成 `file=sys.stdout` | 404 passed / 4 failed：`test_a_provider_failed_segment_says_so_on_stderr`、`test_a_max_turns_segment_says_so_on_stderr`、`test_a_fence_denied_segment_says_so_on_stderr`（本轮新增）、`test_an_overflowed_segment_says_so_on_stderr` | 杀死 |
| 4b | `cli/main.py:536` | 遮蔽反馈那一行 `file=sys.stderr` 换成 `file=sys.stdout` | 405 passed / 3 failed：`test_a_segments_summary_never_appears_on_stdout`、`test_a_compaction_shows_what_it_shadowed_on_stderr`、`test_a_chat_that_compacted_replays_the_same_log_unchanged`（本轮新增） | 杀死 |
| 5 | `cli/main.py:533-536` | 不读 `compaction/summary`，硬编码成 `[遮蔽] 折掉 seq 1 至 8：tokens 15196 降至 74` | 407 passed / 1 failed：`test_a_compaction_shows_what_it_shadowed_on_stderr`（那一行里四个数取自日志读出的那条记录，硬编码的那组对不上） | 杀死 |
| 6 | `cli/main.py:529` | 去掉 `event.seq <= through` 这条线——每段都重报整份日志里发生过的压缩 | 407 passed / 1 failed：`test_a_compaction_shows_what_it_shadowed_on_stderr`（红在 `assert 2 == 1`，同一行出现两遍） | 杀死 |
| 7 | `provider/openai_compat.py:309` | 把「塌成溢出」的判断挪到重试耗尽那条早退之前——5xx 与 429 的正文也去查短语表 | 406 passed / 2 failed：`test_a_500_saying_context_length_exceeded_is_not_an_overflow`、`test_a_429_saying_prompt_is_too_long_is_not_an_overflow`（都红在 `assert 'PROVIDER_CONTEXT_OVERFLOW' == 'PROVIDER_HTTP_STATUS'`） | 杀死 |
| 8 | `cli/main.py:499` | `_SEGMENT_NOTE_SUPPRESSED` 里加进 `STOP_FENCE_DENIED`——围栏拒绝收尾的段又变回无声 | 407 passed / 1 failed：`test_a_fence_denied_segment_says_so_on_stderr`（红在 `assert len(notes) == 1` 实得 0） | 杀死 |
| 9 | `loop/turn_loop.py:657` | `body = _drop_leading_unit(body)` 换回 `body = body[1:]`——裁剪改回逐条丢 | 407 passed / 1 failed：`test_the_summary_trim_drops_whole_round_trips`（红在摘要请求的角色序列 `system / tool / assistant / tool / user`，那条 `tool` 没有请求它的 `assistant`） | 杀死 |

**第 7 条是本轮补判据时当场跑的那一条。** 8.3 的两条判据在改前的实现下就是绿的——`openai_compat.py` 里重试耗尽那条早退本来就挡住了 5xx 与 429，`status >= 400` 那一处从来没有可达的 5xx。所以先确认它们不空转：把塌成溢出的判断挪到那条早退之前，两条都红，还原。这一轮把它一并跑全量记账。

**第 8 与 9 条打的是本轮新写的两条判据**，各自只红在打它的那一条上——8.1 与 8.2 的红绿对本来就是先红后绿，这两条变异是「判据确实钉住了实现」的第二次确认。

**还原。** 还原前先看 `git status`：工作树里与本轮无关的 `docs/tools/`、`repowiki/` 与 `.gitignore` 改动一处没动。十条还原后 `git diff HEAD -- src tests` 是 6 个文件 / +155 / −8——正是本轮四条裁决的改动，没有残留的变异。基线复现：408 passed / 5 skipped、`TOTAL 1931 / 93 / 95%`、mypy `Success: no issues found in 29 source files`、ruff format 70 文件已格式化、ruff check 通过。

**结论：第二轮十个变异全部被杀死，没有存活的变异，没有 dud。** 上一轮定点跑的四条这一轮跑全量：4a 杀四条段注脚判据、4b 杀三条遮蔽判据，合起来盖住上一轮那条 4 的五个，另加本轮新增的两条（`FENCE_DENIED` 那条与 chat 日志重放那条）。
