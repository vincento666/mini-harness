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

用 adapter 的标签模式发：只有开标签、只有闭标签、流结束仍未闭合三种。

**预期**：三种都 `PROVIDER_SCHEMA_INVALID`，没有 `model/response`；不出现半条 reasoning 或半条正文。

## R7 · 只有 reasoning

让 provider 返回 reasoning 但没有正文。

**预期**：blocks 保留 reasoning，`content` 投影为空；壳显示“无正文”，不把 reasoning 当回答。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| R1 | 读文件后回答 | 思考/正文分开 | | | |
| R2 | 折叠/展开 | 默认折叠 | | | |
| R3 | 无 reasoning 模型 | 行为不变 | | | |
| R4 | usage | 不重复计 | | | |
| R5 | effort off/high | off 无思考 | | | |
| R6 | 半标签/坏标签 | `PROVIDER_SCHEMA_INVALID` | | | |
| R7 | 只有 reasoning | 保留 blocks / 无正文 | | | |

**至少一条「用起来别扭」**：_

**结论**：通过 / 不通过（写清场次、session id、SSE 证据）：_
