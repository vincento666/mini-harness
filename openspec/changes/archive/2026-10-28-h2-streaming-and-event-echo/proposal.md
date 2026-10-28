# Proposal

## Why

H1 的宿主已经能开会话、发消息、审批、取消、送 durable 事件；但 `model/response` 要等整轮模型调用结束才落日志，壳在真实长回复上只能「转圈等一整段」。DSH 的 `session/follow` 把这件事拆成两层：durable 帧（有 `seq`、可续读、是事实）+ cursorless assistant-stream 帧（逐字、ephemeral、断线不补）。mini 的 H2 补后者；没有它，第三阶段的壳第一体验仍然是「一次性吐出整段」。

H2 只做**模型正文的流式**，不把逐字帧写进日志。日志仍是唯一真源，最终 `model/response` 仍是唯一 durable 真相（ADR-0032）。

## What Changes

- **Provider 流式**：OpenAI 兼容适配器走 `stream: true`；解析 SSE 的 `data: {...}` 到 `[DONE]`，按 `index` 拼装 `tool_calls`；可选 `stream_options.include_usage`（端点不支持时不带，usage 可缺）。
- **delta sink**：`Provider.generate` 增加可选的 delta 回调（或等价 sink）。没有 sink 时行为与非流式逐点相同；mock provider 也能发 delta，否则 CI 覆盖不到。
- **重试边界**：只在**首 delta 之前**重试一次（429/5xx，照 ADR-0006）；已经吐过字的流不重试，塌成 `PROVIDER_ERROR`，避免屏幕上两遍开头。
- **宿主 ephemeral 帧**：`GET /sessions/{id}/events` 在 durable 帧之间送 `event: model/delta`，无 `id`、不落日志、不参与 `Last-Event-ID`；`data` 是 `{turn_id, index, text}`。顺序是 `model/request`(durable) → 若干 `model/delta`(ephemeral) → `model/response`(durable)。
- **协议版本**：`GET /health` 保持 `protocol: 1`，加 `features: ["delta"]`；不认识 `model/delta` 的客户端按未知事件忽略。
- **UAT 骨架**：`docs/verification/h2-streaming-and-event-echo-uat.md`。
- **ADR-0006 修订**：把「非流式」收窄成「默认非流式、H2 起可选流式」；ADR-0032 已记录 ephemeral 取舍。

**明确不做**：多模型路由 / fallback / 重试策略、逐字帧落日志、WebSocket mux、reasoning token、工具调用逐字流、多个并发模型流（一个会话同一时刻一个段）、把 `seq` 游标或 durable 帧形状换掉。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `provider`: `Provider.generate` 增加可选 delta sink；OpenAI 兼容适配器支持流式 SSE、流式 `tool_calls` 拼装与 usage 可选；重试只发生在首 delta 之前；mock 可发 delta。
- `host-api`: `GET /sessions/{id}/events` 增加 `model/delta` ephemeral 帧（无 `id`、不落日志、不参与游标）；`GET /health` 加 `features: ["delta"]`。

## Impact

- 代码：`provider/contract.py`、`provider/openai_compat.py`、`provider/mock.py`、`loop/turn_loop.py`（把 delta sink 传给 provider，不写日志）、`session/host.py`（每会话 delta 广播）、`cli/host.py`（SSE 合流 durable + delta）。
- 测试：seam ⑤（mock delta、SSE 解析、tool_calls 拼装、usage 可选、流中断）、seam ①（重试只在首 delta 前、取消不写半条 response）、seam ⑥（真实子进程 + httpx 流式读、首帧延迟、拼接等于最终 `content`、重连不重复、replay 相等）。
- 规格：`provider` 与 `host-api` 两个 delta；ADR-0006 修订说明。
- 依赖：H1；无新依赖（aiohttp/httpx 已在）。
