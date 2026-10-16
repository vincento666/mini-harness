# M1 变异测试记录

**基线**：分支 `change/m1-event-log-and-turn-loop`，47 个测试全绿、`uv run mypy --strict src` 干净、`openspec validate m1-event-log-and-turn-loop --strict` valid。
**做法**：只改 `src/mini_harness/` 里一处实现 → 跑全量 `uv run pytest -q` → 记录「变异 / 改法 / 哪些测试变红」→ `git checkout -- <file>` 还原 → 再跑一次全量确认回到基线。

## 变异与结果

| | 变异 | 改法 | 结果 | 判定 |
|---|---|---|---|---|
| A | 受保护头部顺序 | `events/fold.py`：`messages=[*header, *body]` → `[*body, *header]` | 3 failed：`test_fold_puts_the_system_prompt_first_and_keeps_the_body_in_order`、`test_header_cannot_be_replaced_by_conversation_content`、`test_long_conversation_is_folded_without_truncation` | 杀死 |
| B | 停止判定 | `loop/turn_loop.py`：break 条件里的 `or not generated.tool_calls` → `or False` | 10 failed / 31 passed，含 `test_single_turn_writes_the_expected_event_sequence`、`test_empty_tool_calls_ends_the_loop_with_model_completed`、`test_previous_tool_result_is_folded_into_the_next_context`、`test_loop_only_calls_generate_with_three_positional_parameters` | 杀死 |
| C | 只追加 | `events/writer.py`：`self.path.open("a", encoding="utf-8")` → `open("w", encoding="utf-8")` | 16 failed / 25 passed | 杀死 |
| D | 事件词表判定 | `events/vocabulary.py`：`is_known_type` 直接 `return True` | 1 failed / 45 passed：`test_types_outside_the_vocabulary_are_written_as_error_internal` | 杀死（只有一条测试守住） |
| E | `seq` 递增 | `events/writer.py`：删掉 `self._next_seq += 1` | 1 failed / 45 passed：`test_seq_starts_at_zero_and_increments_by_one` | 杀死（只有一条测试守住） |
| F | fixture 回放顺序 | `provider/mock.py`：`raw = self._entries[self._index]` → `raw = self._entries[0]` | 7 failed / 39 passed：`test_generate_replays_the_fixture_entries_in_order`、`test_unregistered_tool_call_is_a_paired_unknown_tool_result`、`test_previous_tool_result_is_folded_into_the_next_context`、`test_turn_that_requests_tool_calls_closes_with_tool_calls`、`test_replay_recomputes_and_verifies_every_assembly_point`、`test_multi_turn_scenario_with_tool_call_and_fixture_exhaustion`、`test_no_m1_scenario_exits_with_the_reserved_codes` | 杀死 |
| G | 头部指纹来源 | `events/fold.py`：`header_fingerprint` 改成对 **body** 计算而不是对 header 计算 | **46 passed，变异存活** | 存活 → 覆盖缺口 |

## 存活变异的处理（G）

G 存活说明没有任何测试把指纹钉在「受保护头部的内容」上：实时折叠与 replay 重算用的是同一个被改坏的函数，所以逐点校验也照样通过。补了一条测试 `tests/test_context_fold.py::test_header_fingerprint_tracks_the_header_not_the_conversation`（断言 `--append-system-prompt` 改变指纹、对话体变长不改变指纹）。它在 G 变异下红：

```
assert plain.header_fingerprint != with_extra.header_fingerprint
AssertionError: assert '8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4' != '8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4'
```

还原 `fold.py` 后全量 47 passed，G 被这条新测试杀死。

## 方法论注记

1. **语义等价的改写不是变异**：`elif not generated.tool_calls:` → `elif False:` 没有让任何测试变红，因为后面的 break 条件里还有同一个判断、`stop_reason` 取值也不变。好的变异必须真的改变可观察行为。
2. **导致 collect error 的改名不是变异**：把 `is_known_type` 改名会让 5 个测试文件在收集阶段报错（退出码 2），测不出任何断言强度。要变异行为，不要变异标识符。
3. **一次只改一处**，且每次变异后都跑全量测试；只跑局部测试会把「只有一条测试守住」的脆弱点误判成强健。
4. **存活变异一律当覆盖缺口处理**：补一条能杀死它的测试（先确认它在变异下红），再还原实现。
5. D 与 E 各只有一条测试守住，是 M1 里最薄两处；M2 引入文件工具后应让它们被更多场景覆盖。

## 第 11 节修复轮的变异轮（tasks 11.13）

**基线**：commit `aecbdb6`，59 个测试全绿、`uv run mypy --strict src` 干净、`openspec validate m1-event-log-and-turn-loop --strict` valid。做法同上：一次只改 `src/mini_harness/` 一处 → 全量 `uv run pytest -q` → 记录 → `git checkout -- <file>` 还原。

| | 变异 | 改法 | 结果 | 判定 |
|---|---|---|---|---|
| H | 追加写的 OSError 捕获 | `events/writer.py`：删掉 `append` 里的 `try/except OSError`，直接写 | 2 failed：`test_a_log_that_becomes_unwritable_mid_session_is_a_log_write_failure`、`test_a_log_that_becomes_unwritable_ends_the_run_as_a_failure_result`（两处 `PermissionError: [Errno 13] Permission denied`） | 杀死 |
| I | fixture 形状校验的时机 | `cli/main.py`：`EventLog.start` 挪到 `load_fixture_provider` 之前 | 2 failed：`test_invalid_fixture_is_rejected`、`test_malformed_fixture_entry_is_rejected_before_any_session_log` | 杀死 |
| J | `context/assembled` 的 `turn_id` | `events/fold.py`：`assembled_payload` 不再写 `turn_id` | 1 failed：`test_context_assembled_carries_the_turn_id_it_belongs_to` | 杀死（只有一条测试守住，见注 6） |
| K | fixture 的 BOM | `provider/mock.py`：`utf-8-sig` → `utf-8` | 1 failed：`test_fixture_with_a_utf8_bom_runs` | 杀死 |
| L | replay 的折叠入参派生 | `cli/main.py`：`tool_descriptions=()` → 读 `records[index + 1]` 的 `model/request.payload["tools"]` | 1 failed：`test_replay_does_not_use_events_after_the_assembly_point` | 杀死 |
| M | 取消时写 `error/abort` | `loop/turn_loop.py`：`if cancel.is_set():` → `if False:` | 1 failed：`test_a_cancelled_turn_writes_an_error_abort_event` | 杀死 |
| N | 坏行的捕获范围 | `events/reader.py`：`except (json.JSONDecodeError, ValidationError)` → `except ValidationError` | 2 failed：`test_a_corrupt_line_is_a_log_read_failure`、`test_replay_of_a_corrupt_log_is_an_internal_error` | 杀死 |
| O | 已注册工具的派发结果 | `tools/dispatch.py`：`outcome="NOT_IMPLEMENTED"` → `outcome="OK"` | 1 failed：`test_a_registered_tool_is_dispatched_as_not_implemented_in_m1` | 杀死 |
| P | CLI 的内核失败映射 | `cli/main.py`：删掉 `_run` 里 `if outcome.stop_reason not in STOP_REASONS: return _report_failure(...)` | **59 passed，变异存活** | 存活 → 覆盖缺口 |
| P′ | 映射收进单点后再删判定 | `cli/main.py`：`exit_code_for` 里删掉词表外判定 | 1 failed：`test_a_log_layer_failure_outcome_maps_to_exit_code_one` | 杀死 |
| Q | Ctrl-C 处理器是否被装上 | `cli/main.py`：`_await_session` 里删掉 `signal.signal(signal.SIGINT, sigint_handler(cancel))` | 1 failed：`test_the_cli_installs_and_restores_the_sigint_handler` | 杀死 |

### 存活变异 P 的处理

删掉那条分支后 CLI 仍然以退出码 1 结束——`STOP_REASONS_TO_EXIT_CODES["LOG_WRITE_FAILED"]` 抛 `KeyError`、进程带 traceback 崩掉，退出码碰巧也是 1。当时没有任何测试断言「内核结果 → 退出码」这条映射对词表外的码也成立，也没有任何 CLI 测试覆盖 `LOG_WRITE_FAILED`（event-log spec 的「session 目录不可写」与 cli spec 的「日志不可写时只有 stderr」两条 Scenario 当时没有测试）。处理：

1. 把映射收进单点 `mini_harness.cli.main::exit_code_for(outcome)`，`_run` 只负责把失败码与 detail 写到 stderr。
2. 补 `tests/test_cli_run.py::test_a_log_layer_failure_outcome_maps_to_exit_code_one`（词表外的 `stop_reason` 映射到 1）——它杀死 P′。
3. 补 `tests/test_cli_run.py::test_unwritable_session_dir_is_a_log_write_failure`（CLI 黑盒：`--session-dir` 落在一个文件下面 → 退出码 1、stderr 含 `LOG_WRITE_FAILED` 与路径、没有 session 日志）。
4. 顺带补 `tests/test_cli_run.py::test_the_cli_installs_and_restores_the_sigint_handler`，它暴露出 Q 也是原本没测的东西。

还原实现后基线是 62 passed、mypy 干净。

### 这一轮剩下的已知缺口

`_run` 里「把内核失败的码与 detail 写到 stderr」这一支仍未被黑盒覆盖：M1 没有办法从 CLI 外部确定性地让日志在 run 中途变得不可写——session id 是随机的，把 session 目录设成只读只会让 `EventLog.start` 先失败（那条路径另有黑盒测试）。目前 seam ① 的 `test_a_log_that_becomes_unwritable_ends_the_run_as_a_failure_result` 覆盖结果本身、`exit_code_for` 的测试覆盖映射。M2 给 CLI 加更多 `--session-dir` 失败形状时应再补一条黑盒。

### 方法论注记（续）

6. **逐点重算的自一致性测不出词表缺失**：J 变异只让一条测试变红——replay 比对的是 `assembled_payload(turn_id, 重算)` 与记录 payload，两边同时少掉 `turn_id` 就仍然相等。要测「日志里到底写了什么」必须直接断言日志，不能只靠重放自洽。
7. **变异轮的还原会把未提交的实现一起 revert**：P′ 之后 `git checkout -- src/mini_harness/cli/main.py` 把当时尚未提交的 `exit_code_for` 也还原了，测试立刻在收集阶段报 `ImportError: cannot import name 'exit_code_for'`。跑变异轮之前先提交基线。
