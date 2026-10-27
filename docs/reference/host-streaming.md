# 宿主流式与事件回显：H2 的设计底稿

**定位**：H2 开工前的设计备忘，不是规格。对外行为以 H2 的 delta spec 为准；本文只把 DSH 的 durable / ephemeral 两层怎么落到 mini 的 SSE 上写清楚。

## 1. DSH 的对照

DSH 的会话流式是 `session/follow`：请求带调用方已持有的 last committed `seq`，返回 **opening snapshot**（带分页）+ **gap-free durable 事件帧** + 可选 **cursorless assistant-stream 帧**。另一条 `$events` 是 27 条 allowlist 的事件回显，没有游标、不补历史。

mini 的落法：

| DSH | mini |
|---|---|
| `session/follow` 的 snapshot | H1 的 `?snapshot=1` 首帧 |
| durable 帧 + `seq` 游标 | H1 的 SSE durable 帧（`id=seq`、`data=整行记录`） |
| assistant-stream 的逐字帧 | H2 的 `event: model/delta`，**ephemeral、无 `id`、不落日志** |
| `$events` 的 27 条 allowlist | **不做**；UI 的事件回显就是日志的逐行镜像 |
| WebSocket mux | **不做**；HTTP + SSE + unary POST |

## 2. 帧的形状

- `snapshot`：H1 已有；`{session_id, status, last_seq, messages}`。
- durable：`id: <seq>`、`event: <记录类型>`、`data: <整行记录 JSON>`；与日志逐字段相等。
- `model/delta`：`event: model/delta`，**不带 `id`**；`data: {turn_id, index, text}`。`index` 从 0 递增；`text` 是本次增量。它不进日志，也不参与 `Last-Event-ID`。
- 一次模型调用的顺序：`model/request`（durable）→ 若干 `model/delta`（ephemeral）→ `model/response`（durable）。`model/response` 的 `content` 是完整文本；UI 用它替换掉已经显示的增量。

**不发什么**：工具调用的逐字 delta、reasoning token、usage 的逐块——工具调用在 `model/response` 里一次给出，usage 也在最终回复里。H2 只流「可见的正文」。

## 3. Provider 侧

- OpenAI 兼容适配器加 `stream: true` 与 `stream_options: {"include_usage": true}`（端点不支持 `stream_options` 时退回不带它，usage 允许缺）；解析 `data: {...}` 行直到 `[DONE]`。
- `tool_calls` 的流式拼装按 `index` 聚合 `id` / `function.name` / `arguments`；拼完仍产出原来的 `AssistantTurn`。
- `Provider.generate` 多一个可选的 delta sink（或等价的回调）；没有 sink 时行为与非流式完全一样。mock provider 也要能发 delta，否则 CI 覆盖不到。
- **重试**：只在首 delta 之前重试一次（429/5xx，照 ADR-0006 的既有规则）；已经吐过字的流不重试，直接塌成 `PROVIDER_ERROR`，避免屏幕上出现两遍开头。
- **取消**：停止读流、关闭响应；内核在回合边界照常写 `error/abort` / `turn/end(ABORTED)`；已经显示的增量不补。

## 4. 断线、重连与 UI 客户端

- 重连带 `?from=<last_seq>` 与 `?snapshot=1`：先拿 snapshot（当前 `last_seq` + 折叠后的消息），再从 `last_seq + 1` 收 durable 帧。
- 重连时**已经丢掉的 delta 不补**；UI 以最终 `model/response` 为准。如果重连发生在一次调用中途，UI 先显示「正在生成」，等最终回复到达再替换。
- UI 客户端用 `fetch` + `ReadableStream` 解析 SSE（`EventSource` 不能带 Authorization header）；逐行解析 `id:` / `event:` / `data:`，按 `event` 分派；`model/delta` 无 `id`，不更新 `last_seq`。
- 多个客户端各自一个 tailer；一个慢读者只拖自己的连接，不拖内核（与 H1 相同）。

## 5. 协议版本

`GET /health` 保持 `protocol: 1`，加 `features: ["delta"]`；H1 的客户端不认识 `model/delta` 时按未知 `event` 忽略即可（SSE 客户端本来就要忽略未知事件）。不为了流式换 `seq` 游标或 durable 帧形状。

## 6. 判据（H2 起草时落成 seam 判据）

- seam ⑤：mock 的 delta 序列；OpenAI 适配器的 SSE 解析、`tool_calls` 拼装、usage 可选、流中断。
- seam ⑥：真实子进程 + httpx 流式读；首帧延迟、delta 拼接等于最终 `content`、重连不重复最终回复、`replay` 与不流式逐点相等。
- seam ①：重试只发生在首 delta 之前；取消中途不写半条 `model/response`。
- 真实端点：一次长回复看首 token 与最终一致性；一次工具调用看拼装。

## 7. 不做

多模型路由、逐字帧落日志、WebSocket、reasoning token、工具调用逐字流、多个并发模型流（一个会话同一时刻一个段）。
