# M12 DSH parity review

**日期**：2026-11-06。对照点来自 `docs/reference/subagents.md` 与 `docs/dsh-reference/DSH运行时设计说明.html` 的委派章节。

| 行为 | DSH | mini | 结论 | 记账 |
|---|---|---|---|---|
| 子代理 spawn | 有（空对话起步，提示词自足） | 有（`subagent` 工具，`task` 必填、不 seed 父历史） | aligned | — |
| 子代理 fork | 有（截至最后一个 `turn/end` 的配平前缀，逐字节一致换缓存命中） | 不做 | deferred | ADR-0035；触发条件：需要 KV cache 复用且宿主协议允许 fork 语义 |
| 深度 | `depth = 父 + 1` 写进子级 header；`maxDepth` 默认 1，0 禁止委派 | 同左；`DEPTH_EXCEEDED` 是 `tool/result` 的结果词 | aligned | — |
| 容量 | 第 9 个可续接子级撞 `maxActiveSubagents = 8`，报 `ACTIVATION_LIMIT_REACHED` / `subagent/delivery-unavailable` | 每父会话 8 个活跃子代理，报 `ACTIVATION_LIMIT_REACHED` | simplified | mini 只有 spawn、没有「可续接子级」，所以没有 `subagent/delivery-unavailable` 这条投递失败词；额度按「每个父会话」计，不做全局投递池；工具并发上限也是 8，同一批 9 个不会撞额度（design D8） |
| 审批 | 权限不继承，但沙箱覆盖与 `never` 钉定继承；子级问人只能得到不可用 | 同左：`approval` 模式随档位继承，一次性放行不继承，审批门固定 `UNAVAILABLE` | aligned | design D4 |
| 子级工具作用域 | `scope.tools = 组合过滤(非授权继承)` | 默认继承父的工具表，`tools` 参数只能收窄、且不是权限边界 | simplified | 父的围栏档位仍是唯一约束；`tools` 是上下文经济选项，不是授权闸门 |
| 同批并发 | 工具批调度里只读调用并发 | `subagent` 标 `parallel`，同批真并发、结果按完成顺序落盘 | aligned | M10 的批调度；判据 `test_two_subagents_run_in_parallel` |
| 取消 | 运行结果永不拒绝，标记 `cancelled` | 父段取消 → 子会话按 `ABORTED` 收尾，父那条是 `TOOL_CANCELLED` | simplified | 取证材料没有写死「父取消是否级联所有子级」；mini 取「本段派生且仍在跑的才收」，已完成结果保留（design D6） |
| 结果形状 | 子级最终结果（投递失败另有词） | 最后一条非摘要 `model/response` 的正文；没有正文时一句说明；模型/内核失败是 `TOOL_IO_FAILED`；围栏拒绝是 `DENIED_BY_APPROVAL` / `DENIED_BY_FENCE` | simplified | 不返回产物清单与投递状态；产物路径若有会出现在正文里（ADR-0036）；拒绝词让父能分清「没做成」与「做成了」（design D10） |

**判据**：每个 spec/design 里出现的 DSH 对照点都有一行；`simplified` 都写了代价，`deferred` 都写了触发条件。
