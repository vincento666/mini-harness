---
status: proposed
---

# 计划模式在派发前硬拦写类工具

DSH 的 plan mode 是**软引导**：只注入 `plan:policy` 提示，写不写由 sandbox 与 approval 各自判定，plan 状态不参与拦截。mini 选择相反：`plan/mode` 为 true 时，`write` / `edit` / `bash` / `subagent` 在派发前被拒，结果词 `DENIED_BY_PLAN`，副作用不发生；只有 `APPROVED` 才翻转状态。

Considered options：照 DSH 只做软引导——否，mini 没有把 sandbox 与 plan 绑在一起的策略层，模型可以在「计划中」直接写文件；每次写都问人——否，审批不知道计划意图，噪音大且仍可能被批准；计划期禁全部工具——否，只读探索是计划的前提。

Consequences：安全性强于 DSH，但这是一处**有意的偏离**，已写进 `docs/reference/plan-and-todo.md` 的边界；计划状态必须从日志折叠恢复，不能只存内存；若将来要对齐 DSH，需要删除派发拦截并补一条策略段，而不是悄悄放宽。
