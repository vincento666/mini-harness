# Tasks

## 1. Blocks 契约与旧投影

- [ ] 1.1 seam ⑤：红判据 `test_assistant_turn_keeps_block_order`——reasoning/text/tool-call 交错保序；实现 `Block` 判别联合与 `AssistantTurn.blocks`
- [ ] 1.2 seam ⑤：红判据 `test_old_content_projection_is_derived_from_blocks`——`content`/`tool_calls` 是投影，不是第二真源；旧 provider 只有 content 时是一个 text 块
- [ ] 1.3 seam ④：守卫——没有 blocks 的旧 fixture / 旧日志行为逐点不变

## 2. Provider 解析与 sink 分流

- [ ] 2.1 seam ⑤：红判据 `test_reasoning_delta_does_not_reach_the_text_sink`——reasoning 只进 reasoning sink，正文只进 text sink；实现 `ReasoningSink`
- [ ] 2.2 seam ⑤：红判据 `test_mock_fixture_can_emit_reasoning_deltas`——fixture 可声明 reasoning deltas；mock 按顺序发
- [ ] 2.3 seam ⑤：红判据 `test_openai_compat_maps_reasoning_content`——`reasoning_content`/thinking 解析成 reasoning blocks，usage 带 reasoning_tokens
- [ ] 2.4 seam ⑤：红判据 `test_unsupported_reasoning_effort_fails_before_io`——`ultra` 在网络前失败 `UNSUPPORTED_REASONING_EFFORT`；`off` 不发 thinking
- [ ] 2.5 seam ⑤：红判据 `test_incomplete_reasoning_tag_is_a_schema_failure`——只有开/闭标签、嵌套、流结束未闭合都 `PROVIDER_SCHEMA_INVALID`，无 `model/response`；跨 chunk 成对标签成功
- [ ] 2.6 seam ⑤：红判据 `test_empty_reasoning_is_dropped_and_reasoning_only_keeps_blocks`——空 delta 不 emit；仅 reasoning 时 content 投影为空，不冒充正文

## 3. 回合循环与 durable response

- [ ] 3.1 seam ①：红判据 `test_turn_loop_writes_blocks_to_one_response`——一次成功调用只写一条 `model/response`，blocks 保序
- [ ] 3.2 seam ①：红判据 `test_reasoning_delta_is_not_logged`——`reasoning/delta` 不写日志，只有最终 response
- [ ] 3.3 seam ①：守卫——取消/失败不写半条 response；无 reasoning 的日志与今天逐点相同
- [ ] 3.4 seam ①：红判据 `test_reasoning_tokens_are_a_subset_of_output`——usage 加 reasoning_tokens，计量不重复加

## 4. fold / replay

- [ ] 4.1 seam ④：红判据 `test_fold_rebuilds_ordered_blocks`——fold 从 blocks 重建 reasoning/text/tool-call 顺序
- [ ] 4.2 seam ④：红判据 `test_old_logs_without_blocks_still_replay_pointwise`——旧日志退化路径逐点相等
- [ ] 4.3 seam ④：红判据 `test_provider_history_carries_blocks`——后续请求按块回传；不支持块回传的适配器显式降级

## 5. SSE / host

- [ ] 5.1 seam ⑥：红判据 `test_sse_has_reasoning_delta_and_model_delta`——两者分开、无 durable id、顺序正确
- [ ] 5.2 seam ⑥：红判据 `test_reasoning_delta_is_not_logged_in_sse_snapshot`——snapshot 不重放 delta；最终 response 带 blocks
- [ ] 5.3 seam ⑥：守卫——没有 reasoning 的模型 SSE 与今天逐点相同

## 6. 文档与 UAT

- [ ] 6.1 文档：更新 `docs/reference/reasoning-mode.md` 的已实现章节与 `docs/contracts/`（若有 assistant message 形状）
- [ ] 6.2 UAT 骨架：`docs/verification/reasoning-mode-and-budget-uat.md`（propose 时立；人跑）

## 7. 收尾四项

- [ ] 7.1 真实端点验收：真实 reasoner 一次长回复，reasoning → tool-call → reasoning → text 可重放；写进 `docs/verification/reasoning-mode-and-budget-real-endpoint.md`
- [ ] 7.2 UAT 验收（人跑）：按 `docs/verification/reasoning-mode-and-budget-uat.md` 填表
- [ ] 7.3 变异测试一轮：改坏「reasoning 写日志」「reasoning 混进正文」「reasoning tokens 重复计」各一处，记进 `docs/verification/reasoning-mode-and-budget-mutation.md`
- [ ] 7.4 Learning Gate：扫证据写 `docs/lessons.md` 收件箱；无可复用信号写 `NO-PROMOTION`

## Workflow follow-up

- 归档后跑 `agents-md-slim`；M10 已完成，本 change 之后进入 M11/M12。
