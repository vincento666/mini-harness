# Host event sync UAT

**状态**：等人跑。

**怎么算办一件真事**：用真实 Host 打开一个有多回合/工具的会话，观察首次全量、snapshot、断线重连、业务终止四种路径；确认远端壳不需要读日志文件也能对齐 durable 投影。

## 跑之前

- 真实 reasoner 或 mock fixture；Host `--http` + token。
- 记录 session id、SSE 原始帧、日志路径。

## H1 · 首次全量

不带 cursor / snapshot 连接 `/events`。

**预期**：从 seq 0 起收到完整 durable；delta 无 id；tool/error/attempt 记录都在。

## H2 · snapshot 语义

`?snapshot=1` 连接。

**预期**：首帧 snapshot 带 `last_seq` 与 `messages`；后续从 last_seq 之后开始；`messages` 只含模型上下文，不是 UI 全量。

## H3 · 游标重连

断开后带 `?from=<last_seq>` 或 `Last-Event-ID` 重连。

**预期**：只补 `seq > last_seq`；不重发旧 durable；delta 不补。

## H4 · 业务终止

制造日志读失败（或会话结束/删除），观察 Host 主动终止。

**预期**：收到 `stream/end`（reason/code），无 id、日志里没有该帧；客户端收到后不自动重连。

## H5 · 物理断线

直接断开 TCP。

**预期**：没有 `stream/end`；客户端可按 last_seq 重连。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| H1 | 首次全量 | seq 0 起 | 真实 host session `e10dbb4c...`：首帧 `session/start`，随后 `segment/start...model/response`；delta 无 id | 通过 | 无 |
| H2 | snapshot | 消息基线 + last_seq | `test_snapshot_precedes_only_new_frames`：snapshot 首帧、`last_seq` 正确、messages 首条 role=system；后续从 last_seq+1 开始 | 通过 | snapshot 只是模型上下文，不是 UI 全量；已在协议里写明 |
| H3 | 游标重连 | 只补 >N | 真实 host `?from=6` 第一条是 seq 7 `turn/end`，未重发 6；`test_a_cursor_resumes_without_gaps` 同判 | 通过 | 无 |
| H4 | 业务终止 | stream/end | 真实 host 删除会话：DELETE 200 后收到 `stream/end {"reason":"session_ended"}`，无 id、日志无此帧；`test_log_read_failure_sends_stream_end` 覆盖 error/LOG_UNREADABLE | 通过 | 业务终止前若有段在跑，DELETE 会 409；需先等 idle |
| H5 | 物理断线 | 无 end | `test_a_disconnected_delta_reader_does_not_stop_the_segment`：客户端断开后段继续，日志无 `stream/end`；Host 不向已断连接写 end | 通过（间接） | 物理断开收不到帧，只能从“连接关闭且无终止帧/日志无 end”判定 |

**至少一条「用起来别扭」**：H5 的“没有 end”无法在断开后直接读；只能从连接关闭时没有收到终止帧、日志也没有 end 来判定。snapshot 只有模型消息，不是完整 UI 基线，壳必须首次从 seq 0 全量读。

**结论**：API 部分通过（agent 代跑，用户 2026-11-02 授权）。真实端点 session `e10dbb4c...`；单元/黑盒判据在 `tests/test_cli_host.py`。
