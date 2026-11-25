# Spec Delta: host-api

## MODIFIED Requirements

### Requirement: 事件流是日志的逐行镜像

`GET /sessions/{id}/events` SHALL 是 SSE：每个 durable 帧的 `id` 是该记录的 `seq`、`event` 是类型、`data` 是整行记录的 JSON；游标来自 `?from=` 或 `Last-Event-ID`，`0` 合法、负数与非整数是 `400`；`?snapshot=1` 时 SHALL 先发一帧 `event: snapshot`（含 `session_id`、`status`、`last_seq` 与折叠后的 `messages`），随后从 `last_seq + 1` 继续送 durable 帧。H2 还 SHALL 在 durable 帧之间送 `event: model/delta` 的 ephemeral 帧：无 `id`、不落日志、不参与游标，`data` 是 `{step_id, index, text}`。

增量的单位是**步**（一次模型往返），不是轮：`step_id` 与同一步 durable `model/response` 载荷里的 `step_id` 同值。旧键 `turn_id` MUST NOT 再出现。

#### Scenario: 帧与日志逐字段相等

- **WHEN** 跑完一个会话后从 0 读事件流
- **THEN** durable 帧数等于日志行数，逐帧的 `data` 解析后与对应记录相等

#### Scenario: snapshot 后只送新帧

- **WHEN** 会话已有 10 条记录时带 `snapshot=1` 连接
- **THEN** 第一帧是 `snapshot` 且 `last_seq` 为 9，之后只送 `seq > 9` 的 durable 帧

#### Scenario: delta 是 ephemeral 帧

- **WHEN** 一次流式模型调用正在生成正文
- **THEN** 客户端收到若干无 `id` 的 `model/delta` 帧，随后收到一条 durable `model/response`；日志里没有 delta 记录，重连后也不补这些 delta

#### Scenario: delta 带步 id 而不是轮 id

- **WHEN** 一轮里跑了两步，只有第二步在流式输出
- **THEN** 这些 `model/delta` 帧的 `step_id` 都是第二步的 id，与那条 `model/response` 的载荷一致
