# Reasoning 模式与预算 UAT

**状态**：等人跑（ADR-0025）。

**怎么算办一件真事**：让模型做一次需要先思考再调工具的任务，观察思考区与回答区是否分开、折叠是否工作、长思考是否把回答挤掉，以及 usage 里 reasoning 是否被重复计。

## 跑之前

- 真实 reasoner 端点（DeepSeek reasoner 或支持的模型）；`DEEPSEEK_API_KEY`。
- 工作区 `.tmp/reasoning-uat/ws`，准备 `notes.md` 与一个需要读文件再回答的问题。
- 记录 session id、SSE 原始帧、`model/response` 的 blocks 与 usage。

## R1 · 思考与回答分开

提示：`先读 notes.md，再根据内容回答：里面有几个 TODO？`

**预期**：SSE 先出现 `reasoning/delta`，再出现 `model/delta`；两者不混。最终 `model/response.blocks` 保留 reasoning/text/tool-call 顺序。

## R2 · 折叠与展开

在壳里观察思考区：流式时显示最新段落预览；结束后可展开完整 reasoning；回答区独立。

**预期**：默认折叠；展开可读；长思考不把回答挤出视口。

## R3 · 无 reasoning 的模型

用不返回 reasoning 的 provider 跑同一提示。

**预期**：只有正文/工具；日志、SSE、fold 与今天逐点相同（除新空字段）。

## R4 · reasoning tokens

记录 `usage.output_tokens` 与 `reasoning_tokens`。

**预期**：reasoning_tokens ≤ output_tokens；成本/计量不按两者之和。

## R5 · effort

配置 `reasoning_effort=off` 与 `high` 各跑一次。

**预期**：off 无 reasoning；high 有；不支持档位在请求前失败。

## R6 · 半标签/坏标签

用 adapter 的标签模式发：开标签后正常流式、只有闭标签、流结束仍未闭合三种。

**预期**：开标签后 reasoning 立即出现；半开结束时 `PROVIDER_SCHEMA_INVALID`，没有 `model/response`；日志有 `model/attempt`（错误码 + 已收前缀），壳清掉 live reasoning；不留下半条正文/思考。

## R7 · 只有 reasoning

让 provider 返回 reasoning 但没有正文。

**预期**：blocks 保留 reasoning，`content` 投影为空；壳显示“无正文”，不把 reasoning 当回答。

## R8 · 用户取消

在 reasoning/text 已经显示后取消；另跑一次首个 delta 前取消。

**预期**：前者只写 `model/response(interrupted:true)` 带已交付前缀，不写 `model/attempt`，下一轮包含；后者只写 `model/attempt`，不写空锚点，按 ABORTED 收尾。坏标签失败只写 `model/attempt`，不写 interrupted。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| R1 | 读文件后回答 | 思考/正文分开 | session `e782b7be...`：blocks `reasoning → text`；session `e8a28659...`：tool-call 回合 + `reasoning → text` 回合 | 通过 | 真实模型不保证一次响应里 reasoning→tool→reasoning→text 全出现 |
| R2 | 折叠/展开 | 默认折叠 | 未跑：需要壳的视觉确认 | 待确认 | agent 不能替代视觉检查 |
| R3 | 无 reasoning 模型 | 行为不变 | session `e50213e6...`（`deepseek-chat`，off）：blocks 只有 `text` | 通过 | 无 |
| R4 | usage | 不重复计 | `e782b7be...`：`output_tokens=266`、`reasoning_tokens=143`；不按 409 计 | 通过 | 无 |
| R5 | effort off/high | off 无思考 | off：`e50213e6...` 只有 text；high：`e782b7be...` 有 reasoning | 通过 | 无 |
| R6 | 半标签/坏标签 | 先 emit；EOF 报错 + `model/attempt` 证据 | `tests/test_reasoning_tags.py`：开标签后先 emit、EOF/孤立闭标签/嵌套均 `TagReasoningError`；`test_schema_failure...` 写 `model/attempt`、不写 response | 通过（adapter 单测） | 产品没有可切换的 tag adapter，只有单测路径 |
| R7 | 只有 reasoning | 保留 blocks / 无正文 | `test_only_reasoning_keeps_blocks_and_empty_content`：reasoning block + `content=""` | 通过（单测） | 真实端点未复现“只有 reasoning”的响应 |
| R8 | 用户取消 | interrupted 前缀进历史 | `test_cancel_with_reasoning_prefix...`：只写 interrupted response；`test_schema_failure...`：失败只写 attempt | 通过（单测） | 需要构造取消时序，不是产品 UI 点击 |

**至少一条「用起来别扭」**：R2 的折叠/展开必须在真实壳里看；R6–R8 目前只能靠单元测试/构造时序，产品没有 tag adapter 或取消注入开关。

**结论**：非视觉部分通过；**R2 折叠/展开明确延后到壳实现后**（2026-11-01 决定），本 change 因此不归档、不合入 `main`。agent 代跑范围依据用户 2026-11-01 授权。
