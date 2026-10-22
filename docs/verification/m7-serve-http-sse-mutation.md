# M7 变异测试一轮（`m7-serve-http-sse`）

跑法：改坏一处实现 → `uv run pytest -q` 全量 → 记「变异 / 改法 / 哪些测试变红」→ 还原（还原前先看 `git status`，别把本轮未提交的判据一起回滚）。变异都改变可观察行为。起点 `9c226ee`（`change/m7-serve-http-sse`），2026-10-22 16:58 至 17:52。基线 385 passed / 5 skipped。

| # | 位置 | 改法 | 变红的测试 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | `cli/serve.py:50` `_sse_frame` | 帧里不写 `id:` 那一行 | 7 条：`test_one_frame_per_log_record`（`KeyError: 'id'`）、`test_reconnecting_with_last_event_id_continues_after_that_record`、`test_the_from_query_overrides_the_last_event_id_header`、`test_a_cursor_ahead_of_what_is_written_is_not_an_error`、`test_a_cursor_that_is_negative_or_not_an_integer_is_400`、`test_a_half_written_line_is_never_streamed`、`test_two_clients_read_the_same_stream_without_shadowing_each_other`（7 failed / 378 passed） | 杀死 |
| 2 | `cli/serve.py:36` `_CURSOR_DIGITS` | `[0-9]+` 换成 `[1-9][0-9]*`（`0` 不再是合法游标） | `test_a_cursor_that_is_negative_or_not_an_integer_is_400`（红在 `IndexError`：带 `Last-Event-ID: 0` 的连接变成 400、一帧都没有） | 杀死 |
| 3 | `cli/serve.py:63-65` `_cursor` | 读游标的先后反过来（`Last-Event-ID` 覆盖 `?from=`） | `test_the_from_query_overrides_the_last_event_id_header`（`assert 6 == 3`） | 杀死 |
| 4 | `cli/serve.py:120-125` `_events` | 去掉 `except ConnectionResetError` 那一圈 | `test_a_client_that_disconnects_changes_nothing_about_the_session`：子进程 stderr 里冒出 aiohttp 的 `Error handling request from 127.0.0.1` 与 traceback | 杀死 |
| 5 | `events/reader.py:69` `LogTail.read_new` | `chunk.rfind(b"\n")` 换成 `len(chunk) - 1`（残行也消费掉） | `test_event_log_append.py::test_the_tail_consumes_nothing_of_a_half_written_line`（红在 `isinstance(LogReadFailure 对象, list)` 为假） | 杀死 |
| 6 | `events/reader.py:78` | `record.seq > self._after` 换成 `>=`（游标那条记录重复送一遍） | 4 条：`test_reconnecting_with_last_event_id_continues_after_that_record`、`test_the_from_query_overrides_the_last_event_id_header`、`test_a_cursor_ahead_of_what_is_written_is_not_an_error`、`test_a_cursor_that_is_negative_or_not_an_integer_is_400` | 杀死 |
| 7 | `cli/main.py:390` `_serve` | `port > 65535` 换成 `> 65536` | `test_ports_outside_the_vocabulary_are_invalid_arguments`：红在 `assert 1 == 2`——65536 跑到 `sock.bind` 变成 `OverflowError: bind(): port must be 0-65535`，参数错误塌成运行期故障 | 杀死 |
| 8 | `cli/main.py:430` `_serve_session` | `entry=ENTRY_SERVE` 换成 `ENTRY_RUN` | `test_the_start_record_names_the_serve_entry_and_the_prompt_verbatim`、`test_serve_without_the_http_flag_is_the_same_session` | 杀死 |
| 9 | `cli/main.py:418` | 监听地址从 stderr 改到 stdout | 3 条：`test_stdout_is_only_the_session_id_and_stderr_says_where_it_listens`、`test_budget_overflow_in_serve_is_a_process_exit`、`test_serve_without_the_http_flag_is_the_same_session` | 杀死 |
| 10 | `cli/main.py:408-425` `_serve_session` | 装配（`_prepare_or_fail`）挪到绑定之前 | `test_an_occupied_port_fails_before_the_session_starts`：红在多出一个 `sessions/<id>.jsonl` | 杀死 |
| 11 | `cli/main.py:397` `_serve` | 去掉 `host not in SERVE_HOSTS` 那一格 | `test_host_outside_the_vocabulary_is_an_invalid_argument`：红在 `assert 0 == 2`——`--host localhost` 真能绑上并把会话跑完 | 杀死 |
| 12 | `tools/bash_tools.py:83` | 两处 `errors="replace"` 换成 `errors="ignore"` | `test_bash_tool.py::test_non_utf8_output_collapses_into_replacement_characters`：红在 `'\ufffd\ufffd中文\ufffd' in '退出码 0\n中文'` | 杀死 |
| 13 | `cli/main.py:130` `build_parser` | `--http` 改回 `required=True` | `test_serve_without_the_http_flag_is_the_same_session`：红在 `assert 2 == 0`（`INVALID_ARGUMENT: the following arguments are required: --http`） | 杀死 |
| 14 | `cli/serve.py:126` `_events` | `if self.session_finished.is_set(): return response` 改成永不返回（事件流不跟会话收尾一起结束） | **定点变异**（只跑 `tests/test_cli_serve.py`，290 s）：8 条红，全部撞 `httpx.ReadTimeout` | 杀死（形状特殊：这一处一挂，所有「读到底」的判据一起超时） |
| 15 | `cli/serve.py:34` `NO_CURSOR` | `-1` 换成 `0`（没有游标时跳过日志第一条） | 5 条：`test_one_frame_per_log_record`（`assert 15 == 16`）、`test_the_stream_carries_no_fact_the_log_does_not_have`、`test_reconnecting_with_last_event_id_continues_after_that_record`、`test_a_half_written_line_is_never_streamed`、`test_two_clients_read_the_same_stream_without_shadowing_each_other` | 杀死 |

## 两条变异暴露的正是 10.1 补的判据

- **变异 8**（`entry=ENTRY_SERVE` → `ENTRY_RUN`）在 10.1 之前**全仓 21 条 serve 判据一条都不红**——`entry` 只有 seam ① 的进程内判据。补完 `test_the_start_record_names_the_serve_entry_and_the_prompt_verbatim` 与不带 `--http` 那条之后，它一装上去就红两条。这是 `docs/lessons.md` 里 L-048（「新入口必须重跑旧入口的事件形状」）在 M6 记过的同一课在 M7 复发。
- **变异 12 与 13** 判的是 10.1 新补的 bash lossy UTF-8 判据与「`--http` 可选」判据：两条都不是空转。
- **变异 5** 是 M7 中途那个「只在 seam ⑥ 存活」的变异：当时三轮（含 20000 汉字的记录）全绿，人裁决定把判据落到 seam ④（`test_the_tail_consumes_nothing_of_a_half_written_line`）之后才被抓到。本轮它一次就红。

## 没有变异的三处（缺口，已记账）

- `cli/serve.py:119`：`LogTail` 返回 `LogReadFailure` 时事件流提前结束。要触发它得在会话进行中让那份日志读不动，`serve.py` 唯一未覆盖的一行就是它。
- `--host 0.0.0.0` 真绑定、`--port 65535` 上界：没有判据，也就没有可放的变异（变异 7 与 11 判的是词表本身，不是这两个合法端点）。
- 慢读者把进程退出拖到 `shutdown_timeout`：没有判据。

三处都记在 `docs/adr/0002-deferred-refactors.md` 第 61 条与第 54 条，处理时点 M10 或 Linux runner。

## dud 变异

本轮没有 dud：15 处改法都改变了可观察行为（退出码、帧内容、日志文件是否存在、stdout / stderr 的内容），没有语义等价的改法。

## 基线确认与门禁

变异 14 之后先 `git status`（只有外来文件与 `src/mini_harness/cli/serve.py` 这一处变异）再还原。全部还原后 `git diff --stat src tests` 为空。门禁四道：`ruff format --diff` 退出码 0（69 files already formatted）、`ruff check` 退出码 0（All checks passed）、`mypy --strict src` 退出码 0（Success: no issues found in 29 source files）、`385 passed / 5 skipped`、`TOTAL 1852 语句 / 89 未覆盖 / 95%`（地板 95%，`--fail-under=95` 退出码 0）。

判据达成：**15 个变异全部被杀死**，没有存活变异，因此没有新的补判据；覆盖率分布与本轮起点相同（`cli/serve.py` 75 / 1 未覆盖、`cli/main.py` 313 / 9、`events/reader.py` 50 / 6、`tools/bash_tools.py` 48 / 3）。
