# Tasks

## 1. 工具与子会话

- [ ] 1.1 seam ⑦：`test_subagent_writes_its_own_log`——子 session/start 带 entry=subagent/parent/depth
- [ ] 1.2 seam ⑦：`test_parent_log_has_only_tool_pair`——父只有 tool/call + tool/result
- [ ] 1.3 seam ⑦：`test_subagent_result_is_not_child_log`——结果是最终文本，不是子日志

## 2. 限制

- [ ] 2.1 seam ⑦：`test_depth_exceeded_is_a_result`
- [ ] 2.2 seam ⑦：`test_activation_limit_is_a_result`——第 9 个子代理
- [ ] 2.3 seam ⑦：`test_child_approval_is_unavailable`

## 3. 并发与取消

- [ ] 3.1 seam ⑦：`test_two_subagents_run_in_parallel`——wall-clock 小于串行
- [ ] 3.2 seam ⑦：`test_parent_cancel_cancels_child`
- [ ] 3.3 seam ⑦：`test_completed_child_result_survives_parent_cancel`

## 4. Host

- [ ] 4.1 seam ⑥：`test_session_view_has_parent_and_depth`
- [ ] 4.2 seam ⑥：`test_parent_sse_does_not_forward_child_events`

## 5. 文档与 UAT

- [ ] 5.1 文档：subagent 参考文档更新
- [ ] 5.2 UAT 骨架

## 6. 收尾四项 + DSH parity

- [ ] 6.1 真实端点验收
- [ ] 6.2 UAT 验收（人跑）
- [ ] 6.3 变异测试一轮
- [ ] 6.4 Learning Gate
- [ ] 6.5 DSH parity review：spawn/depth/capacity/approval/parallel/cancel 六项逐条对比，写 `docs/verification/m12-subagent-delegation-dsh-review.md`
