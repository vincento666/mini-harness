---
status: proposed
---

# 单目标 + 任务并行；多目标调度后置

M13 只支持一个当前目标（`create` 仅在没有目标或上一个已 `complete` 时成立），并行发生在目标内部的任务上：一次 `todo` 调用可标多个 `in_progress`，各任务状态在同一张表里各自成立。多目标并存与轮次调度整体后置到 `parallel-goal-scheduler`（不占 M 编号），`2026-11-17` 人裁。

Considered options：多目标并存、轮次交替（原 roadmap 写法）——否，DSH 的 `create` 契约、`GoalRef` 与投影都是「当前一个目标」，改成集合要同时动事件、CAS、投影与驱动四处，而这一轮要的是「任务不丢、能自己往下走」；只做单目标单任务——否，段边界会清空 todo，多步任务的进度留不住，等于没解决；把并行开关做成必填（照 DSH 的 `allowParallelInProgress` 无默认）——否，会让既有 `mini.config.toml` 全部失效。

Consequences：M13 的判据里「两目标互不覆盖」改为「多任务互不覆盖」，钉的是投影值与 `/todo` 输出；`parallel-goal-scheduler` 的范围因此从「调度」扩为「多目标状态 + 调度」；`allow_parallel_in_progress` 的缺省 `true` 少了一个显式部署声明，靠文档与示例补。
