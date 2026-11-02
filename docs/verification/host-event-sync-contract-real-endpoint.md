# Host event sync 真实端点验收

**日期**：2026-11-02。**端点**：DeepSeek `deepseek-reasoner`（真实 key，不进日志）。
**Host**：`127.0.0.1:10886`，session `e10dbb4c2c7d40abaa8ab13df863ab2a`。

## 观察

- 首次连接（无 cursor）：从 `segment/start` 起收到完整 durable；`reasoning/delta` 与 `model/delta` 都是 ephemeral，无 `id`。
- 最终 `model/response`：
  - blocks：`reasoning, text`
  - usage：`input_tokens=1182`、`output_tokens=124`、`reasoning_tokens=20`
  - `last_seq=6`。
- 游标重连：`?from=6` 第一条是 seq 7 `turn/end`，没有重发 seq 6。
- 会话删除：DELETE 返回 `status=ended`；已开的 SSE 收到 `stream/end`，payload `{"reason":"session_ended"}`，无 `id`，日志里没有该帧。
- 业务错误路径（日志损坏）由 `test_log_read_failure_sends_stream_end` 覆盖；真实端点不主动制造坏日志。

## 结论

- snapshot/游标/durable 字段/终止语义在真实 Host 上走通。
- delta 不补；最终 response 校正。
- 远端壳不需要日志文件，靠 events 即可重建 durable 投影。
