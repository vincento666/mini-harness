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

### Requirement: 游标边界是明确的半开区间

`GET /events` 不带游标 SHALL 从 seq 0（含）开始；`?from=N` 与 `Last-Event-ID: N` SHALL 只发 `seq > N` 的 durable 帧。只有 durable 帧 SHALL 带 `id=seq`；`model/delta` / `reasoning/delta` / `stream/end` MUST NOT 带 `id`，也不参与游标。客户端 SHALL 按 seq 去重；重复帧不产生重复 UI 行。

#### Scenario: 无游标从 0 开始

- **WHEN** 首次连接不传 from/Last-Event-ID
- **THEN** 收到 seq 0 起的全部 durable 记录

#### Scenario: from 是排他的

- **WHEN** 连接传 `from=7`
- **THEN** 第一条 durable 帧是 seq 8，seq 7 不重发

#### Scenario: delta 不移动游标

- **WHEN** 客户端收到 `model/delta` 或 `reasoning/delta`
- **THEN** 帧没有 `id`，客户端不更新 last_seq

### Requirement: durable 帧保留 UI 需要的字段

Host SHALL 原样透出 durable `model/response.blocks`（含 `reasoning` / `text` / `tool-call` 顺序）、`interrupted: true`、`model/attempt` 与 `error/*` 的 `code` / `detail`。`model/attempt` MUST 保持 log-only 语义，客户端可显示诊断行但 MUST NOT 把它当 assistant 历史。snapshot 的 `messages` 不得替代这些字段。

#### Scenario: interrupted 字段透出

- **WHEN** 日志里有一条 interrupted `model/response`
- **THEN** SSE 的该 durable 帧带 `interrupted: true` 与已交付 `blocks`

#### Scenario: attempt 不被当历史

- **WHEN** 日志里有一条 `model/attempt`
- **THEN** SSE 透出该记录；客户端能区分它是 attempt，不是 assistant message

### Requirement: Host 主动终止发 stream/end

Host 在主动终止事件流时（业务/持久化错误、会话删除/结束等）SHALL 先发一个 ephemeral `stream/end` 帧：

```json
{ "reason": "error" | "session_ended" | "server_shutdown", "code": "..." }
```

`stream/end` MUST NOT 带 `id`、MUST NOT 落日志、MUST NOT 参与游标。物理断线（客户端断开、TCP 断、Host 被杀）MUST NOT 发 `stream/end`。

#### Scenario: 业务错误终止

- **WHEN** Host 读日志失败并决定终止流
- **THEN** 先发 `stream/end`（reason=error，code=LOG_UNREADABLE），再关闭响应

#### Scenario: 物理断线没有 end

- **WHEN** 客户端直接断开 TCP
- **THEN** Host 不发 `stream/end`；客户端应把它当可重连断线

### Requirement: 客户端按终止语义决定重连

客户端收到 `stream/end` 后 MUST NOT 自动重连该流；没有 `stream/end` 的断流 MAY 按 `last_seq` 重连。重连只补 durable；丢弃的 delta MUST NOT 被请求重放，最终 durable `model/response` 校正。

#### Scenario: end 后不重连

- **WHEN** 客户端收到 `stream/end(reason=error)`
- **THEN** 停止自动重连，显示错误；不把断流当网络抖动

#### Scenario: 无 end 断流重连

- **WHEN** 流在没有 `stream/end` 时断开
- **THEN** 客户端带 `last_seq` 重连，只补 durable

### Requirement: 不提供原始日志下载

Host MUST NOT 暴露按路径读取原始 JSONL 的接口。远端 UI 只能通过 snapshot + durable SSE 读取日志投影；审计与 `replay` 留在 Host 本机。

#### Scenario: 没有 log 路径接口

- **WHEN** 远端请求任意 `/log?path=...` 或等价路径
- **THEN** 不是合法路由；不能读取 Host 文件系统
