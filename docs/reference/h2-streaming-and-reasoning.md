# 流式、sink 与思考帧：实现原理与 DSH 对照

**用途**：把流式回复、`sink`、`model/delta`、`reasoning/delta`、SSE 合流与 DSH 的 `assistant-stream` / `assistant/message` 讲成一条线。只解释实现原理；读完应该能回答：

- 外部模型 API 的 SSE 怎么变成 mini 的 delta；
- `sink` 是回调、队列还是日志，谁把 delta 交给谁；
- 为什么 `model/delta` 不落日志，而 `model/response` 是唯一 durable 真相；
- `GET /sessions/{id}/events` 怎么把 durable 与 ephemeral 合到一条 SSE 上，顺序怎么保证；
- DSH 的 `assistant-stream` / `assistant/message` / `reasoning-delta` 各在哪一层；
- 思考内容要进入模型上下文，需要经过哪些层，不能只加一个字段。

术语以 mini 为主；mini 没有的概念用 DSH 原名。

---

## 0. 总图：外部 API、日志、两种帧

```text
外部模型 API（OpenAI 兼容 /chat/completions，stream=true）
   │  HTTP POST + Bearer key（key 只从环境变量名解析，不进日志）
   │  SSE: data: {...}\n\n ... data: [DONE]
   ▼
┌──────────────── Provider 适配器（httpx stream）────────────────┐
│ 解析 data / [DONE]；tool_calls 按 index 拼装；usage 可选        │
│ 正文片段 → DeltaSink(text)                                      │
│ 最终 → AssistantTurn(content, tool_calls, usage, finish_reason) │
└───────────────────────────────┬─────────────────────────────────┘
                                │ final turn / delta
┌───────────────────────────────▼─────────────────────────────────┐
│ Kernel（turn_loop）                                              │
│ 装配 → provider.generate(..., on_delta=forward)                 │
│ forward(text) → env.on_delta(turn_id, text)                     │
│ 最终写 model/request、model/response 到日志                     │
└───────────────┬───────────────────────────────┬─────────────────┘
                │ append                         │ TurnDeltaSink
                ▼                                ▼
        ┌───────────────┐              ┌──────────────────────────┐
        │ 日志 JSONL     │              │ Host                     │
        │ durable 真相   │              │ 每 SSE 连接一个 delta 队列│
        └───────┬───────┘              └──────────┬───────────────┘
                │ fold / LogTail                   │
                ▼                                  ▼
        ┌───────────────┐              ┌──────────────────────────┐
        │ 表层 messages │              │ SSE 合流                  │
        │ 模型上下文     │              │ durable 帧 + model/delta  │
        └───────────────┘              └──────────┬───────────────┘
                                                  ▼
                                        ┌──────────────────┐
                                        │ Shell / UI       │
                                        │ 正文区 + 事件回显 │
                                        └──────────────────┘
```

三条独立事实：

1. **日志**记 durable 事实（请求、完整响应、工具、边界、错误）；
2. **表层**是 `fold(日志前缀)` 给模型的上下文；
3. **SSE** 是日志镜像 + 当前正在发生的 ephemeral 增量，不是第二份日志。

---

## 1. 三个时间尺度：请求、回合、段

```text
段（segment）
├─ segment/start
├─ 回合 t1
│  ├─ context/assembled
│  ├─ model/request
│  ├─ model/response
│  ├─ tool/call ×N
│  ├─ tool/result ×N
│  └─ turn/end
├─ 回合 t2 ...
└─ segment/end
```

- **回合** = 一次模型请求/响应 + 响应里声明的工具批次；
- **段** = 一条输入展开的一串回合；
- `model/delta` 只属于某一个回合，`turn_id` 就是它的归属；
- 一帧不等于一步：一个回合有多条 durable 记录，delta 只是其中一次调用的过程。

---

## 2. 两种帧：durable 与 ephemeral

### 2.1 durable

```text
id: <seq>
event: <记录类型>
data: <日志整行 JSON>
```

- `id` 是日志 `seq`；帧与日志逐字段相等；
- `Last-Event-ID` / `?from=` 只推进 durable 的 `seq`；
- 日志里有什么，durable 就能重放什么。

### 2.2 ephemeral

```text
event: model/delta
data: {"turn_id":"t1","index":0,"text":"你"}
```

- 无 `id`；不参与游标；
- 不落日志；重连不补；
- 顺序：`model/request` → 若干 `model/delta` → `model/response`；
- 最终正文以 `model/response.content` 为准，delta 只用于“正在生成”的显示。

### 2.3 snapshot

```text
日志：0 ... 93 94 95 | 96 97 ...
                  ▲
                  snapshot 读 0..95，last_seq=95
                  messages = fold(0..95)

?snapshot=1：
  第一帧  event: snapshot（无 id；last_seq + messages）
  之后    id=96, 97, ... durable
  delta   只发连接之后产生的，不补
```

snapshot 是**前缀折叠**，`last_seq` 是前缀终点，不是起点；它不是“最后一回合的结果”。

---

## 3. `sink`：从 provider 到 SSE 的回调链

### 3.1 外部 API 到 provider

外部 API 一次流式请求：

```text
POST <base-url>/chat/completions
{
  "model": "...",
  "messages": [...],
  "tools": [...],
  "stream": true,
  "stream_options": {"include_usage": true}
}
```

响应是 SSE：

```text
data: {"choices":[{"delta":{"content":"你"},"finish_reason":null}]}
data: {"choices":[{"delta":{"content":"好"},"finish_reason":null}]}
data: {"choices":[{"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

适配器只把正文片段交给 sink；`tool_calls` 的 `arguments` 片段按 `index` 拼装，不交给正文 sink；usage 在最终 response 里。

### 3.2 三层 sink

```python
# provider 只认正文
DeltaSink = Callable[[str], Awaitable[None]]

# kernel 给片段加回合归属
TurnDeltaSink = Callable[[str, str], Awaitable[None]]  # turn_id, text

async def forward(text: str) -> None:
    await env.on_delta(turn_id, text)
```

```text
provider.generate(..., on_delta=forward)
        │ await forward("你")
        ▼
env.on_delta(t1, "你")
        │
        ▼
HostSession.publish_delta(t1, "你")
        │ put_nowait({turn_id, index, text})
        ▼
每个 SSE 连接的 asyncio.Queue
        │
        ▼
event: model/delta（无 id）
```

- provider 不知道 turn；
- kernel 不消费 delta，只负责归属；
- host 不写日志，只广播；
- shell 不反推日志，只按帧渲染。

### 3.3 有界队列与慢读者

- 每个连接一个队列，上限 256；
- 队列满时丢最旧（ephemeral 可丢）；
- 不反压 provider；
- 连接断开就退订；durable 仍可从日志续读，最终 `model/response` 校正屏幕。

---

## 4. 合流：durable `LogTail` + delta 队列

### 4.1 顺序算法

```text
subscribe delta queue
tail = LogTail(after=cursor)

loop:
  records = tail.read_new()
  for record in records:
      if record.type == "model/response":
          drain delta queue        # 先补完它之前的增量
      write durable record
  drain delta queue                # 还没有 response 时也要实时送
  sleep(poll)
```

两个要点：

1. **不能先把所有 delta 写完再写 durable backlog**：backlog 里可能有 `session/start`、`segment/start`，delta 会排到它们前面。
2. **不能只在 `model/response` 时排空**：没有 response 前 delta 会被憋到整段结束，首帧延迟变成“整段生成时间”。

### 4.2 一次调用的帧顺序

```text
model/request (durable)
  ├─ model/delta #0
  ├─ model/delta #1
  └─ ...
model/response (durable)
```

为什么顺序稳定：provider 在返回最终 turn 之前，已经 `await` 过每个 delta 回调；kernel 收到最终 turn 后才写 `model/response`。单事件循环里，delta 入队先于 response 落日志。

### 4.3 重连

```text
连接 A：看到 model/request → delta #0..#5 → 断开
连接 B：?snapshot=1
  第一帧 snapshot（last_seq=当前 durable 高水位）
  之后的 durable 从 last_seq+1 开始
  delta 不补；最终 model/response 到达后整段替换
```

这不是丢帧：delta 不是 durable 事实；重连的正确性以 `model/response` 为准。

---

## 5. Provider 流式的边界

### 5.1 重试

```text
首 delta 之前 429/5xx → 可重试一次
首 delta 之后失败     → 不重试，塌成失败结果
```

原因：已经吐过字的流再重发，会在屏幕上留下两遍开头。重试事实由 provider 带回，kernel 写 `model/retry`；provider 自己不写日志。

### 5.2 失败与取消

- 流在 `[DONE]` 之前结束：失败结果，不是半条 `model/response`；
- 取消：停止读流，kernel 写 `error/abort` / `turn/end(ABORTED)`；
- 已经显示的 delta 不回滚，但最终 response 不写半条。

### 5.3 tool_calls

```text
data: {"delta":{"tool_calls":[{"index":0,"id":"c1",
        "function":{"name":"read","arguments":"{\"file"}}]}}
data: {"delta":{"tool_calls":[{"index":0,
        "function":{"arguments":"_path\":\"a.md\"}"}}]}}

最终 AssistantTurn.tool_calls = [
  {id:"c1", name:"read", arguments:{file_path:"a.md"}}
]
```

工具参数片段不进正文 sink；最终 `model/response.tool_calls` 是完整调用。

---

## 6. 思考帧：mini 的目标与 DSH 的完整实现

### 6.1 mini 当前没有

mini 的 `model/response` 只有：

```text
content: str
tool_calls: [...]
usage: {input_tokens, output_tokens}
finish_reason
```

没有 reasoning 内容块，也没有 `reasoning/delta`。H2 明确只流可见正文。

### 6.2 目标形状（原理）

```text
实时：
  event: reasoning/delta
  data: {"turn_id":"t1","index":0,"text":"..."}

durable：
  model/response {
    blocks: [
      {type:"reasoning", text:"先看 note.md"},
      {type:"tool-call", id:"c1", name:"read", arguments:{file_path:"note.md"}},
      {type:"reasoning", text:"读到了 alpha/beta"},
      {type:"text", text:"note.md 里是 alpha 和 beta。"}
    ],
    usage: {..., reasoning_tokens: 30},
    finish_reason
  }
```

- 思考与回答是两条实时流，不能混进同一个 `model/delta`；
- 只写一条 durable `model/response`，不按 delta 写日志；
- `fold` 保留 block 顺序；`content` / `tool_calls` 若保留，只能是 blocks 的派生投影，不能双写真源；
- 后续请求按协议回传 blocks；只加一个 `reasoning` 字符串不能表达 reasoning/text/tool-call 的交错；
- `reasoning_tokens` 是 `output_tokens` 的子集，不重复计。

### 6.3 DSH 的完整流程

```text
外部 DeepSeek API（Messages / thinking）
        │ content_block_delta: thinking_delta
        ▼
StreamChunk: reasoning-delta { index, text }
        │
        ├─ BlockAssembler → content block {type:"reasoning", text}
        ├─ AssistantStreamAccumulator → 紧凑带时间 stream
        └─ agent/assistant-stream 帧（进程内、ephemeral）
                │
                ├─ 实时：session/follow 的 assistant-stream 帧 → UI
                │
                └─ 结束：一条 assistant/message（durable）
                        message.content = [
                          {type:"reasoning", text},
                          {type:"text", text},
                          {type:"tool-call", ...}
                        ]
                        stream = [...]
```

关键点：

- DSH **不按 delta 写日志**；一条成功 attempt 只有一条 `assistant/message`；
- 实时帧是 typed 的：`reasoning-delta` 与 `text-delta` 分开，壳按类型分流；
- durable 的 `message.content` 也保留块类型，重放/重开能恢复“哪段是思考、哪段是回答”；
- `assistant/attempt` 保留失败/重试/取消的 stream，但不进模型历史。

### 6.4 DSH 的重连 baseline

```text
session/follow：
  snapshot {
    header, cursor, records,
    assistantStream?: {
      revision, activeAttempt: {startedAfterSeq, nextIndex, stream}
    }
  }
  + durable event
  + assistant-stream frame（cursorless）
```

重连时，DSH 能把进行中的半截接上；mini 没有这个 baseline，只补 durable，最终 response 校正。

### 6.5 DSH 的 UI 分离

```text
assistant/message.content:
  reasoning block → ReasoningRow（默认折叠，流式显示最新段落预览）
  text block      → 回答正文
  tool-call block → 工具调用行
```

不是“先把思考与回答合并成一段文本，再由壳拆开”；传输与 durable 都是 typed 的。

---

## 7. 思考内容如何进入模型上下文

这是“先思考再行动”能否成立的关键。

```text
第 1 次模型调用：
  provider 产生 reasoning-delta + text/tool-call
        │
        ▼
  assistant/message.content = [reasoning, text?, tool-call?]
        │
        ├─ 实时：reasoning-delta → 壳思考区
        └─ durable：日志
                │
                ▼
第 2 次模型调用前：
  fold(日志) 重建 Messages
  assistant message 同时带 reasoning 与 tool-call / text
        │
        ▼
  provider 把历史 reasoning 按协议回传（DSH：原样传回）
        │
        ▼
  模型在第 2 个回合看到自己上一轮的思考，再决定下一步
```

要点：

- **只有把 reasoning 放进 assistant message 的块里，并让 provider 在后续请求回传，模型才真正“看到自己之前的思考”**；只把 reasoning 写进日志、不给模型，不算进入上下文。
- **这并不强制“行动前先思考”**：它是模型能力 + 历史回传；模型仍可能直接调工具。若要在 harness 层强制“先写计划再行动”，需要的是计划工具 / 计划状态，不是 reasoning 字段。
- **“边思考边行动”** 依赖 provider 是否允许 reasoning 与 tool-call 交错、以及历史是否保留这种顺序。DSH 用内容块保留了顺序；mini 若只加一个 `reasoning` 字符串，只能表达“思考在回答之前”，不能表达任意交错。
- **协议不同不能直接照搬**：DSH 的 DeepSeek 适配器走 Messages 的 thinking block；mini 的 deepseek 走 OpenAI 兼容 chat completions，字段与回传规则要按该协议验证。把 reasoning 当普通文本塞回 messages，可能被模型忽略或改变行为。

---

## 8. 常见误解

| 误解 | 实际 |
|---|---|
| `model/delta` 是日志事件 | 它是传输层 ephemeral 帧 |
| delta 拼接就是 `model/response` | 最终 response 由同一次调用产出；日志不存 delta 序列 |
| `sink` 是日志缓冲区 | sink 是回调出口；日志只记最终 response |
| snapshot 后可以任意重放 delta | delta 不参与 snapshot/游标 |
| 思考只在流里 | DSH 的 durable `assistant/message` 有 reasoning 内容块与紧凑 stream |
| 思考先合并再由壳拆 | 实时帧与 durable 块本来就 typed |
| 把 reasoning 写进日志就等于模型看到了 | 必须进 assistant message 并在后续请求回传 |
| reasoning 字段能强制先计划再行动 | 不能；强制计划是另一层 |
| 首帧顺序对就说明没有缓冲 | 顺序对不代表实时；缓冲会拖到整段结束 |

---

## 9. 代码地图

mini：

| 文件 | 责任 |
|---|---|
| `src/mini_harness/provider/contract.py` | `DeltaSink` / `TurnDeltaSink` / `generate` 契约 |
| `src/mini_harness/provider/openai_compat.py` | 外部 API SSE、tool_calls 拼装、重试边界 |
| `src/mini_harness/loop/turn_loop.py` | `_forward_delta`；最终 `model/response` 落账 |
| `src/mini_harness/session/host.py` | `subscribe_deltas` / `publish_delta`；有界队列 |
| `src/mini_harness/cli/host.py` | `_events` 合流、`_delta_frame`、snapshot |
| `src/mini_harness/cli/serve.py` | `sse_frame`：durable 帧编码 |
| `src/mini_harness/events/reader.py` | `LogTail` |
| `src/mini_harness/events/writer.py` | `EventLog`：append / seq |

DSH（`re/verified/dsh/node_modules/@deepseek-ai/...`）：

| 文件 | 责任 |
|---|---|
| `dsh-llm/lib/index.js` | `BlockAssembler`、`AssistantStreamAccumulator`、chunk 类型 |
| `dsh-llm-deepseek/lib/index.js` | `thinking_delta` → `reasoning-delta` |
| `dsh-agent-loop/lib/index.js` | `AssistantStreamAttempt`、`agent/assistant-stream`、`assistant/message` |
| `dsh-session/README.md` | `assistant/message` + compact stream、`assistant/attempt` |
| `dsh-api-session-controller/lib/types/history.js` | `session/follow` 帧与 baseline |
| `dsh-client-ui-chat/lib/client.js` | `ReasoningRow` |

---

## 10. 一句话总结

**mini 的流式是：外部 API 的 SSE → provider 正文 sink → kernel 的 turn-aware sink → host 每连接队列 → durable + `model/delta` 合流；日志只记最终 `model/response`。**

**思考要真正进入模型行动前的上下文，必须多走一步：reasoning 进入 assistant message 的内容块，`fold` 重建，provider 在下一请求回传。只加日志或只加 UI 都不算。**

**DSH 已经把这一步做成 typed 的 `reasoning` 内容块 + 实时 `assistant-stream` + durable `assistant/message`；mini 目前只有正文流，思考帧与历史回传还没有。**
