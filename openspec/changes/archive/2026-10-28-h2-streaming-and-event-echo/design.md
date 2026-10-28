# Design

## Context

H1 已经提供 `minihns host --http`：每会话一个 `SessionEnv`、段队列、取消、approval、SSE durable 帧与 snapshot。`Provider.generate(messages, tools, signal)` 目前一次返回完整 `AssistantTurn`；`openai_compat` 发非流式 POST。H2 要在这条链上加入逐字正文，而不改日志真源与 `seq` 游标。

底稿见 `docs/reference/host-streaming.md`；取舍见 ADR-0032 与 ADR-0006 的修订。

## Goals / Non-Goals

**Goals:**

- 模型正文可以流式到达宿主的 SSE；最终 `model/response` 仍是唯一 durable 真相。
- 没有 delta sink 时，行为与非流式逐点相同。
- 重试只发生在首 delta 之前；取消/断流不写半条 `model/response`。
- `replay` 与不流式逐点相等；`seq` / durable 帧形状不变。

**Non-Goals:**

- 工具调用逐字流、reasoning token、usage 逐块、多模型路由、WebSocket。
- 把 delta 写进日志，或让 delta 参与 `Last-Event-ID` / snapshot 的 `last_seq`。
- 多个并发模型流；一个会话同一时刻仍然只有一个段。

## Decisions

**D1 `Provider.generate` 增加可选 delta sink，而不是新方法。** 形如 `generate(messages, tools, signal, on_delta=None)`，`on_delta` 是 `Callable[[str], Awaitable[None]]`；没有 sink 时走现有非流式路径。否决「新方法 `generate_stream`」：回合循环会出现两种调用形状，mock 与真实适配器要各维护一套；否决「全局回调」：provider 是会话级对象，回调必须跟这次调用绑定。

**D2 delta 只在宿主侧广播，不进日志。** `SessionEnv` 增加可选的 `on_delta`（或由 host 在构造 env 时注入）；turn loop 把它传给 provider。host 的 `HostSession` 维护订阅者队列；`model/delta` 的 `data` 是 `{turn_id, index, text}`，无 `id`。不新增事件类型；`events/vocabulary`、`fold`、`replay` 都不认识它。

**D3 每个 SSE 连接一个 delta 队列 + 一个 durable `LogTail`。** `_events` 先送 snapshot（若有），然后循环：先 drain 该连接的 delta 队列，再读 durable 新帧。delta 在 provider 返回前发出，因此顺序稳定为 `model/request` → deltas → `model/response`。慢读者队列有界；满了丢最旧的 delta（ephemeral 可丢），durable 帧仍从日志补，最终 response 校正屏幕。连接关闭即退订。

**D4 快照/重连只覆盖 durable。** snapshot 仍是 `0..last_seq` 的 fold；重连用 `last_seq+1` 继续 durable。已经丢掉的 delta 不补；客户端在 `model/response` 到达后以完整 `content` 替换。这样 `seq` 与 durable 帧形状完全不变。

**D5 适配器用 `httpx` 的流式响应。** `stream: true` + `client.stream("POST", ...)`；逐行解析 `data:`，`[DONE]` 结束；`stream_options.include_usage` 失败时退回不带它，usage 允许缺。`tool_calls` 按 `index` 聚合；增量正文只交 sink，不进 `AssistantTurn.content`。取消时关闭响应并抛回结果，不重试。

**D6 重试边界由适配器记住「首 delta 已发」。** 首 delta 前 429/5xx 照旧重试一次；一旦发过 delta，任何失败都塌成 `PROVIDER_ERROR`，不重发、不写 `model/retry`。回合循环只负责把 `ProviderFailure.attempts` 落账，不判断流位置。

**D7 mock 的 fixture 增加可选 `deltas`。** 不改变旧 fixture 的行为：没有 `deltas` 就不发增量；有 `deltas` 时只在调用方给 sink 时发，最终 `content` 由 fixture 给。这样 seam ⑤ 不依赖真实端点。

**D8 health 只加一个 `features` 字段。** `protocol` 仍是 1；`features: ["delta"]` 是能力广告，不是协议版本升级。旧客户端忽略未知字段；SSE 客户端忽略未知 event。

## Risks / Trade-offs

- **delta 与 durable 的排序** → 单连接先 drain delta 再读日志；测试用真实子进程 + httpx 流断言 `model/request`、deltas、`model/response` 的相对顺序。
- **慢读者内存增长** → 有界队列 + 丢最旧 delta；durable 仍可从日志续读。
- **断线后屏幕不完整** → 不补 delta；`model/response` 到达后整段替换，重连以 snapshot 为准。
- **端点不支持 `stream_options`** → 退回不带它；usage 缺省零值，不因缺 usage 失败。
- **重试把开头打两遍** → 首 delta 标志；发过 delta 即禁止重试。
- **replay 漂移** → delta 不落日志，`fold`/`replay` 的输入不变；新增判据要求 replay 与不流式逐点相等。

## Open Questions

- delta 队列上限的具体数值（设计先取 256，E1 量到真实慢读者再调）。
- `features` 是否在 H2 之后加 `"tool-call-delta"`；H2 明确不做工具调用逐字流。
