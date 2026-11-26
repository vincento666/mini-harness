# Tasks

## 1. 初次同步与 snapshot 语义

- [x] 1.1 seam ⑥：`test_snapshot_precedes_only_new_frames`——snapshot.messages 首条是 system，证明它是模型上下文
- [x] 1.2 seam ⑥：`test_snapshot_precedes_only_new_frames`——snapshot `last_seq` 后第一条 durable 是 `last_seq+1`
- [x] 1.3 seam ⑥：`test_the_event_stream_mixes_durable_and_delta_frames`——无 cursor 时从 seq 0 的 durable 开始

## 2. 游标边界

- [x] 2.1 seam ⑥：`test_a_cursor_resumes_without_gaps`——`from=3` 第一条 durable 是 4
- [x] 2.2 seam ⑥：`test_a_cursor_resumes_without_gaps`——`Last-Event-ID: 3` 与 `from=3` 等价
- [x] 2.3 seam ⑥：`test_a_delta_does_not_move_the_cursor`——delta 无 id、不推进游标

## 3. durable 字段透出

- [x] 3.1 seam ⑥：`test_reasoning_delta_is_a_separate_ephemeral_frame`——`model/response.blocks` 顺序原样
- [x] 3.2 seam ⑥：`test_error_frame_preserves_code_and_detail`——`error/model` 的 code/detail 在 SSE 中原样

## 4. stream/end

- [x] 4.1 seam ⑥：`test_log_read_failure_sends_stream_end`——reason=error、code=LOG_UNREADABLE，无 id
- [x] 4.2 seam ⑥：`test_session_end_sends_stream_end_without_id`——删除会话发 reason=session_ended，无 id、不落日志

## 5. 文档与 UAT

- [x] 5.1 文档：`docs/reference/host-streaming.md` 写清 snapshot/游标/end/无日志下载
- [x] 5.2 UAT 骨架：`docs/verification/host-event-sync-contract-uat.md`

## 6. 收尾四项

- [x] 6.1 真实端点验收：真实 reasoner 下 Web/SSE 首次全量 + 断线重连 + 业务终止，写进 `docs/verification/host-event-sync-contract-real-endpoint.md`
- [x] 6.2 UAT 验收（API 部分由用户授权代跑）：按 UAT 表填
- [x] 6.3 变异测试一轮：`from` 包含边界、snapshot 空 messages、会话结束不发 end；记进 `docs/verification/host-event-sync-contract-mutation.md`
- [x] 6.4 Learning Gate：L-068

## Workflow follow-up

- 归档后跑 `agents-md-slim`；本 change 只补 Host 协议，客户端去重/重连、物理断线 wire 验证移到壳时。
