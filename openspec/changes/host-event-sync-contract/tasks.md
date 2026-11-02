# Tasks

## 1. 初次同步与 snapshot 语义

- [x] 1.1 seam ⑥：红判据 `test_snapshot_is_a_message_baseline_not_ui_transcript`——snapshot.messages 只含模型上下文；有 tool/approval 记录时不冒充 UI 全量
- [x] 1.2 seam ⑥：红判据 `test_snapshot_then_events_resume_after_last_seq`——snapshot `last_seq=42` 后第一条 durable 是 43，不重发
- [x] 1.3 seam ⑥：红判据 `test_initial_events_without_cursor_start_at_seq_zero`——无 from/Last-Event-ID 时 seq 0 出现

## 2. 游标边界

- [x] 2.1 seam ⑥：红判据 `test_from_cursor_is_exclusive`——`from=7` 第一条 durable 是 8
- [x] 2.2 seam ⑥：红判据 `test_last_event_id_has_the_same_semantics`——header 与 `from` 等价
- [x] 2.3 seam ⑥：红判据 `test_only_durable_frames_carry_id_and_move_cursor`——delta 无 id、不推进
- [x] 2.4 seam ⑥：守卫——客户端按 seq 去重，重复 durable 不产生重复 UI 行

## 3. durable 字段透出

- [x] 3.1 seam ⑥：红判据 `test_sse_preserves_blocks_and_interrupted`——`model/response.blocks` 顺序与 interrupted 原样
- [x] 3.2 seam ⑥：红判据 `test_sse_preserves_model_attempt`——attempt 透出，但客户端不把它当 assistant 历史
- [x] 3.3 seam ⑥：红判据 `test_sse_preserves_error_code_and_detail`

## 4. stream/end 与重连判定

- [x] 4.1 seam ⑥：红判据 `test_log_read_failure_emits_stream_end_before_close`——reason=error、code=LOG_UNREADABLE，无 id、不落日志
- [x] 4.2 seam ⑥：红判据 `test_physical_disconnect_has_no_stream_end`——客户端断开不产生 `stream/end`
- [x] 4.3 seam ⑥：红判据 `test_session_end_emits_session_ended`——若可观察，发 reason=session_ended
- [x] 4.4 seam ⑥：守卫——客户端收到 end 不重连；无 end 断流按 last_seq 重连

## 5. 文档与 UAT

- [x] 5.1 文档：`docs/reference/host-streaming.md` 写清 snapshot/游标/end/无日志下载
- [x] 5.2 UAT 骨架：`docs/verification/host-event-sync-contract-uat.md`

## 6. 收尾四项

- [x] 6.1 真实端点验收：真实 reasoner 下 Web/SSE 首次全量 + 断线重连 + 业务终止，写进 `docs/verification/host-event-sync-contract-real-endpoint.md`
- [x] 6.2 UAT 验收（人跑）：按 UAT 表填
- [x] 6.3 变异测试一轮：改坏「from 包含边界」「snapshot 当 UI 全量」「物理断线发 end」各一处，记进 `docs/verification/host-event-sync-contract-mutation.md`
- [x] 6.4 Learning Gate：扫证据写 `docs/lessons.md` 收件箱；无可复用信号写 `NO-PROMOTION`

## Workflow follow-up

- 归档后跑 `agents-md-slim`；本 change 只补协议，不改 UI/内核。
