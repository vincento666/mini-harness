# H2 变异测试（2026-10-28）

**目的**：确认 H2 的判据能杀死「可观察行为」的改坏，而不是只覆盖 happy path。每个变异都先改源码、跑指定判据、记录红，再用 `git checkout -- <file>` 还原；还原后 `git status` 只剩 `docs/tools` 的既有未跟踪脚本。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | snapshot 后重放旧 durable | `cli/host.py` 里 snapshot 的 `after = last_seq` 改成 `after = 0` | `test_snapshot_precedes_only_new_frames` | 红：snapshot 后第一帧 `id` 是 1，不是 `last_seq+1` |
| M2 | delta 带 id | `_delta_frame` 在 `event: model/delta` 前加 `id: 0` | `test_the_event_stream_mixes_durable_and_delta_frames` | 红：delta 帧出现 `id` |
| M3 | 慢读者不丢旧 delta | `session/host.py` 把 `if queue.full():` 改成 `if False:` | `test_a_slow_delta_subscriber_drops_old_deltas` | 红：队列仍 256，首条 `index` 是 0 而不是 5 |
| M4 | 首 delta 前不重试 | `provider/openai_compat.py` 把 `if _retryable(...) and not attempts:` 改成 `if False:` | `test_stream_retries_429_before_first_delta` | 红：429 后直接失败，没有第二次请求 |

**无效变异（不计入）**：在 `publish_delta` 里直接 `self.log.append("model/delta", frame)`，host 在 `/health` 前就起不来（`model/delta` 不是日志事件词表成员），无法判断是判据杀死还是启动失败；这不是有效变异，已还原。

**结论**：4 个有效变异全部被至少一条判据杀死；还原后工作树干净（除 `docs/tools` 既有未跟踪脚本）。没有存活变异需要补判据。
