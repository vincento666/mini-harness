# M6 变异测试一轮（`m6-chat-repl`）

跑法：改坏一处实现 → `uv run pytest -q` 全量 → 记「变异 / 改法 / 哪些测试变红」→ 还原（还原前先看 `git diff --stat src`，别把本轮未提交的判据一起回滚）。变异都改变可观察行为。起点 `86ac972`（`change/m6-chat-repl`），2026-10-21 23:36 至 2026-10-22 00:10。

| # | 位置 | 改法 | 变红的测试 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | `loop/turn_loop.py:591` `_recover_overflowed_request` | 重试的 `context/assembled` 用装配点那份（`folded` 换成 `context`） | `test_turn_compaction.py::test_the_request_level_retry_records_the_context_it_actually_sent`（1 failed / 353 passed） | 杀死 |
| 2 | 同文件 `:601-608` | 重试仍报超限时改走 `_provider_error`（塌成 `error/model` 加 `PROVIDER_ERROR`） | `test_a_provider_reported_overflow_that_survives_the_retry_collapses` | 杀死 |
| 3 | `cli/main.py:386` `_print_new_replies` | `"purpose" in event.payload` 放宽成 `False`（摘要回复也打到 stdout） | 无，355 全绿 | **存活 → 缺口** |
| 4 | `cli/main.py:454` `_chat_session` | `session/end` 的 `stop_reason` 换成 `MAX_TURNS` | `test_two_inputs_make_one_log_two_segments_and_two_user_messages`、`test_a_segment_failure_does_not_end_the_session`、`test_an_overflowed_segment_returns_to_the_prompt` | 杀死 |
| 5 | 同处 | `turns=turn_index - 1` 换成 `turn_index`（回合数与回合编号混用） | 无，355 全绿 | **存活 → 缺口** |
| 6 | `cli/main.py:123` `build_parser` | chat 加一个 `--events jsonl` | `test_chats_flag_table_is_runs_flag_table_minus_two` | 杀死 |
| 7 | `cli/main.py:277` `_prepare_or_fail` | 密钥缺失那条的退出码 2 换成 1 | `test_a_chat_that_cannot_start_leaves_no_log`、`test_cli_config.py::test_a_missing_required_item_leaves_no_log_file`、`test_cli_provider.py` 的三条 | 杀死 |
| 8 | `cli/main.py:236` 启动期窗口校验 | `<= 0` 换成 `< 0` | 无，355 全绿 | **存活 → 缺口** |
| 9 | `events/fold.py:204` `assembly_points` | 不跟 `turn/start` 记 `turn_id`（装配点失去回合归属） | 12 条：`test_cli_replay.py` 九条、`test_cli_run.py::test_a_hard_killed_log_replays_without_appending`、`test_context_fold.py::test_assembly_points_carry_their_own_prefix_and_turn_id`、`test_turn_compaction.py::test_the_request_level_retry_records_the_context_it_actually_sent` | 杀死 |
| 10 | `loop/turn_loop.py:687` `start_session` | `session/start` 不写 `entry` | 只有 `test_cli_chat.py::test_chat_shares_the_flag_table_and_the_layering` | 杀死，但**暴露缺口** |
| 11 | `loop/turn_loop.py:751` `run_turn_segment` | `segment/end.turns` 恒 1 | `test_cli_chat.py::test_a_segment_that_uses_up_max_turns_returns_to_the_prompt`、`test_turn_loop.py::test_two_segments_number_segments_and_turns_continuously` | 杀死 |
| 12 | `cli/main.py:365` `_chat_sigint_handler` | `signals.active is not None` 换成 `False`（Ctrl-C 永不取消当前段） | `test_cli_chat.py::test_the_chat_handler_cancels_the_running_segment`：判据把 `KeyboardInterrupt` 抛穿到 pytest，整轮中止（exit 2，30 passed 后中断） | 杀死（形状特殊） |

## 三个存活的与一个暴露的缺口，补的判据

补的判据都在**变异还挂着的时候**先确认红，再还原确认绿。

- **变异 3** → `test_cli_chat.py::test_a_segments_summary_never_appears_on_stdout`：一条输入、一次真压缩（`--window 70000 --reserve 100`，`read` 一个 100000 字符的文件），日志里有 `compaction/summary`，stdout 必须恰是 `["> ", "先读一下", "这是回复", "> "]`。红在 `assert '那是摘要不该出现' not in result.stdout`。缺口成因：chat 的判据里从来没有一次真压缩，所以「不打带 `purpose` 的那条」这条规则在 seam ⑥ 上没人钉。
- **变异 5** → `test_two_inputs...` 加 `session/end.turns == 2`（红在 `assert 3 == 2`）、`test_an_empty_stdin_is_a_legal_session` 加 `turns == 0`（红在 `assert 1 == 0`）。缺口成因：「会话跑掉的回合数」与「最后一个回合编号」在 chat 这一侧没人分辨，`turn_index - 1` 那一格减不减都一样。
- **变异 8** → `test_cli_run.py::test_a_window_that_leaves_exactly_zero_pressure_budget_is_a_parameter_error`（`--window 70000 --reserve 4464`，`W - O - 65536` 恰为 0）。红在 `assert 4 == 2`：少了 `<= 0` 那一格，配置期错误跑到运行期变成退出码 4——正是 ADR-0019 要避开的形状。既有判据用的三个窗口（32768 / 4096、70000 / 4096、66000 / 100）都不落在 0 上。
- **变异 10** → `test_cli_run.py::test_a_run_records_which_entry_opened_the_session`（红在 `KeyError: 'entry'`）。`entry` 的两个值此前只有 `chat` 那一半有判据，`run` 那一半没有——「每个词表值可达」这条纪律在 M6 只做到了一半。

## dud 变异（不计）

把密钥缺失那条的退出码写成不存在的常量 `EXIT_PROVIDER_FAILURE`：红是 `NameError` 而不是行为差异，属语义无关的 dud。已换成存在的 `EXIT_INTERNAL_ERROR` 重跑，即变异 7。

## 一条测试侧观察（不动代码）

`test_the_chat_handler_cancels_the_running_segment` 装上 SIGINT 处理器后没有还原。判据本身有效（变异 12 正是被它杀死的），但它把信号处理器留在了测试进程里：变异让处理器改抛异常时，整轮 pytest 中止而不是只让那一条判据变红。记在这里，不在 M6 动。

## 基线确认与门禁

还原后 `git diff --stat src` 为空（只剩本轮新增的判据在 `tests/`）。门禁四道：`ruff format --diff` 0（67 files already formatted）、`ruff check` 0、`mypy --strict src` Success（28 source files）、`357 passed / 4 skipped`、`TOTAL 1704 语句 / 84 未覆盖 / 95%`（地板 95%，`--fail-under=95` 退出码 0）。

判据达成：12 个变异全部被杀死，其中三个存活变异与一个暴露的缺口由本轮补的四条判据杀死（`fold.py` 98%、`turn_loop.py` 90% 未变——补的判据都在 seam ⑥ 与 seam ① 的既有低覆盖处之外）。
