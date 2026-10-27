# Tasks

## 1. 装配抽成库（seam ② 与 ⑥）

- [x] 1.1 seam ②：红判据 `test_assemble_returns_a_prepared_for_a_mock_request`——`assemble(request, environ)` 返回 `Prepared`（provider / settings / log / registry 四样齐），临时目录里出现一份日志；实现 `session/assembly.py`，把 `cli/main.py::_prepare_or_fail` 的主体搬过去，`run` / `chat` / `serve` 改成调用它，既有 seam ⑥ 判据全绿
- [x] 1.2 seam ②：红判据 `test_assemble_failure_happens_before_any_log`——缺密钥、非法配置、未知工具名各返回 `Failure`，`session_dir.glob("*.jsonl") == []`；实现校验顺序（配置 → 窗口 → 工具 → provider/密钥 → 开日志）
- [x] 1.3 seam ⑥：守卫判据 `test_the_three_entries_still_write_the_same_payload`——`run` / `chat` / `serve` 的 `session/start` payload 与重构前逐字段相同（mock fixture）；只加判据，确认 1.1 没改行为

## 2. host 骨架、鉴权与健康（seam ⑥）

- [x] 2.1 seam ⑥：红判据 `test_host_starts_and_health_is_public`——无 token 启动 `minihns host --http --port <free>` 时退出码 2、stderr 含 `INVALID_ARGUMENT`、不建日志；带 `MINIHNS_HOST_TOKEN`（≥32 字符）启动后 `GET /health` 200、`{protocol: 1}`
- [x] 2.2 seam ⑥：红判据 `test_host_rejects_missing_or_wrong_token`——`GET /sessions` 无 token 401、错 token 401、对 token 200；错误信封是 `{"error": {"code": "UNAUTHORIZED", ...}}`
- [x] 2.3 seam ⑥：红判据 `test_a_foreign_origin_is_forbidden`——带 `Origin: https://example.com` 与正确 token 的 `POST /sessions` 返回 403；`Origin: null` 与同源放行
- [x] 2.4 seam ⑥：红判据 `test_host_can_bind_all_interfaces_with_a_token`——`--host 0.0.0.0` + token 能绑定；无 token 时启动已在上一条失败（只判绑定与 `/health`，不判外网可达）

## 3. 创建会话与资源上限（seam ⑥）

- [x] 3.1 seam ⑥：红判据 `test_create_session_writes_the_host_entry`——`POST /sessions`（mock fixture）返回 201、`session_id` 匹配 `^[0-9a-f]{32}$`，日志第一条 `session/start` 的 `entry` 为 `host`、`prompt` 为空串、其余设置与请求体一致
- [x] 3.2 seam ⑥：红判据 `test_a_bad_session_request_leaves_no_log`——非法配置、缺密钥、未知工具名各返回 400 且会话目录无新文件
- [x] 3.3 seam ⑥：红判据 `test_the_session_cap_is_enforced`——同时存在 4 个会话后第 5 个返回 429 `TOO_MANY_SESSIONS`，不建日志
- [x] 3.4 seam ⑥：红判据 `test_an_invalid_session_id_is_rejected`——`GET /sessions/../secret/events`、`GET /sessions/xyz` 都是 400，且不读任何日志

## 4. 消息、段与排队（seam ⑥ 与 ①）

- [x] 4.1 seam ⑥：红判据 `test_a_message_starts_a_segment`——`POST /messages` 返回 202，日志里 `user/message` 在 `segment/start` 与 `segment/end` 之间，段以 `MODEL_COMPLETED` 收尾、会话回到 `idle`
- [x] 4.2 seam ①：红判据 `test_a_second_message_queues_and_runs_after_the_first`——第一段进行中再 POST 一句，第二次 202 且 `queued` 为 true；第一段收尾后第二句开新段；日志里两段的 `segment_id` 连续、MUST NOT 交叉
- [x] 4.3 seam ⑥：红判据 `test_a_full_queue_is_rejected`——一段在跑、队列已有一句时第三句 429 `SESSION_BUSY`，不写 `user/message`
- [x] 4.4 seam ⑥：红判据 `test_an_empty_message_is_rejected`——空串/纯空白 400 `INVALID_ARGUMENT`，不写记录

## 5. 取消与关闭（seam ⑥ 与 ①）

- [x] 5.1 seam ①：红判据 `test_cancel_ends_only_the_segment`——段进行中 `POST /cancel` 后日志有 `error/abort` / `turn/end(ABORTED)` / `segment/end(ABORTED)`、会话仍 `idle`；再 POST 一句能正常跑完；预先排队的那条在取消后照常开新段（队列不被清空）
- [x] 5.2 seam ⑥：红判据 `test_cancel_on_an_idle_session_is_a_noop`——空闲时 cancel 返回 200，日志字节不变
- [x] 5.3 seam ⑥：红判据 `test_delete_closes_only_an_idle_session`——空闲 DELETE 返回 200、最后一条是 `session/end(MODEL_COMPLETED)`；段进行中 DELETE 409；重复 DELETE 404

## 6. 审批走 HTTP 回程（seam ② 与 ⑥）

- [x] 6.1 seam ②：红判据 `test_the_approval_gate_receives_the_tool_call_id`——`ApprovalGate.request` 收到 `tool_call_id`；`StdinApprovalGate` 行为不变；host 门在测试里用 future 实现
- [x] 6.2 seam ⑥：红判据 `test_host_approves_a_write_over_http`——段因 `write` 停住，`POST /approvals/{tool_call_id}`（approve）返回 200，日志写 `approval/response(APPROVED)`、`tool/result` 为 `OK`，段收尾
- [x] 6.3 seam ⑥：红判据 `test_host_denies_a_write_over_http`——同一形状 deny 后 `approval/response(DENIED)`、该调用 `DENIED_BY_APPROVAL`、段 `FENCE_DENIED`、会话 `idle`
- [x] 6.4 seam ②：红判据 `test_an_unknown_or_expired_approval_is_a_result`——未知 `tool_call_id` 返回 404；超时（测试注入 0.1 s）塌成 `UNAVAILABLE`、写 `approval/response(UNAVAILABLE)`，不默认批准
- [x] 6.5 seam ②：红判据 `test_the_host_gate_never_reads_stdin`——stdin 是可读的 tty 替身、没有任何 HTTP 应答时，门只等 future，不消费 stdin

## 7. 事件流与 snapshot（seam ⑥ 与 ④）

- [x] 7.1 seam ⑥：红判据 `test_host_frames_equal_the_log`——会话跑完后从 0 读 SSE，帧数等于日志行数，逐帧 `data` 与记录相等
- [x] 7.2 seam ④：红判据 `test_a_cursor_resumes_without_gaps`——`?from=3` 与 `Last-Event-ID: 3` 都从 `seq=4` 起；`0` 合法；负数与非整数 400 且会话不受影响
- [x] 7.3 seam ⑥：红判据 `test_snapshot_precedes_only_new_frames`——已有 10 条记录时 `?snapshot=1` 的第一帧是 `snapshot`、`last_seq` 为 9，之后只送 `seq > 9`
- [x] 7.4 seam ⑥：红判据 `test_a_disconnect_does_not_change_the_session`——读几帧就断开，会话继续跑完，日志与没有客户端时逐字节相同

## 8. 生命周期与退出（seam ⑥）

- [x] 8.1 seam ⑥：红判据 `test_host_outlives_a_session`——一个会话收尾后 `GET /health` 仍 200、`GET /sessions` 仍列出它
- [x] 8.2 seam ⑥：红判据 `test_sigint_cancels_all_segments_and_writes_session_end`——段进行中发 SIGINT，日志有 `error/abort` / `turn/end(ABORTED)` / `segment/end(ABORTED)` / `session/end`，进程退出码 0（Windows 上 `skipif`，Linux 跑）
- [x] 8.3 seam ⑥：红判据 `test_shutdown_leaves_no_orphan_session`——两个会话同时在跑时 SIGINT，两份日志都以 `session/end` 收尾，没有半条记录

## 9. 安全与错误信封（seam ⑥）

- [x] 9.1 seam ⑥：红判据 `test_every_host_error_uses_the_envelope`——401 / 403 / 404 / 409 / 429 各返回对应状态与 `code`，`detail` 不含 token、密钥或完整日志行
- [x] 9.2 seam ⑥：红判据 `test_danger_full_access_needs_the_server_flag`——请求体要 `danger-full-access` 而服务器未给 `--allow-danger-full-access` 时 400，不建日志；给了之后允许
- [x] 9.3 seam ⑥：红判据 `test_the_token_never_reaches_the_log`——创建/发消息/审批各一次后，整份日志里搜不到 token 的前 8 个字符
- [x] 9.4 seam ⑥：红判据 `test_auto_approval_needs_the_server_flag`——请求体 `approval: "auto"` 而服务器未给 `--allow-auto-approval` 时 400、不建日志；给了之后 `write` 直接 `OK` 且日志没有 `approval/*`

## 10. 完成判据、文档与收尾

- [x] 10.1 seam ⑥：完成判据——一条黑盒脚本：创建会话 → 发两句话（第二句排队）→ 批准一次写 → 取消一回合 → `?snapshot=1` 重连，帧与日志逐字段相等、`session/start.entry` 为 `host`
- [x] 10.2 文档：用 `domain-modeling` 写 ADR-0031（常驻多会话 HTTP + SSE + token 的取舍与代价），把 `host` / `snapshot` / `approval 门` 三个词写进 `GLOSSARY.md`；ADR-0002 的 H1 那一堆逐条核对——已处理的写「已处理（H1）」，没处理的改判到 H2 / M11 并写原因，不许整堆勾掉
- [ ] 10.3 真实端点验收：用真实端点跑 10.1 的脚本（写一个文件、批准一次、取消一次），观察记进 `docs/verification/h1-host-session-api-real-endpoint.md`
- [ ] 10.4 UAT 验收（人跑）：按 `docs/verification/h1-host-session-api-uat.md` 的场次，人坐在终端/浏览器前拿它办一件真事，填完观察表；tty 场次 agent 不得代跑（ADR-0025）
- [ ] 10.5 变异测试一轮：改坏 host 的实现（鉴权跳过、队列不排队、审批默认批准、snapshot 的 `last_seq` 错、DELETE 允许 running 各一处），跑全量，把「变异 / 改法 / 哪些测试变红」记进 `docs/verification/h1-host-session-api-mutation.md`，还原前先看 `git status`
- [ ] 10.6 Learning Gate：扫本轮证据，把可复用教训写进 `docs/lessons.md` 收件箱；无可复用信号就写 `NO-PROMOTION`
