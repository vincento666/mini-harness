# Design

## Context

`AssistantTurn{content, tool_calls, usage}` 与 `Message{content, tool_calls}` 是当前唯一形状；H2 的 `model/delta` 是一个正文 sink。DSH 的 assistant message 是有序 content blocks，实时 chunk 有 `reasoning-delta`，durable 一条 `assistant/message`。本 change 只取这条主干，不取紧凑 stream / attempt / baseline。

## Goals / Non-Goals

**Goals:** blocks 保序；reasoning delta 独立 ephemeral；durable 一条 response；usage 口径；effort 配置；fold/replay 兼容；host SSE 分流。

**Non-Goals:** 紧凑带时间 stream、assistant/attempt、active baseline、plan mode、自动摘要/脱敏、跨路由回传。

## Decisions

**D1 blocks 是新增字段，旧投影保留。** `AssistantTurn.blocks` 是真相；`content` / `tool_calls` 由 blocks 派生，读旧代码仍可用。`Message` 同样加 `blocks`，`content`/`tool_calls` 作为投影。这样 H2 的旧日志与现有测试不需要一次性重写。

**D2 `Block` 是最小判别联合。** 三种：

```python
class ReasoningBlock(BaseModel): type: Literal["reasoning"]; text: str
class TextBlock(BaseModel): type: Literal["text"]; text: str
class ToolCallBlock(BaseModel): type: Literal["tool-call"]; id: str; name: str; arguments: dict
```

不用 `dict[str, Any]` 裸块；不用 `content` 字符串冒充 reasoning。

**D3 `reasoning/delta` 与 `model/delta` 并列，不进日志。** Sink 形状 `ReasoningSink = Callable[[str, int, str], Awaitable[None]]`（turn_id, index, text）；正文 sink 保持 `DeltaSink`。Provider 适配器从 `reasoning_content` / `thinking_delta` 取 reasoning，只喂 reasoning sink。

**D4 durable 仍是一条 `model/response`。** payload 新增 `blocks`，并保留 `content`/`tool_calls` 投影；`reasoning` 全文进 blocks，delta 不写。失败/取消沿用现有 `error/model` / ABORTED。

**D5 effort 在装配期校验。** `reasoning_effort` 是配置/端点设置；值域 `off|low|high|max`。不支持的值在 provider 发起请求前失败；`off` 不请求 thinking。有效值写进 `session/start`（供审计），不每轮猜。

**D6 usage 不加总。** `Usage` 加 `reasoning_tokens`；计量显示 `output_tokens`，reasoning 是其中子集；上下文预算照旧按文本估算。

**D7 fold 优先 blocks，旧日志退化。** 有 blocks 时按块生成 Message；没有时走现有内容投影。Provider 历史回传按块；OpenAI 兼容适配器若只能发 `content`，显式把 reasoning 丢弃/降级并记录，不静默拼进 content。

**D8 host SSE 复用现有合流。** `reasoning/delta` 是 ephemeral 帧，走 H2 的 delta 队列；`model/response` 是 durable 边界；重连不补 delta，最终 response 校正。

**D9 核心不解析标签，adapter 的标签协议乐观 emit、EOF fail closed。** 结构化 channel 是主路径；只有 adapter 选择 `思考...` 标签时，开标签确认后立即把后续内容作为 reasoning 流式发出，只保留检测闭标签的小尾缓冲；闭标签确认后这段完整。半开（EOF 未闭合）/半闭/嵌套/标签外无法归属内容一律 `PROVIDER_SCHEMA_INVALID`、不写 `model/response`；已经发出的 live reasoning 由壳清掉，不留下半条 durable。没有标签时全部按 text。

**D10 空 reasoning 丢弃，仅 reasoning 不冒充回答。** 空文本不产生 block/delta；只有 reasoning 的响应保留 blocks、`content` 投影为空，壳显示“无正文”，不把 reasoning 升级为可见答案。这样“只有思考没有正文”是可解释状态，不是半条回答。

**D11 失败也留 attempt 证据，DSH 同款。** DSH 在每个 settlement 的 attempt 上提交事件：成功是 `assistant/message`，失败/重试/取消/stream error 是 `assistant/attempt`，保留 stream 但不进模型历史。mini 对应地加一条 log-only `model/attempt`（`status`、`error_code`、`partial_blocks` / 紧凑 stream），`fold` 忽略它；这样坏标签/取消不会只剩一行 `error/model`，也不会把半条内容塞进历史。硬进程丢失在 settlement 前仍无 durable attempt（DSH 同样如此）。

## Risks / Trade-offs

- **投影双真源** → D1 规定投影只由 blocks 派生；判据比较 blocks 与投影。
- **日志体积/敏感内容** → 完整 reasoning 入日志（DSH 同款），UI 默认折叠；MVP 不做脱敏。
- **旧 provider 没有 reasoning** → 单 text block；旧日志 replay 逐点不变。
- **OpenAI 兼容不能块级回传** → 显式降级并记录；不把 reasoning 塞 content。
- **SSE 顺序** → reasoning 与 text 各自 sink，最终 response 是边界；判据分开。
- **effort 不支持** → 装配期失败，不发出请求。

## Migration Plan

1. 契约与 blocks、旧投影。
2. provider 解析与 sink 分流（mock 先行）。
3. turn loop 写 blocks 与 reasoning sink。
4. fold/replay 兼容。
5. host SSE `reasoning/delta`。
6. 门禁、真实端点、UAT、变异、Learning。

## Open Questions

- `reasoning_effort` 是全局配置还是每个 provider preset？先按配置，默认 `high`；DSH 的 deployment `thinking` 另算。
- reasoning 是否计入压缩的保留尾部？先按普通块，E1 再调。
- 壳的折叠 UI 是 H2 壳还是独立前端？先出 SSE 协议与事件，UI 只做最小折叠。
