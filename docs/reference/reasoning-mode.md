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

### 1.5 plan mode 是另一件事

`dsh-plan-mode` 是独立产品包：`/plan`、持久化 `plan/mode` 事件、`plan:policy` 提示词、`exit_plan_mode` 工具，工具目录不变。它不负责 reasoning effort，也不该和本 change 混在一起。

## 2. mini 的决策

### 采用（“应该参考：做”）

1. **一条 durable `model/response` 仍是唯一真相**；reasoning 合进这条记录，不按 delta 写日志。
2. **实时 reasoning 独立成 `reasoning/delta`**：无 `id`、不落日志、不参与游标，和 H2 的 `model/delta` 并列。
3. **壳按类型分流**：思考内容进折叠区，回答正文单独渲染；不在服务端把两者拍平成一段文本。
4. **思考强度是 provider/请求头配置**：值域先照 DSH 的 `off|low|high|max`，具体适配器映射由 provider 决定。
5. **历史回传**：后续请求把之前的 reasoning 原样带回；`fold` 必须能从日志重建它。
6. **UI 形态参考 DSH**：流式时思考区显示最新段落预览；结束后可展开完整 Markdown；回答区独立。

### 固定取舍

- **日志体积与敏感内容：先参考 DSH**——durable 里保存完整 reasoning；接受日志变大、思考内容进入日志；UI 默认折叠。MVP 不做自动脱敏/摘要。
- **预算语义：reasoning tokens 是 output 的一部分，不重复计**。`usage.reasoning_tokens` 是 `output_tokens` 的子集；token meter/成本视图不得再加一遍。上下文预算另算：回传的 reasoning 文本进入后续请求，就按普通上下文计入。

### 暂缓（“先记着”，不照抄）

- 紧凑带时间 stream（DSH 的 `assistant/message.stream` 时间线）。
- 单独的 `assistant/attempt` 事件；mini 先复用 `error/model` + `model/retry`。
- 完整 content-block 模型（reasoning/text/tool-call 交错）；第一个切片先加 `reasoning` 字段。
- DSH 式 active attempt baseline（重连接上生成中的半截）；H2 仍是不补 delta，最终 response 校正。
- 完整 plan-mode 状态机；`todo`/`plan` 归 M14c。

## 3. 建议的数据形状

durable：

```json
{
  "type": "model/response",
  "payload": {
    "turn_id": "t1",
    "content": "最终回答",
    "reasoning": "可选：最终思考文本",
    "tool_calls": [],
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

折叠层增加可选 `Message.reasoning`；provider 请求把历史 reasoning 带回。若未来需要交错块，再把 `reasoning`/`content` 升级成 `blocks`，作为另一次 schema 变更。

## 4. 边界

- 不改 H2 已冻结的 `model/delta` / durable 帧形状；`reasoning/delta` 是新增的并列 ephemeral 事件。
- 不把 reasoning 写进 `model/delta`，也不把工具参数/usage 逐块流式化。
- 不做完整 plan-mode；M14c 的 `plan` / `todo` 是另一层。
- 不默认把 reasoning 当可见回答；UI 必须能折叠。
- 没有 reasoning 的 provider/model 必须保持现有行为逐点不变。

## 5. 判据（change 起草时落成 seam）

- seam ⑤：DeepSeek/兼容适配器解析 reasoning 与 `reasoning_tokens`；mock fixture 能发 reasoning deltas；不支持 effort 在 I/O 前失败。
- seam ①：turn loop 把 reasoning sink 传给 provider；最终 reasoning 与 content 一起落一条 `model/response`；delta 不写日志；取消不写半条 response。
- seam ④：`fold` 能从日志重建 `Message.reasoning`；`replay` 逐点相等。
- seam ⑥：SSE 同时有 `reasoning/delta` 与 `model/delta`，两者顺序与 `model/response` 边界正确；重连不补 delta，最终 response 带 reasoning；无 reasoning 的模型日志与今天逐点相同。
- 真实端点：reasoner 一次长回复；首 reasoning delta / 首正文 delta / 最终 content 一致；usage 的 reasoning 不重复计。
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

M10 完成后、M11/M12 前做。这样 M12 子代理能继承思考档位，不用回头补；M14c 只做 plan/todo，不和 reasoning 混。

## 7. 开放问题（propose 时答）

1. 档位是会话级（`session/start`）还是每回合可改（`model/request`）？先按会话级，减少 payload 漂移；若壳要每回合切换，再改 request header。
2. mini 的 DeepSeek 走 OpenAI 兼容 `reasoning_content`，还是新写 Messages/thinking 适配器？先按现有适配器能力定；不为了对齐 DSH 直接换协议。
3. reasoning 回传是否总是原样带回，还是只在同一 provider/model 路由内？默认同一路由原样；跨路由要 ADR。
4. 思考区默认折叠；是否需要“只看摘要”策略？MVP 不做自动摘要。
5. reasoning 是否影响上下文压缩的遮蔽范围？先按普通 message 内容计入预算；是否需要单独保留，留 E1 数据。

## 出处

- `re/verified/dsh/node_modules/@deepseek-ai/dsh-llm-deepseek/README.zh.md`（thinking / reasoningEffort / 流式）
- `.../dsh-llm-deepseek/lib/index.js`（`thinking_delta` → `reasoning-delta`、usage 映射）
- `.../dsh-agent-loop/lib/index.js`（`AssistantStreamAttempt`、`agent/assistant-stream`、`assistant/message` 的 `stream`）
- `.../dsh-session/README.zh.md`（`assistant/message` + compact stream、`assistant/attempt`）
- `.../dsh-api-session-controller/lib/types/history.js` 与 `types/assistant-stream.js`（follow 帧、baseline）
- `.../dsh-client-ui-chat/lib/client.js`（`ReasoningRow`、折叠预览）
- `.../dsh-plan-mode/README.zh.md`（plan mode 是独立状态机）
