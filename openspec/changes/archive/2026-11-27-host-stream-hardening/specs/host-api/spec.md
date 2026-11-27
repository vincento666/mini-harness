# Spec Delta

## ADDED Requirements

### Requirement: 初次同步的 snapshot 是消息基线，不是完整 UI

`GET /sessions/{id}/events?snapshot=1` SHALL 在首帧返回 `snapshot`，含 `session_id`、`status`、`last_seq`、`messages`；`messages` MUST 明确定义为 `fold` 出来的模型上下文，不是完整 UI transcript。需要完整 UI 的客户端 MUST 用 `/events` 从 seq 0 读 durable 事件并在本地建 projection，MUST NOT 把 snapshot 的 `messages` 当作 tool/approval/error 的完整历史。snapshot 之后流 SHALL 从 `last_seq` 之后继续。

#### Scenario: snapshot 后从 last_seq 继续

- **WHEN** snapshot 返回 `last_seq=42`
- **THEN** 后续 durable 帧的 seq 从 43 起，不重发 42

#### Scenario: snapshot 不是完整 UI

- **WHEN** 会话之前有 tool/approval/error 事件
- **THEN** snapshot.messages 只反映模型上下文；客户端要完整 UI 必须从 seq 0 读 events

### Requirement: Host 主动终止发 stream/end

Host 在主动终止事件流时（日志读不动等持久化错误、会话删除/结束等）SHALL 先发一个 ephemeral `stream/end` 帧：

```json
{ "reason": "error" | "session_ended", "code": "..." }
```

`stream/end` MUST NOT 带 `id`、MUST NOT 落日志、MUST NOT 参与游标。

#### Scenario: 业务错误终止

- **WHEN** Host 读日志失败并决定终止流
- **THEN** 先发 `stream/end`（reason=error，code=LOG_UNREADABLE），再关闭响应

#### Scenario: 会话结束终止

- **WHEN** 会话被删除而事件流还开着
- **THEN** 先发 `stream/end`（reason=session_ended），再关闭响应

#### Scenario: stream/end 不落日志与游标

- **WHEN** 客户端收到 `stream/end` 后重连（带或不带 `Last-Event-ID`）
- **THEN** 日志里没有 `stream/end` 记录；重放出来的 durable 帧序列不含它

### Requirement: 不提供原始日志下载

Host MUST NOT 暴露按路径读取原始 JSONL 的接口。远端 UI 只能通过 snapshot + durable SSE 读取日志投影；审计与 `replay` 留在 Host 本机。

#### Scenario: 没有 log 路径接口

- **WHEN** 远端请求任意 `/log?path=...` 或等价路径
- **THEN** 不是合法路由；不能读取 Host 文件系统
