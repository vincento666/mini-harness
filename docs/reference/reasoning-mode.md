# 思考模式与预算：M10 之后的设计底稿

**状态**：planning memo，不是活动 OpenSpec change。按 `docs/roadmap.md` 的顺序，**M10 完成后**才 propose `reasoning-mode-and-budget`；本文只固定决策与边界，避免到接壳时再补协议。

**依据**：`re/verified/dsh` 的实际实现，不是只看摘要。关键出处见文末。

## 1. DSH 的事实

### 1.1 模型侧

`@deepseek-ai/dsh-llm-deepseek`：

- 部署配置 `thinking: enabled|disabled`；`disabled` 把所有请求锁成 `off`。
- `reasoningEffort: off|low|high|max`，默认 `high`。
- `off` 发 `thinking.type: disabled`；其余发 `output_config.effort`。
- 不支持的 effort 在网络 I/O 前以 `UNSUPPORTED_REASONING_EFFORT` 失败。
- 有效值记录在 request header，不是每轮重新猜。

### 1.2 实时层

`dsh-agent-loop` 的 `AssistantStreamAttempt` 把每个 chunk：

- 喂给 `BlockAssembler` 组装最终 message；
- 喂给 `AssistantStreamAccumulator` 组装紧凑 stream；
- 通过 `agent/assistant-stream` 发进程内、ephemeral 的帧。

chunk 类型里明确有 `reasoning-delta`。UI 的 `ReasoningRow` 把它渲染成独立的折叠“思考”行，和回答正文分开。

### 1.3 durable 层

DSH 不把每个 delta 写成一条日志事件。一次成功 attempt 只追加一条 `assistant/message`：

- `message.content` 是完整内容块，`CONTENT_KINDS` 包含 `reasoning`；
- `stream` 是这次 attempt 的紧凑带时间 chunk 序列；
- 失败/重试/取消走 `assistant/attempt`，保留 stream 但不进模型历史。

`dsh-session` 的原话是：`assistant/message` carries the assembled model-visible message plus its compact timed stream。

### 1.4 壳与重连

- `session/follow` 的帧是 `snapshot + durable event + 可选 assistant-stream`。
- opening snapshot 可带 `assistantStream` baseline；`SessionAssistantStreamAccumulator` 保留 `startedAfterSeq`、`nextIndex` 和已收到 stream，所以重连能接上进行中的半截。
- 最终 durable `assistant/message` 是重放/历史；实时帧只负责“正在发生”。

### 1.5 mini 当前的不足

| 位置 | mini 现状 | 只加 `reasoning` 字段的问题 |
|---|---|---|
| durable `model/response` | `content: str` + `tool_calls` | 只能表达“思考在回答之前”，无法表达 reasoning / text / tool-call 的任意顺序 |
| 表层 `Message` | `content` + `tool_calls` | reasoning 没有块类型，provider 回传时只能当普通文本或丢弃 |
| 实时输出 | 只有 `model/delta` | 思考与正文共用一条流，壳无法可靠分流 |
| shell | 正文区 + durable 事件回显 | 没有独立思考区 |
| DSH 对照 | `assistant/message` 的 `content` 是有序块数组 | mini 的单字段模型不具备同等表达能力 |

**结论**：要真正对齐 DSH 的“先思考 / 思考与行动交错”，不能只加一个 `reasoning` 字符串；必须把 assistant message 升级成 **有序 content blocks**。单字段只能作为临时过渡，不能作为 `reasoning-mode-and-budget` 的目标形状。

## 2. mini 的决策

### 采用（“应该参考：做”）

1. **一条 durable `model/response` 仍是唯一真相**；reasoning 合进这条记录，不按 delta 写日志。
2. **实时 reasoning 独立成 `reasoning/delta`**：无 `id`、不落日志、不参与游标，和 H2 的 `model/delta` 并列。
3. **壳按类型分流**：思考内容进折叠区，回答正文单独渲染；不在服务端把两者拍平成一段文本。
4. **思考强度是 provider/请求头配置**：值域先照 DSH 的 `off|low|high|max`，具体适配器映射由 provider 决定。
5. **历史回传**：后续请求把之前的 reasoning 原样带回；`fold` 必须能从日志重建它。
6. **UI 形态参考 DSH**：流式时思考区显示最新段落预览；结束后可展开完整 Markdown；回答区独立。
7. **采用 DSH 的有序 content blocks**：`model/response` 的 assistant message 用 `blocks` 表达 `reasoning` / `text` / `tool-call` 的顺序；`fold` 保留顺序；provider 按协议回传。只加 `reasoning` 字段不足以对齐 DSH，不列为目标形状。

### 固定取舍

- **日志体积与敏感内容：先参考 DSH**——durable 里保存完整 reasoning；接受日志变大、思考内容进入日志；UI 默认折叠。MVP 不做自动脱敏/摘要。
- **预算语义：reasoning tokens 是 output 的一部分，不重复计**。`usage.reasoning_tokens` 是 `output_tokens` 的子集；token meter/成本视图不得再加一遍。上下文预算另算：回传的 reasoning 文本进入后续请求，就按普通上下文计入。

### 暂缓（“先记着”，不照抄）

- 紧凑带时间 stream（DSH 的 `assistant/message.stream` 时间线）。
- 单独的 `assistant/attempt` 事件；mini 先复用 `error/model` + `model/retry`。
- DSH 式 active attempt baseline（重连接上生成中的半截）；H2 仍是不补 delta，最终 response 校正。

## 3. 建议的数据形状

durable：

```json
{
  "type": "model/response",
  "payload": {
    "turn_id": "t1",
    "blocks": [
      {"type": "reasoning", "text": "先看 note.md"},
      {"type": "tool-call", "id": "c1", "name": "read", "arguments": {"file_path": "note.md"}},
      {"type": "reasoning", "text": "读到了 alpha/beta"},
      {"type": "text", "text": "note.md 里是 alpha 和 beta。"}
    ],
    "usage": {
      "input_tokens": 100,
      "output_tokens": 50,
      "reasoning_tokens": 30
    },
    "finish_reason": "stop"
  }
}
```

ephemeral：

```text
event: reasoning/delta
data: {"turn_id":"t1","index":0,"text":"..."}
```

折叠层：

```python
class Message:
    role: str
    blocks: list[Block]          # reasoning / text / tool-call，保序
    # content 与 tool_calls 若保留，只能是 blocks 的派生投影，不能双写真源
```

provider 请求按协议把 blocks 回传（DSH 的 DeepSeek 适配器用 thinking block）。如果 mini 的 OpenAI 兼容适配器不支持块级回传，就在适配器层显式降级/丢弃并记录，MUST NOT 把 reasoning 当普通 `content` 静默塞回。

## 4. 边界

- 不改 H2 已冻结的 `model/delta` / durable 帧形状；`reasoning/delta` 是新增的并列 ephemeral 事件。
- 不把 reasoning 写进 `model/delta`，也不把工具参数/usage 逐块流式化。
- **本 change 的目标是 content blocks，不是单字段**；`content` / `tool_calls` 若保留只是投影。
- 不默认把 reasoning 当可见回答；UI 必须能折叠。
- 没有 reasoning 的 provider/model 必须保持现有行为逐点不变。
- 不做完整 plan-mode 状态机。

## 5. 判据（change 起草时落成 seam）

- seam ⑤：DeepSeek/兼容适配器解析 reasoning 与 `reasoning_tokens`；mock fixture 能发 reasoning deltas；不支持 effort 在 I/O 前失败。
- seam ①：turn loop 把 reasoning sink 传给 provider；最终 blocks（含 reasoning/text/tool-call 顺序）落一条 `model/response`；delta 不写日志；取消不写半条 response。
- seam ④：`fold` 能从 blocks 重建 `Message` 的顺序；`replay` 逐点相等。
- seam ⑥：SSE 同时有 `reasoning/delta` 与 `model/delta`，两者顺序与 `model/response` 边界正确；重连不补 delta，最终 response 带 blocks；无 reasoning 的模型日志与今天逐点相同。
- 真实端点：reasoner 一次长回复；reasoning → tool-call → reasoning → text 的顺序可重放；usage 的 reasoning 不重复计。
- UAT：思考区与回答区分开；折叠/展开；长思考不把回答挤掉。
- 变异：reasoning 误写日志、reasoning 混进正文、reasoning tokens 重复计——各至少一条判据杀死。

## 6. 时机

```text
M10（工具管线 / 并发 / 上下文经济）
  ↓
reasoning-mode-and-budget（本 memo）
  ↓
M11 / M12 / M13
  ↓
M14 / M14c（plan/todo UX）
  ↓
接壳前冻结 reasoning 协议
```

**顺序**：M10 完成后、M11/M12 前做。这样 M12 子代理能继承思考档位；M14c 的 `todo` / `plan` 仍另算。

## 7. 开放问题（propose 时答）

1. `blocks` 是新增字段并保留 `content`/`tool_calls` 投影，还是直接替换旧字段？若保留投影，必须保证投影不成为第二真源。
2. mini 的 DeepSeek 走 OpenAI 兼容 `reasoning_content`，还是新写 Messages/thinking 适配器？块级回传能力按适配器协议裁。
3. reasoning 回传是否总是原样带回，还是只在同一 provider/model 路由内？默认同一路由原样；跨路由要 ADR。
4. 思考区默认折叠；是否需要“只看摘要”策略？MVP 不做自动摘要。
5. reasoning 是否影响上下文压缩的遮蔽范围？先按普通 block 内容计入预算；是否需要单独保留，留 E1 数据。

## 出处

- `re/verified/dsh/node_modules/@deepseek-ai/dsh-llm-deepseek/README.zh.md`（thinking / reasoningEffort / 流式）
- `.../dsh-llm-deepseek/lib/index.js`（`thinking_delta` → `reasoning-delta`、usage 映射）
- `.../dsh-agent-loop/lib/index.js`（`AssistantStreamAttempt`、`agent/assistant-stream`、`assistant/message` 的 `stream`）
- `.../dsh-session/README.zh.md`（`assistant/message` + compact stream、`assistant/attempt`）
- `.../dsh-api-session-controller/lib/types/history.js` 与 `types/assistant-stream.js`（follow 帧、baseline）
- `.../dsh-client-ui-chat/lib/client.js`（`ReasoningRow`、折叠预览）
- `.../dsh-plan-mode/README.zh.md`（plan mode 是独立状态机）
