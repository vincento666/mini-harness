# Tasks

## 1. flag 与 sink 注入

- [x] 1.1 seam ⑥：红判据 `test_chat_stream_flag_is_mutually_exclusive`——`--stream --no-stream` 退出 2；默认 `stream=False`
- [x] 1.2 seam ⑥：红判据 `test_chat_stream_wires_delta_and_reasoning_sinks`——`--stream` 时 `SessionEnv` 有 on_delta/on_reasoning；`--no-stream` 没有
- [x] 1.3 seam ⑥：守卫——`--no-stream` 的 stdout/日志/退出码与今天逐点相同
- [ ] 1.4 seam ⑥：红判据 `test_chat_stream_renderer_is_a_cli_adapter`——renderer 只依赖 sink/输出流，不引用 host 的 SSE/cursor/queue；chat `_chat` 不出现 host 分支

## 2. 输出渲染

- [x] 2.1 seam ⑥：红判据 `test_chat_stream_prints_text_deltas_to_stdout`——fixture `deltas` 按顺序出现在 stdout，提示符不重复
- [x] 2.2 seam ⑥：红判据 `test_chat_stream_prints_reasoning_to_stderr`——reasoning 只在 stderr，带 `[thinking]`；stdout 不含思考
- [x] 2.3 seam ⑥：红判据 `test_chat_stream_does_not_repeat_final_content`——有 delta 的 turn 结束后不再打印整段
- [x] 2.4 seam ⑥：红判据 `test_chat_stream_falls_back_when_no_delta`——无 delta 时打印最终正文，不留空输出
- [x] 2.5 seam ⑥：红判据 `test_chat_stream_keeps_partial_output_on_cancel`——取消保留已显示正文，不追加最终整段
- [ ] 2.6 seam ⑥：守卫——同一 fixture 的 host SSE 与 chat stream 规范化后 `context/assembled` / `model/response` 一致（只排除 `entry` 与传输帧）；chat 不复制 host 的 snapshot/cursor

## 3. 文档与 UAT

- [x] 3.1 文档：`chat-repl` / `chat-streaming` 的 stdout/stderr 约束与 flag 写清；`docs/reference/host-streaming.md` 区分 host SSE 与 chat shell
- [x] 3.2 UAT 骨架：`docs/verification/chat-streaming-shell-uat.md`（propose 时立；人跑）

## 4. 收尾四项

- [x] 4.1 真实端点验收：真实 reasoner `chat --stream` 看正文/思考分流与取消，写进 `docs/verification/chat-streaming-shell-real-endpoint.md`
- [ ] 4.2 UAT 验收（人跑）：按 UAT 表填
- [x] 4.3 变异测试一轮：改坏「deltas 重复打印」「reasoning 进 stdout」「取消后补整段」各一处，记进 `docs/verification/chat-streaming-shell-mutation.md`
- [x] 4.4 Learning Gate：扫证据写 `docs/lessons.md` 收件箱；无可复用信号写 `NO-PROMOTION`

## Workflow follow-up

- 归档后跑 `agents-md-slim`；本 change 依赖 `reasoning-mode-and-budget` 的 reasoning sink，后者的 R2 视觉 UAT 仍等壳。
