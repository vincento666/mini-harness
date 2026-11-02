# Tasks

## 1. 初次同步与 snapshot 语义

- [x] 1.1 seam ⑥：`test_snapshot_precedes_only_new_frames`——snapshot.messages 首条是 system，证明它是模型上下文；没有单独造 tool/approval 全量场景
- [x] 1.2 seam ⑥：`test_snapshot_precedes_only_new_frames`——snapshot `last_seq` 后第一条 durable 是 `last_seq+1`
- [x] 1.3 seam ⑥：`test_the_event_stream_mixes_durable_and_delta_frames`——无 cursor 时从 seq 0 的 durable 开始

## 2. 游标边界

- [x] 2.1 seam ⑥：`test_a_cursor_resumes_without_gaps`——`from=3` 第一条 durable 是 4
- [x] 2.2 seam ⑥：`test_a_cursor_resumes_without_gaps`——`Last-Event-ID: 3` 与 `from=3` 等价
- [x] 2.3 seam ⑥：`test_a_delta_does_not_move_the_cursor`——delta 无 id、不推进游标
- [ ] 2.4 壳时：客户端按 seq 去重，重复 durable 不产生重复 UI 行（本 change 只定协议，不实现客户端）

## 3. durable 字段透出

- [x] 3.1 seam ⑥：`test_reasoning_delta_is_a_separate_ephemeral_frame`——`model/response.blocks` 顺序原样；interrupted 的 durable 形状由内核单测覆盖
- [ ] 3.2 内核/host 事件流未直接驱动 attempt（mock 无“先吐部分再失败”的 fixture）；attempt 字段透出由 `sse_frame` 的通用 durable 编码保证，测试留壳时补
- [x] 3.3 seam ⑥：`test_error_frame_preserves_code_and_detail`——`error/model` 的 code/detail 在 SSE 中原样

## 4. stream/end 与重连判定

- [x] 4.1 seam ⑥：`test_log_read_failure_sends_stream_end`——reason=error、code=LOG_UNREADABLE，无 id
- [ ] 4.2 物理断线的“没有 end”无法在断线后读；`test_a_disconnected_delta_reader_does_not_stop_the_segment` 只证明段继续、日志无 end。留壳时用真实客户端连接关闭验证
- [x] 4.3 seam ⑥：`test_session_end_sends_stream_end_without_id`——删除会话发 reason=session_ended，无 id、不落日志
- [ ] 4.4 壳时：客户端收到 end 不重连；无 end 断流按 last_seq 重连（本 change 只定协议）

## 5. 文档与 UAT

- [x] 5.1 文档：`docs/reference/host-streaming.md` 写清 snapshot/游标/end/无日志下载
- [x] 5.2 UAT 骨架：`docs/verification/host-event-sync-contract-uat.md`

## 6. 收尾四项

- [x] 6.1 真实端点验收：真实 reasoner 下 Web/SSE 首次全量 + 断线重连 + 业务终止，写进 `docs/verification/host-event-sync-contract-real-endpoint.md`
- [x] 6.2 UAT 验收（API 部分由用户授权代跑）：按 UAT 表填
- [x] 6.3 变异测试一轮：`from` 包含边界、snapshot 空 messages、会话结束不发 end；记进 `docs/verification/host-event-sync-contract-mutation.md`
- [x] 6.4 Learning Gate：L-068

## Workflow follow-up

- 归档后跑 `agents-md-slim`；本 change 只补协议，不改 UI/内核。
