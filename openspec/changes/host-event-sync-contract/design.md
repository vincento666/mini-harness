# Design

## Context

`/events` 现在有 snapshot、`from`/`Last-Event-ID`、LogTail 与 delta 队列；但 snapshot 的 `messages` 是 `fold` 模型上下文，游标边界与断流终止语义没有写死。Web 壳需要一套可恢复的 durable projection 契约，而不是拿日志文件。

## Decisions

**D1 snapshot 只做消息级快速基线。** 保留 `messages = fold(records).messages`，但明确它不是 UI transcript；客户端首次完整 UI 必须从 seq 0 读 events。这样不改现有 H2 snapshot 形状，也不会让 UI 把 system/header 当聊天记录。

**D2 无游标 = 全量；from 是排他。** `from=N` / `Last-Event-ID: N` 只发 `seq > N`。只有 durable 帧带 `id`；客户端按 seq 去重。`from=0` 会跳过 seq 0，这是半开区间的自然结果；需要 seq 0 时不传游标。

**D3 字段只透传，不重解释。** `model/response.blocks`、interrupted、model/attempt、error 字段原样从日志记录进 SSE data；host 不重新 fold 成 UI 行。

**D4 `stream/end` 是 ephemeral 终止标记。** 新帧：

```text
event: stream/end
data: {"reason":"error|session_ended|server_shutdown","code":"..."}
```

无 id、不落日志。仅在 Host 主动终止时发；物理断线不发。客户端据此区分“可重连断线”与“业务终止”。

**D5 终止点。** 目前最小实现只覆盖：
- 读日志失败（`LogReadFailure`）→ `stream/end(error, code)`；
- 会话被删除/结束时的流收尾（若当前循环能观察到）→ `stream/end(session_ended)`；
- server shutdown（若实现）→ `server_shutdown`。

不新增内核事件，不把 `stream/end` 写日志。

**D6 不提供日志下载。** 远端只有 snapshot + events；原始 JSONL 与 replay 留在 Host 文件系统/CLI。

## Risks / Trade-offs

- **snapshot 不完整** → 文档与测试明确；Web 首次全量读 events。后续可加 UI snapshot，不改内核。
- **全量重放大** → MVP 接受；分页/UI baseline 放到壳时。
- **stream/end 新帧** → 客户端必须识别；旧客户端忽略未知 event 即可，不破坏 durable。
- **业务终止 vs 物理断线** → 只有前者有 end；Host 被硬杀时客户端重连，符合预期。
- **无日志下载** → 审计只能本机；避免路径穿越与凭据泄漏。
