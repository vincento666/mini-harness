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
