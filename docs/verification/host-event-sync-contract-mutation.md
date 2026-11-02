# Host event sync 变异测试

**日期**：2026-11-02。每个变异改源码、跑指定判据、记录红，再用 `git checkout -- <file>` 还原。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | `from` 变成包含边界 | `reader.py` 的 `record.seq > after` 改成 `>=` | `test_a_cursor_resumes_without_gaps` | 红：`from=3` 第一条是 3 而不是 4 |
| M2 | snapshot 不再带消息基线 | snapshot 的 `messages` 改成 `[]` | `test_snapshot_precedes_only_new_frames` | 红：`messages[0]` 不存在 |
| M3 | 会话结束不发终止帧 | 删掉 `stream_ended` 分支 | `test_session_end_sends_stream_end_without_id` | 红：客户端等不到 `stream/end`，ReadTimeout |

**结论**：3 个有效变异全部被杀死；还原后回到基线。
