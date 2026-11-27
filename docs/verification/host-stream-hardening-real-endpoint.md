# host-stream-hardening — 真实端点验收

**日期**：2026-11-27。**端点**：OpenRouter `qwen/qwen3.8-27b`（`docs/reference/verification-endpoint.md` 的指定验证端点；密钥读进程环境，不进日志）。

**判据**：起 Host 跑一场真实会话，SSE 客户端收帧序列正常；`stream/end` 不出现在 durable 重放里。

## 场次：`minihns host --http` + SSE 探针

会话 `19c0c50fa9dc4b639bab305f6ae57867`（`.tmp/uat-reasoning3/ws`，探针脚本 `.tmp/uat-reasoning3/probe.py`：POST `/sessions` → 先订阅 `GET /sessions/{id}/events` → POST `/sessions/{id}/messages` → 读到 `turn/end` 收）。

帧序列（事件名）：`session/start → turn/start → user/message → step/start → context/assembled → model/request → reasoning/delta × 59 → model/delta × 42 → model/response → step/end → turn/end`。

- 帧序正常：durable 帧带 `id` 逐条递增，ephemeral 两条流（思考先、正文后）按 `step_id` 归属。
- 该会话**没有**触发 Host 主动终止（没删会话、日志没读不动），所以流里没有 `stream/end`——符合「物理断线/正常收尾不发帧」的语义。
- durable 日志逐行 grep：`stream/end` **0 命中**、`reasoning/delta` **0 命中**、`model/delta` **0 命中**。判据「不出现在 durable 重放里」成立。
- `stream/end` 的两条主动终止路径各有黑盒判据钉着：host 侧 `test_a_broken_log_sends_stream_end_on_reconnect`（LOG_UNREADABLE）与删除会话的 `session_ended` 帧；serve 侧 `test_a_corrupt_log_line_ends_the_stream_with_stream_end`（进程内直测 `ServeServer`——坏行进真会话会把下一次装配一并带走，那是「坏行终止会话」的既有语义，不能拿来当传输层判据）。

## 结论与边界

- 三条防御性条款中，`stream/end` 的实现缺口（host + serve 两端）已收口并被变异钉住；snapshot 边界与「不提供原始日志下载」是纯追认，判据已落（`test_snapshot_messages_are_the_model_context_not_the_control_plane`、`test_no_log_download_route`）。
- 真端点这一场只覆盖「正常收尾」形状；`stream/end` 的两条终止路径是黑盒判据覆盖的，真端点没人为造一次日志读不动（那需要破坏持久化，冒充不了也不会去做）。
