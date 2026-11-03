# Tasks

## 1. flag 与 sink 注入

- [x] 1.1 seam ⑥：红判据 `test_chats_flag_table_is_runs_flag_table_minus_two`——`--stream --no-stream` 退出 2；默认 `stream=True`
- [x] 1.2 seam ⑥：红判据 `test_chat_stream_wires_delta_and_reasoning_sinks`——`--stream` 时 `SessionEnv` 有 on_delta/on_reasoning；`--no-stream` 没有
- [x] 1.3 seam ⑥：守卫——`--no-stream` 的 stdout/日志/退出码与今天逐点相同
- [x] 1.4 代码审查守卫：`ChatStreamRenderer` 只依赖 `on_delta`/`on_reasoning`/stdout/stderr，不引用 host SSE、cursor、queue

## 2. 输出渲染

- [x] 2.1 seam ⑥：红判据 `test_chat_stream_prints_text_deltas_to_stdout`——fixture `deltas` 按顺序出现在 stdout，提示符不重复
- [x] 2.2 seam ⑥：红判据 `test_chat_stream_prints_reasoning_to_stderr`——reasoning 只在 stderr，带 `[thinking]`；stdout 不含思考
- [x] 2.3 seam ⑥：红判据 `test_chat_stream_does_not_repeat_final_content`——有 delta 的 turn 结束后不再打印整段
- [x] 2.4 seam ⑥：红判据 `test_chat_stream_falls_back_when_no_delta`——无 delta 时打印最终正文，不留空输出
- [x] 2.5 seam ⑥：红判据 `test_chat_stream_keeps_partial_output_on_cancel`——取消保留已显示正文，不追加最终整段

## 3. 文档与 UAT

- [x] 3.1 文档：`chat-repl` / `chat-streaming` 的 stdout/stderr 约束与 flag 写清；`docs/reference/host-streaming.md` 区分 host SSE 与 chat shell
- [x] 3.2 UAT 骨架：`docs/verification/chat-streaming-shell-uat.md`（propose 时立；人跑）

## 4. 收尾四项

- [x] 4.1 真实端点验收：真实 reasoner `chat --stream` 看正文/思考分流与取消，写进 `docs/verification/chat-streaming-shell-real-endpoint.md`
- [x] 4.2 UAT 验收（人跑）：按 UAT 表填
- [x] 4.3 变异测试一轮：改坏「deltas 重复打印」「reasoning 进 stdout」「取消后补整段」各一处，记进 `docs/verification/chat-streaming-shell-mutation.md`
- [x] 4.4 Learning Gate：扫证据写 `docs/lessons.md` 收件箱；无可复用信号写 `NO-PROMOTION`

## Workflow follow-up

- 归档后跑 `agents-md-slim`；本 change 依赖 `reasoning-mode-and-budget` 的 reasoning sink，后者的 R2 视觉 UAT 仍等壳。
