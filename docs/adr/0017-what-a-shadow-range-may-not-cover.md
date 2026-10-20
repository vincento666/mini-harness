---
status: accepted
---

# 摘要不能被它自己摘要的东西遮蔽：`session/start` 与既有摘要不进遮蔽范围

一次压缩遮蔽哪一段，裁决两条保护与一条标记。`session/start` 不进范围——它是头部（含可用工具名列表）与窗口参数的唯一来源，遮蔽它等于下一次装配没有头部可派生，replay 也判不了。既有的 `compaction/summary` 不进范围——遮蔽一条摘要等于把摘要本身也忘掉，多次压缩就失去连续性。摘要调用本身照常被观测：它走同一个 `generate`，落 `model/request` 与 `model/response`，带 `purpose: "compaction"`，折叠时**不产出 assistant 消息**（否则模型会在表层看到「自己要求做摘要」这一轮，并可能照着它继续摘要）。

Considered options：摘要调用不落盘（否：不变量 F 全程可观测，且 replay 要能重算出遮蔽范围是怎么来的）；摘要落盘但不标记（否：不标记就会被折叠成一条 assistant 消息进表层，也会被预算校准当成一次可信读数）；把 `session/start` 也遮蔽、头部另存（否：等于第二份真源，与 ADR-0015 相反方向）。

Consequences：遮蔽范围里必须至少有一条产出消息的记录，否则这次压缩没有意义，`shadowed_range` 返回 `None`（「没有可遮蔽的内容」）而不是一个空范围；切点落在一组工具往返内部时整组一起遮蔽，不许把一条超预算的 assistant 请求单独拉进尾部。
