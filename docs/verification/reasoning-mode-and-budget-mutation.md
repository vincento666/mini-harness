# Reasoning 模式变异测试

**日期**：2026-11-01。每个变异改源码、跑指定判据、记录红，再用 `git checkout -- <file>` 还原。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | reasoning 写日志 | 在 `model/response` 前追加 `("reasoning/delta", ...)` | `test_reasoning_delta_is_not_logged` | 红：日志里出现 `reasoning/delta`（被事件词表改写成 error/internal，仍是 durable 证据） |
| M2 | reasoning 混进正文 | `_capture_sinks` 的 reasoning 包装同时调用正文 sink | `test_reasoning_does_not_reach_the_text_sink` | 红：正文 sink 多出 reasoning 文本 |
| M3 | reasoning tokens 重复计 | `_usage_from` 的 `output_tokens` 再加 `reasoning_tokens` | `test_nonstream_reasoning_content_becomes_a_reasoning_block` | 红：`output_tokens=13` 而不是 8 |

**结论**：3 个有效变异全部被杀死；还原后回到基线。
