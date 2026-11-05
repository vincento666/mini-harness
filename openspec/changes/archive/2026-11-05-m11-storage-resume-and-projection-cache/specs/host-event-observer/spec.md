# Spec Delta

## ADDED Requirements

### Requirement: Host live durable 事件走 observer

Host 的 live durable SSE 帧 SHALL 来自 `EventLog` 的 append observer（`HostSession.publish_event`），MUST NOT 靠 `LogTail` 轮询文件来发现新事件。历史/重连/snapshot 仍可从日志读取；observer 只负责 append 后推送。

每个 SSE 连接 SHALL 有独立的 durable 事件队列，断开时退订；同一个 `seq` MUST NOT 因 backlog 与 observer 各来一次而重复发送。slow reader 不得反压内核 append。

#### Scenario: 新 append 立即入队

- **WHEN** 内核 append 一条 `tool/result`
- **THEN** 已连接的 SSE 队列收到该记录，SSE 以 `id=seq` 发出

#### Scenario: 历史与 live 不重复

- **WHEN** 连接先读 backlog 到 seq N，observer 又收到 seq ≤ N
- **THEN** 只发送一次，`after` 单调推进

#### Scenario: 断开退订

- **WHEN** SSE 连接关闭
- **THEN** 该连接队列从 `event_subscribers` 移除，后续 append 不再入队
