# Chat streaming shell 变异测试

**日期**：2026-11-03。每个变异改源码、跑指定判据、记录红，再用编辑还原。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | 有 delta 又重复最终整段 | `_print_new_replies` 的 skip 分支改成 `pass` | `test_chat_stream_prints_text_deltas_without_repeating_final_content` | 红：stdout 出现两次 `你好` |
| M2 | reasoning 混进 stdout | `_ChatStreamRenderer.reasoning` 写 `sys.stdout` 而不是 stderr | `test_chat_stream_sends_reasoning_to_stderr_only` | 红：stdout 含 `先想` |
| M3 | 无 delta 回退被破坏 | `_print_new_replies` 对所有 stream turn 都跳过 | `test_chat_stream_falls_back_when_provider_sends_no_delta` | 红：stdout 只剩 `> > ` |

**结论**：3 个有效变异全部被杀死；还原后回到基线。
