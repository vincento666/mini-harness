# Spec Delta

## MODIFIED Requirements

### Requirement: 事件流是日志的逐行镜像

`GET /sessions/{id}/events` SHALL 是 SSE：每个 durable 帧的 `id` 是该记录的 `seq`、`event` 是类型、`data` 是整行记录的 JSON；游标来自 `?from=` 或 `Last-Event-ID`，`0` 合法、负数与非整数是 `400`；`?snapshot=1` 时 SHALL 先发一帧 `event: snapshot`（含 `session_id`、`status`、`last_seq` 与折叠后的 `messages`），随后从 `last_seq + 1` 继续送 durable 帧。H2 还 SHALL 在 durable 帧之间送 `event: model/delta` 的 ephemeral 帧：无 `id`、不落日志、不参与游标，`data` 是 `{turn_id, index, text}`。

#### Scenario: 帧与日志逐字段相等

- **WHEN** 跑完一个会话后从 0 读事件流
- **THEN** durable 帧数等于日志行数，逐帧的 `data` 解析后与对应记录相等

#### Scenario: snapshot 后只送新帧

- **WHEN** 会话已有 10 条记录时带 `snapshot=1` 连接
- **THEN** 第一帧是 `snapshot` 且 `last_seq` 为 9，之后只送 `seq > 9` 的 durable 帧

#### Scenario: delta 是 ephemeral 帧

- **WHEN** 一次流式模型调用正在生成正文
- **THEN** 客户端收到若干无 `id` 的 `model/delta` 帧，随后收到一条 durable `model/response`；日志里没有 delta 记录，重连后也不补这些 delta

## ADDED Requirements

### Requirement: health 报告流式能力

`GET /health` SHALL 保持 `protocol: 1`，并在响应中增加 `features: ["delta"]`；未知该字段的客户端 MUST 能继续工作。

#### Scenario: health 带 delta 能力
- **WHEN** 请求 `GET /health`
- **THEN** 响应含 `protocol: 1` 与 `features: ["delta"]`
