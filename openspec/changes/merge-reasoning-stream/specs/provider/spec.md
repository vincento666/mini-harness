# Spec Delta

## MODIFIED Requirements

### Requirement: 适配器把 reasoning 解析成独立的块与 sink

OpenAI 兼容适配器 SHALL 从响应的 `reasoning_content` / `reasoning` 字段构造 `ReasoningBlock`，与 `TextBlock`、`ToolCallBlock` 按 provider 给出的顺序组成 `blocks`；`AssistantTurn.content` 与 `tool_calls` 仍是投影，`blocks` 是真相。流式时 reasoning 增量 SHALL 走独立的 reasoning sink（`(step_id, index, text)`），MUST NOT 混进正文 sink。

`usage.completion_tokens_details.reasoning_tokens` 或顶层 `reasoning_tokens` SHALL 解析进 `Usage.reasoning_tokens`，它是 `output_tokens` 的子集、不重复计；缺失按 0。

#### Scenario: 非流式响应带 reasoning

- **WHEN** 响应体含 `reasoning_content: "先想"` 与非空 `content`
- **THEN** `blocks` 依次是 reasoning、text；`content` 等于正文；`usage.reasoning_tokens` 取自 details

#### Scenario: 思考与正文分流

- **WHEN** 流式响应交错给出 reasoning 与正文片段
- **THEN** 正文 sink 只收到正文、reasoning sink 只收到 reasoning，两条流都按 step_id 归属

#### Scenario: 流式思考只带 `reasoning` 字段（OpenRouter 归一）

- **WHEN** 流式 delta 里只有 `reasoning`（无 `reasoning_content`），随后才给 `content`
- **THEN** reasoning sink 照常收到增量、`blocks` 里是 reasoning → text，正文流不受影响
