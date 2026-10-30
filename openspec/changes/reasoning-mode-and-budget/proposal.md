# Proposal

## Why

mini 现在的 assistant message 只有 `content: str` + `tool_calls`，实时输出只有一条 `model/delta`。reasoning 只能被塞成正文的一部分，壳体也无法把「思考」与「回答」分开；DSH 的 `assistant/message` 用有序 content blocks 表达 reasoning / text / tool-call 的交错。

这一片把 assistant message 升级成**有序 content blocks**，新增独立的 ephemeral `reasoning/delta`，并把思考强度与 reasoning token 口径固定下来；模型工具面、工具执行与 H2 的 `model/delta`/durable 帧形状不变。

## What Changes

- **`AssistantTurn.blocks`**：`reasoning` / `text` / `tool-call` 三类块，保序；`content` / `tool_calls` 仅作为 blocks 的派生投影保留，供旧代码与旧日志读取。
- **`model/response.blocks`**：一次成功调用仍只写一条 durable 记录；完整 reasoning 内容进日志；delta 不进日志。
- **`reasoning/delta`**：新的 ephemeral SSE 事件，`turn_id` + `index` + `text`；无 `id`、不落日志、不参与游标；与 `model/delta` 并列。
- **Provider sink 分流**：`ReasoningSink` 与正文 `DeltaSink` 分开传入；适配器 MUST NOT 把 reasoning 混进正文 sink。
- **坏标签容错**：核心层不解析标签；adapter 的标签协议在开标签确认后**乐观 emit** reasoning，只留小尾缓冲等闭标签。半开（EOF 未闭合）/半闭/嵌套一律 `PROVIDER_SCHEMA_INVALID`、不写 `model/response`；已发出的 live reasoning 由壳清掉。空 reasoning 丢弃；只有 reasoning 时保留 blocks、`content` 为空，不冒充正文。
- **思考强度**：`reasoning_effort` 配置 `off|low|high|max`；不支持的档位在网络 I/O 前失败；有效值随请求记录。
- **usage**：`reasoning_tokens` 是 `output_tokens` 的子集；成本/计量不重复加；上下文预算按普通文本计入回传的 reasoning。
- **fold/replay**：`fold` 从 blocks 重建有序消息；旧日志没有 blocks 时行为逐点不变。
- **host SSE**：`reasoning/delta` 与 `model/delta` 都走现有 SSE 通道；重连不补 delta，最终 `model/response` 带 blocks。

## Capabilities

### New Capabilities

- `reasoning`：assistant content blocks、reasoning delta、durable 记录、思考强度、reasoning token 口径、fold/replay 与 SSE。

### Modified Capabilities

无。现有 `provider` / `turn-loop` / `host-api` 的约束继续成立；本 change 是在 assistant message 上增加 blocks，并保留旧字段投影。

## Impact

- 代码：`provider/contract.py`（Block/AssistantTurn）、`provider/openai_compat.py` / `mock.py`（reasoning 解析与 sink）、`events/fold.py`（blocks→Message）、`loop/turn_loop.py`（sink 转发、response blocks）、`session/host.py` + `cli/serve.py`（SSE 事件）、`config`（reasoning_effort）。
- 测试：seam ⑤ provider、seam ① 回合/日志、seam ④ fold/replay、seam ⑥ SSE。
- 规格：新 capability `reasoning`。
- 验收：真实 reasoner 一次长回复；UAT 思考区/回答区分开；变异 3 条；Learning Gate。

## Non-Goals

- DSH 的紧凑带时间 stream、`assistant/attempt` 事件、active attempt baseline。
- 完整 plan-mode 状态机、自动摘要/脱敏。
- 把 reasoning 当可见回答；默认折叠。
- 跨 provider/model 路由回传；默认同一路由原样。
