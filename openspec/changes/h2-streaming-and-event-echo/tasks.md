# Tasks

## 1. Provider 契约与 mock 增量

- [x] 1.1 seam ⑤：红判据 `test_generate_without_a_sink_is_unchanged`——同一 fixture 带/不带 `on_delta` 跑，`model/response`/`tool/*` 序列逐点相同，且不带 sink 时没有 delta；实现 `Provider.generate(..., on_delta=None)`，无 sink 走原路径
- [x] 1.2 seam ⑤：红判据 `test_mock_emits_fixture_deltas`——fixture 条目声明 `deltas: ["你","好"]`，sink 依次收到两段、最终 `content` 为 `你好`；实现 mock 的可选 `deltas`
- [x] 1.3 seam ⑤：守卫判据——旧 fixture（没有 `deltas`）不产生任何增量，既有 mock 判据全绿

## 2. OpenAI 兼容适配器的流式解析

- [x] 2.1 seam ⑤：红判据 `test_openai_stream_content_deltas`——假端点发 `data: {"choices":[{"delta":{"content":"你"}}]}` 等，sink 收到增量、`AssistantTurn.content` 是拼接结果；实现 `stream: true` 与 `data:` / `[DONE]` 解析
- [ ] 2.2 seam ⑤：红判据 `test_openai_stream_tool_calls_are_assembled_by_index`——分片给两个 `tool_calls` 的 id/name/arguments，最终 `tool_calls` 是两条完整调用，工具参数片段不进正文 sink
- [ ] 2.3 seam ⑤：红判据 `test_openai_stream_usage_may_be_missing`——没有 usage 块时 `Usage` 为零值、不失败；`stream_options` 被端点拒绝时退回不带它
- [ ] 2.4 seam ⑤：红判据 `test_a_stream_that_breaks_before_done_is_a_result`——首 delta 后连接中断返回 `PROVIDER_ERROR`，不抛未捕获异常、不产生半条 `model/response`

## 3. 重试边界与取消

- [ ] 3.1 seam ⑤：红判据 `test_retry_only_before_the_first_delta`——首 delta 前 429 仍重试一次并写 `model/retry`；首 delta 后再 429/5xx 不重试、不写 `model/retry`、塌成 `PROVIDER_ERROR`
- [ ] 3.2 seam ①：红判据 `test_cancel_during_stream_aborts_without_a_response`——流式读取中置位取消，回合以 `ABORTED` 收尾，不写 `model/response`，已发 delta 不回滚

## 4. 宿主侧 delta 广播

- [ ] 4.1 seam ①：红判据 `test_the_turn_loop_passes_a_delta_sink_to_the_provider`——`SessionEnv` 带 sink 时 provider 收到同一个回调；sink 收到的文本不写日志
- [ ] 4.2 seam ①：红判据 `test_host_session_broadcasts_deltas_to_subscribers`——`HostSession` 的订阅者队列按顺序收到 `{turn_id,index,text}`；没有订阅者时不影响回合
- [ ] 4.3 seam ⑥：红判据 `test_a_slow_delta_subscriber_drops_old_deltas`——有界队列满时丢最旧 delta，不阻塞 provider；durable 帧不受影响

## 5. SSE 合流与协议

- [ ] 5.1 seam ⑥：红判据 `test_the_event_stream_mixes_durable_and_delta_frames`——真实子进程 + httpx：`model/request`（durable）→ 若干无 `id` 的 `model/delta` → `model/response`（durable）；日志里没有 delta
- [ ] 5.2 seam ⑥：红判据 `test_a_delta_does_not_move_the_cursor`——`model/delta` 不参与 `Last-Event-ID`/`?from=`；snapshot 的 `last_seq` 只由 durable 记录推进
- [ ] 5.3 seam ⑥：红判据 `test_reconnect_does_not_replay_lost_deltas`——中途断开再带 `snapshot=1` 重连，丢掉的 delta 不补，最终 `model/response` 只出现一次
- [ ] 5.4 seam ⑥：红判据 `test_health_advertises_delta`——`GET /health` 返回 `protocol: 1` 与 `features: ["delta"]`
- [ ] 5.5 seam ⑥：红判据 `test_a_disconnected_delta_reader_does_not_stop_the_segment`——delta 读者断开后段继续跑完，日志与没有客户端时逐字节相同

## 6. Replay 与既有行为守卫

- [ ] 6.1 seam ④：红判据 `test_replay_is_equal_with_and_without_streaming`——同一 fixture 的流式/非流式两份日志，`replay` 都退出码 0，`model/response`/`tool/*`/`turn/*` 逐点相等
- [ ] 6.2 seam ⑥：守卫判据——既有 `serve`/`run`/`chat` 的非流式判据全绿；`session/start` payload 不变

## 7. 文档与 UAT

- [ ] 7.1 文档：修订 ADR-0006 的「非流式」收窄为「默认非流式、H2 起可选流式」；把 `model/delta` / ephemeral 的取舍写进 ADR-0032 的后果或补记
- [ ] 7.2 UAT 骨架已在 propose 时立好 `docs/verification/h2-streaming-and-event-echo-uat.md`；跑完由人填观察表

## 8. 收尾四项

- [ ] 8.1 真实端点验收：真实 deepseek 跑 S1/S2/S3/S4，记录进 `docs/verification/h2-streaming-and-event-echo-real-endpoint.md`
- [ ] 8.2 UAT 验收（人跑）：按 `docs/verification/h2-streaming-and-event-echo-uat.md` 填观察表；tty/浏览器场次 agent 不得代跑（ADR-0025）
- [ ] 8.3 变异测试一轮：至少改坏「首 delta 前/后重试边界」「delta 是否写日志」「snapshot 后是否补 delta」各一处，记进 `docs/verification/h2-streaming-and-event-echo-mutation.md`
- [ ] 8.4 Learning Gate：扫本轮证据写进 `docs/lessons.md` 收件箱；无可复用信号写 `NO-PROMOTION`

## Workflow follow-up

- 归档后跑 `agents-md-slim`；`code-review` 两轴在变异之前跑。
