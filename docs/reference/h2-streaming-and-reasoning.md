# 流式、sink 与思考帧：H2 与 DSH 的对照

**用途**：把 H2 做完之后仍然容易混在一起的一组概念讲成一条线——durable 日志、ephemeral 帧、`sink`、`model/delta`、`reasoning/delta`、SSE 合流，以及 DSH 在同一个位置上多做了哪些层。读完之后应该能回答：

- `model/delta` 和 `model/response` 到底是什么关系，为什么一个不落日志；
- `sink` 是回调、队列还是日志？谁把 delta 交给谁；
- `GET /sessions/{id}/events` 为什么能把 durable 帧和 delta 合到一条 SSE 上，顺序怎么保证；
- H2 已经做到哪、刻意没做哪；
- DSH 的 `assistant-stream` / `assistant/message` / `reasoning-delta` / `ReasoningRow` 各在哪一层；
- 「思考内容」应该落在 durable 的哪里、实时又该怎么发；mini 以后要做时不能漏哪几层。

这不是新架构，也不是把 DSH 的 L0–L13 层号搬过来；它是 mini 在 H2 这个时间点上的**流式运行时教学模型**。

---

## 0. 先看总图

```text
┌────────────────────────── Shell / UI（S） ──────────────────────────┐
│ 人看得见：回答正文、思考折叠区、事件回显、工具调用/结果             │
│ 读：GET /sessions/{id}/events（durable + ephemeral）                 │
│ 写：POST messages / cancel / approvals                               │
└───────────────────────────────▲──────────────────┬───────────────────┘
                                │ SSE 帧            │ 人的选择
┌───────────────────────────────┴──────────────────▼───────────────────┐
│ Host（H1/H2，外壳侧的运行时）                                         │
│ 会话表 / 段队列 / 取消 / approval future / SSE 合流 / 鉴权           │
│ 每个连接一个 delta 队列；慢读者丢最旧；不写日志                       │
└───────────────────────────────▲──────────────────┬───────────────────┘
                                │ delta 回调        │ 段、工具、审批
┌───────────────────────────────┴──────────────────▼───────────────────┐
│ Kernel（K）                                                           │
│ turn_loop：装配 → model → tool batch → 停止判定                       │
│ 把 provider 的 text 增量包成 turn-aware 的 sink；把最终结果落账       │
└───────────────────────────────▲──────────────────┬───────────────────┘
                                │ chunk             │ append
┌───────────────────────────────┴──────────────────▼───────────────────┐
│ Provider（模型适配器）                                                │
│ OpenAI 兼容 SSE：data: {...}，直到 [DONE]；tool_calls 按 index 拼     │
└───────────────────────────────┬──────────────────┬───────────────────┘
                                │                  │
                     ┌──────────▼─────────┐  ┌─────▼──────────────────┐
                     │ 日志 JSONL         │  │ 表层 messages          │
                     │ durable，只追加    │─►│ fold(前缀)，模型上下文 │
                     └────────────────────┘  └────────────────────────┘
```

从下往上看：

1. **Provider** 产生 chunk；
2. **Kernel** 把正文 chunk 转成 delta，最终结果写成 durable `model/response`；
3. **Host** 把 delta 广播给每个 SSE 连接，同时读日志送 durable 帧；
4. **Shell** 把两类帧分开渲染；
5. **Log** 只记 durable 事实；delta 不进日志。

---

## 1. 两种帧：durable 与 ephemeral

### 1.1 durable 帧

`GET /sessions/{id}/events` 上的 durable 帧：

```text
id: <seq>
event: <记录类型>
data: <日志整行 JSON>
```

- `id` 就是日志的 `seq`；帧与日志逐字段相等；
- `Last-Event-ID` / `?from=` 只推进 durable 的 `seq`；
- 日志里有什么，durable 流就能重放什么；
- `snapshot=1` 时第一帧是合成的 `snapshot`，没有 `id`（见第 3 节）。

H2 的 durable 帧没有新增形状；`model/response` 仍然是唯一的一条完整回复。

### 1.2 ephemeral 帧

`model/delta` 是 H2 新增的 ephemeral 帧：

```text
event: model/delta
data: {"turn_id":"t1","index":0,"text":"你"}
```

- **没有 `id`**；不参与 `Last-Event-ID` / `?from=`；
- **不落日志**；重连不补；
- 一次模型调用的顺序是：

```text
model/request（durable）
  → model/delta × N（ephemeral）
  → model/response（durable）
```

- `model/response.content` 是完整正文；UI 收到它后用完整正文替换已经显示的增量。

### 1.3 帧 ≠ 事件 ≠ 一步

| 说法 | 实际 |
|---|---|
| 一帧 = 一条日志记录 | durable 帧是；`model/delta` 不是；`snapshot` 也不是 |
| 一帧 = 一步 | 一个回合由多条记录组成；delta 只是其中一条记录的“过程” |
| delta 是日志事件 | 不是；它只在传输层存在 |
| `model/response` 是 delta 的拼接结果 | 是同一个 provider 调用的最终结果；日志只存它，不存 delta 序列 |

---

## 2. `sink`：回调，不是日志，也不是队列

### 2.1 provider 侧的 `DeltaSink`

H2 的 provider 契约：

```python
DeltaSink = Callable[[str], Awaitable[None]]
```

`provider.generate(messages, tools, signal, on_delta=None)`：

- 有 `on_delta`：边解析 SSE 边 `await on_delta(text)`；
- 没有 `on_delta`：走原来的非流式路径，最后一次性返回 `AssistantTurn`；
- 无论有没有 sink，最终都返回一个完整的 `AssistantTurn`（`content`、`tool_calls`、`usage`、`finish_reason`）。

`DeltaSink` 只认正文文本；provider **不知道** `turn_id`，也不应该知道。

### 2.2 Kernel 侧的 `TurnDeltaSink`

`SessionEnv` 上的 sink 是 turn-aware 的：

```python
TurnDeltaSink = Callable[[str, str], Awaitable[None]]  # (turn_id, text)
```

`turn_loop` 为每个 turn 包一层：

```python
async def forward(text: str) -> None:
    await env.on_delta(turn_id, text)
```

provider 收到的是 `forward`（只认 text）；Host 收到的是 `(turn_id, text)`。这样：

- provider 不需要知道回合编号；
- Host 可以给每个 delta 带上 `turn_id` 和该 turn 的 `index`；
- sink 的边界就是“一次 turn 的正文增量”。

### 2.3 Host 侧的订阅者队列

`HostSession`：

```text
subscribers: set[asyncio.Queue[dict]]
delta_indexes: dict[turn_id, int]
```

- `subscribe_deltas()`：一个 SSE 连接一个队列；
- `publish_delta(turn_id, text)`：给每个队列 `put_nowait({turn_id, index, text})`；
- 队列上限 256；满了丢最旧（ephemeral 可丢），不反压 provider；
- 连接断开就退订；慢读者只拖自己的连接。

### 2.4 sink 的三种角色

| 层 | 名字 | 拿到什么 | 做什么 |
|---|---|---|---|
| Provider | `DeltaSink` | `text` | 把 SSE 正文片段交给调用方 |
| Kernel | `TurnDeltaSink` | `turn_id, text` | 包一层，给片段归属 |
| Host | `publish_delta` | `turn_id, text` | 广播到每个连接队列 |
| Shell | `model/delta` 帧 | `{turn_id,index,text}` | 追加到 UI 的流式区 |

一句话：**sink 是出口，不是仓库；日志只记最终 `model/response`，不记流过 sink 的每一滴。**

---

## 3. 合流：durable `LogTail` + ephemeral 队列

### 3.1 mini 的实现

`cli/host.py::_events`：

```text
1. 需要 snapshot 时：读日志前缀，fold 成 messages，发 snapshot 帧
2. 订阅该连接的 delta 队列
3. 循环：
     a. tail.read_new() 读 durable 新记录
     b. 按顺序写 durable 帧
     c. 如果遇到 model/response，先把 delta 队列排空，再写 response
     d. 没有 response 时，也把已到的 delta 写出去（否则会等整段结束）
     e. sleep(EVENTS_POLL_SECONDS)
```

关键顺序：

```text
model/request(durable)
  → 已到的 delta
  → model/response(durable)
```

为什么不是“先排空 delta 再写所有 durable”：如果日志 backlog 里有 `session/start`、`segment/start`，先写 delta 会把 `model/delta` 排到 `session/start` 前面。H2 的第一版就踩过这个坑；真实端点还暴露了另一个坑——只在 `model/response` 前排空会让整段被缓冲到结束，首帧 1.2 s。修复后：

- 有 response 时：先排空 delta，再写 response；
- 没有 response 时：写完本批 durable 后，也把已到的 delta 写出去。

### 3.2 重连与 snapshot

```text
日志：0 ... 93 94 95 | 96 97 ...（新记录）
                  ▲
                  snapshot 读 0..95，last_seq=95
                  messages = fold(0..95)

?snapshot=1：
  第 1 帧  event: snapshot（无 id；last_seq=95 + messages）
  之后     id=96, 97, ...（durable）
  delta    只发连接之后产生的；已经丢的不补
```

- snapshot 是**前缀折叠**，不是“最后一回合的结果”；
- `last_seq` 是前缀终点，不是起点；
- H2 的 delta 不参与 snapshot：重连只补 durable，最终 `model/response` 校正屏幕；
- 这不是丢帧：旧 delta 是 ephemeral，不是事实。

### 3.3 与 DSH 的差别

DSH 的 `session/follow` 帧同样分三层：

```text
snapshot
+ durable event
+ assistant-stream（可选）
```

但它多一个 **active attempt baseline**：snapshot 可带 `assistantStream`，其中保留 `startedAfterSeq`、`nextIndex` 和已收到的 stream。重连时能接上进行中的半截，而不是只等最终 `assistant/message`。

mini H2 没有这个 baseline；这是有意的简化，代价是重连看不到断线前的增量。

---

## 4. H2 已经做了什么

### 4.1 Provider

- `generate(..., on_delta=None)`：可选 delta sink；无 sink 行为逐点不变。
- OpenAI 兼容 SSE：`stream: true`、`data:` / `[DONE]` 解析。
- 每个 `choices[0].delta.content` 非空片段交给 sink；最终 `AssistantTurn.content` 是拼接结果。
- `tool_calls` 按 `index` 聚合 `id` / `name` / `arguments`；工具参数片段不进正文 sink。
- usage 可选：`stream_options.include_usage`；端点 400 拒绝时退回不带它；usage 缺省零值。
- 重试只发生在首 delta 之前；已经吐过字不再重试。
- 流在 `[DONE]` 之前结束是 `PROVIDER_TRANSPORT`，不是半条 response。
- mock fixture 可声明 `deltas`，CI 能覆盖流式。

### 4.2 Kernel

- `SessionEnv.on_delta` 是可选的 `TurnDeltaSink`。
- 正常模型调用与请求级压缩后的重试都传 sink；摘要请求不传（不给 UI 发摘要正文）。
- 流式取消：不写半条 `model/response`，写 `error/abort` + `turn/end(ABORTED)`。
- 无 sink 的取消保留原行为（不改变 `ABORTED_BEFORE_DISPATCH` 等可达性）。

### 4.3 Host / SSE

- `HostSession` 每个连接一个 delta 队列；慢读者丢最旧。
- `GET /events` 合流 durable + `model/delta`；delta 无 `id`、不落日志、不参与游标。
- `snapshot` 后只送新 durable；delta 不补。
- `GET /health` 带 `features: ["delta"]`。
- 首帧延迟修复：没有 `model/response` 时也送已到的 delta。

### 4.4 验收

- 真实 deepseek：首帧 0.406–0.734 s；delta 拼接等于最终 content；日志无 delta；工具调用 `read` 拼装；中途断开 + snapshot 重连，最终 response 只有一条。
- UAT S1–S5（人跑）通过；变异 4 条全杀；Learning Gate 收 L-064。
- 门禁：`522 passed / 8 skipped`、覆盖率 95%、ruff/mypy 全绿。

---

## 5. DSH 的完整原理（H2 只对齐了一部分）

### 5.1 Provider chunk

DSH 的 `StreamChunk` 类型比 mini 的正文 delta 多：

```text
block-start { index, blockType }
text-delta { index, text }
reasoning-delta { index, text }
tool-call-delta { index, id, name?, argumentsDelta }
block-end { index, block }
usage
finish
```

- `BlockAssembler` 把 chunk 组装成完整 content block（text / reasoning / tool-call）；
- `AssistantStreamAccumulator` 把 chunk 收成紧凑带时间 stream；
- 一次成功的 attempt 最终产出一个 `AssistantTurn` 等价的 message 和 usage。

### 5.2 实时层：`agent/assistant-stream`

`AssistantStreamAttempt` 每收到一个 chunk：

1. 喂 `BlockAssembler`；
2. 喂 `AssistantStreamAccumulator`；
3. 发一个进程内 ephemeral 帧：

```text
agent/assistant-stream { frame }
  frame.start / chunk / end
  chunk.chunk = raw StreamChunk（包括 reasoning-delta）
```

这不是日志事件；它只用于当前连接的实时显示。`session/follow` 会把这些帧转成 `assistant-stream` 帧发给客户端。

### 5.3 durable 层：`assistant/message`

DSH 不把每个 delta 写成一条日志事件。一次成功 attempt 追加**一条**：

```text
assistant/message {
  turn, step,
  message: {
    content: [
      { type: "reasoning", text: "..." },
      { type: "text", text: "..." },
      { type: "tool-call", ... }
    ]
  },
  usage,
  stream: [紧凑带时间 chunk...]
}
```

- `message.content` 是完整、有序的内容块；`reasoning` 是其中一种内容类型。
- `stream` 是紧凑的带时间 chunk 序列，用于重放/诊断。
- `assistant/attempt` 保留失败/重试/取消/stream error 的 attempt，但不进模型历史。
- 原则是 **model-visible means logged**：任何进入后续模型请求的内容，都必须能从日志重建。

### 5.4 `session/follow` 与 baseline

```text
SessionFollowFrame =
  snapshot（header、cursor、records、projections，可选 assistantStream baseline）
  | durable event
  | assistant-stream（frame）
```

- durable 事件有 `seq`，gap-free；
- assistant-stream 是 cursorless 的实时帧；
- snapshot 的 `assistantStream` baseline 里保留当前 attempt 的 stream、`startedAfterSeq`、`nextIndex`；
- 重连时客户端能把“已经生成到一半”的思考/正文接上，而不是只等最终 message。

### 5.5 Shell 侧的分离

DSH 的 `ReasoningRow`：

- 思考内容单独一行，默认折叠；
- 流式时显示最新完成段落的预览；
- 点开显示完整 Markdown；
- 回答正文是另一个区域；
- usage 面板单独显示 `reasoningTokens`（output 的子集）。

也就是说：**durable 的 `assistant/message` 是完整内容块；实时 `assistant-stream` 是流；壳按 block 类型分开渲染。** 不是“先合并成一段文本，再由壳拆开”。

### 5.6 plan mode 是另一条线

`dsh-plan-mode`：

- `/plan` 进入，持久化 `plan/mode` 事件；
- `plan:policy` 提示词段落 + `exit_plan_mode` 工具；
- 工具目录不变，约束是提示词 + 沙箱/审批；
- 退出计划要人评审。

它不是 reasoning-effort，也不是本节的 `assistant/message`。mini 的 M14c 只计划 `todo` / `plan` 工具，不打算做完整 plan-mode 状态机。

---

## 6. mini 与 DSH 的对照

| 位置 | mini H2（已做） | DSH（完整原理） | mini 还没做 |
|---|---|---|---|
| Provider 正文增量 | `DeltaSink(text)`；OpenAI SSE | `StreamChunk`（text/reasoning/tool-call/usage/finish） | reasoning chunk、tool-call delta 细粒度 |
| 实时帧 | `model/delta`（无 id，ephemeral） | `assistant-stream`（无 cursor，含 reasoning） | `reasoning/delta` |
| 最终 durable | 一条 `model/response`：`content` + `tool_calls` + usage | 一条 `assistant/message`：内容块 + 紧凑 stream | reasoning 内容块、紧凑 stream |
| 失败 attempt | `error/model` + `model/retry` | `assistant/attempt`（保留 stream） | 独立 attempt 事件 |
| 重连 baseline | 无；只补 durable | snapshot 可带 active `assistantStream` | 进行中半截的 baseline |
| 思考强度 | 无 | `thinking` + `reasoningEffort` | 档位、请求头、历史回传 |
| UI 思考区 | 无 | `ReasoningRow` 折叠/预览 | 思考区 |
| plan mode | 无；M14c 计划 todo/plan | `dsh-plan-mode` 状态机 | 完整 plan-mode 不做 |

---

## 7. 未来的 `reasoning/delta` 与 mini 的落点

如果按计划在 M10 之后做 `reasoning-mode-and-budget`，mini 的目标形状是：

```text
event: reasoning/delta
data: {"turn_id":"t1","index":0,"text":"..."}
```

以及最终：

```json
{
  "type": "model/response",
  "payload": {
    "content": "最终回答",
    "reasoning": "最终思考文本",
    "tool_calls": [],
    "usage": {"input_tokens": 100, "output_tokens": 50, "reasoning_tokens": 30},
    "finish_reason": "stop"
  }
}
```

原则：

1. **一条 durable `model/response` 仍唯一**；reasoning 合进这条记录，不按 delta 写日志。
2. `reasoning/delta` 是独立 ephemeral 帧，不能混进 `model/delta`。
3. `fold` 重建 `Message.reasoning` 并回传；历史 reasoning 参与后续请求。
4. 日志体积/敏感内容先照 DSH：durable 保存完整 reasoning，UI 默认折叠。
5. `reasoning_tokens` 是 `output_tokens` 子集，不重复计；回传进上下文另按上下文预算算。
6. 暂缓：紧凑带时间 stream、单独 `assistant/attempt`、完整 content-block 重构、DSH 式 active baseline、完整 plan-mode。

详细决策见 `docs/reference/reasoning-mode.md`。

---

## 8. 常见误解

| 误解 | 实际 |
|---|---|
| `model/delta` 是日志事件 | 它是传输层 ephemeral 帧，不落日志 |
| delta 拼接就是 `model/response` | 最终 response 由同一次 provider 调用产出；日志不保存 delta 序列 |
| `sink` 是日志缓冲区 | sink 是回调出口；H2 的日志只记最终 response |
| snapshot 后可以任意重放 delta | delta 不参与 snapshot/游标；重连不补 |
| H2 把思考也流了 | H2 明确只流可见正文，不发 reasoning |
| DSH 的思考只存在于流里 | durable `assistant/message` 里也有 reasoning 内容块和紧凑 stream |
| DSH 的思考先合并成一段再由壳拆 | 实时帧本来就分类型；durable 也是内容块 |
| `model/delta` 的 `id` 可以当游标 | 它没有 `id`；游标只由 durable `seq` 推进 |
| 首帧测试通过就说明没有缓冲 | 顺序对不代表实时；H2 的首帧 1.2 s 就是反例 |

---

## 9. 代码地图

mini：

| 文件 | 责任 |
|---|---|
| `src/mini_harness/provider/contract.py` | `DeltaSink` / `TurnDeltaSink` / `generate` 契约 |
| `src/mini_harness/provider/openai_compat.py` | SSE 解析、tool_calls 拼装、首 delta 重试边界 |
| `src/mini_harness/loop/turn_loop.py` | `_forward_delta`；把 sink 传给 provider；最终 response 落账 |
| `src/mini_harness/session/host.py` | `subscribe_deltas` / `publish_delta`；有界队列丢最旧 |
| `src/mini_harness/cli/host.py` | `_events` 合流、`_delta_frame`、snapshot、health features |
| `src/mini_harness/cli/serve.py` | `sse_frame`：durable 帧编码 |
| `src/mini_harness/events/reader.py` | `LogTail`：durable 增量读 |
| `src/mini_harness/events/writer.py` | `EventLog`：唯一 append/seq |

DSH（`re/verified/dsh/node_modules/@deepseek-ai/...`）：

| 文件 | 责任 |
|---|---|
| `dsh-llm/lib/index.js` | `BlockAssembler`、`AssistantStreamAccumulator`、chunk 类型 |
| `dsh-llm-deepseek/lib/index.js` | `thinking_delta` → `reasoning-delta`；`thinking`/`reasoningEffort` |
| `dsh-agent-loop/lib/index.js` | `AssistantStreamAttempt`、`agent/assistant-stream`、`assistant/message` 落账 |
| `dsh-session/README.md` | `assistant/message` + compact stream、`assistant/attempt` |
| `dsh-api-session-controller/lib/types/history.js` | `session/follow` 帧与 active baseline |
| `dsh-client-ui-chat/lib/client.js` | `ReasoningRow` 折叠预览 |
| `dsh-plan-mode/README.md` | plan mode 独立状态机 |

规格与术语：

- H2 主规格：`openspec/specs/host-api/spec.md`、`openspec/specs/provider/spec.md`
- H2 设计底稿：`docs/reference/host-streaming.md`
- 思考模式计划：`docs/reference/reasoning-mode.md`
- 四层与 H1 控制面：`docs/reference/runtime-layers-and-control-plane.md`

---

## 10. 一句话总结

**H2 做的是：provider 正文增量 → Kernel 的 turn-aware sink → Host 每连接队列 → SSE 的 durable + `model/delta` 合流；日志只记最终 `model/response`。**

**DSH 多做的是：reasoning 也是一种 chunk / content block；实时 `assistant-stream` 与 durable `assistant/message`（内容块 + 紧凑 stream）分工，`session/follow` 还能用 baseline 接上进行中的半截，壳再按块类型分成思考区和回答区。**

**mini 还没做的是：reasoning 的 provider/档位/预算/历史回传、`reasoning/delta`、最终 `model/response.reasoning`、思考区 UI，以及 DSH 的 compact stream / attempt / baseline / plan mode。**
