# M10 压缩参数变异测试

**日期**：2026-10-29。每个变异改源码、跑指定判据、记录红，再用 `git checkout -- <file>` 还原。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | `retain_tokens` 不覆盖 ratio | `budget.py` 的 `if retain_tokens > 0:` 改成 `if False:` | `test_retain_line_prefers_tokens_and_falls_back_to_ratio` | 红：`retain_line(100000, .10, 3000)` 返回 10000 而不是 3000 |
| M2 | ratio 边界放过 0 | `assembly.py` 的 `0 < value <= 1` 改成 `0 <= value <= 1` | `test_compaction_ratio_out_of_range_fails_before_a_session` | 红：`compaction_retain_ratio=0` 的 run 退出 0，而不是 2 |
| M3 | payload 不记录 `compaction_retain_ratio` | `turn_loop.py` 的 payload 键改成 `compaction_retain_ratio_disabled` | `test_compaction_config_reaches_the_session_start_payload` | 红：payload 缺 `compaction_retain_ratio`，测试 KeyError |

**结论**：3 个有效变异全部被杀死；还原后工作树只剩 `docs/tools` 的既有未跟踪脚本。
