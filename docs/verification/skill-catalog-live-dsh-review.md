# skill-catalog-live 对齐复核

**日期**：2026-11-12。对齐对象：提案 / 设计 / 规格 / 验收 + DSH 十项。

## 提案与验收

| 类别 | 对照点 | 实现 | 结论 |
|---|---|---|---|
| 提案 | 目录改为持久 user 消息 | `turn_loop._maybe_emit_catalog` 写 `user/message source=skill-catalog` | aligned |
| 提案 | 每 turn 指纹替换 | `catalog_digest`（模型可调 name+desc+complete）；每 turn 比对 | aligned |
| 提案 | 不完整重试/恢复 | 每次刷新观察；警告 + `incomplete`；恢复后替换无警告 | aligned |
| 提案 | 空目录退休 | `render_catalog_message([], True)` 明确不要用旧名字 | aligned |
| 提案 | 压缩后重建 | `_catalog_shadowed` 查 `shadowed_range` | aligned |
| 提案 | 子会话含 preset 层 | `child_refresh` 重放 `merge_skill_layer` | aligned |
| 验收 | tasks 1.1–3.2 | 判据 9 条；全量 643 passed | aligned |

## 设计决策

D1–D6、D8 aligned；D7（命令面仍用装配快照）simplified，触发条件：命令面也要实时视图。

## DSH 十项

| # | 项 | 结论 | 记账 |
|---|---|---|---|
| 1 | 形状 | aligned | `<available_skills>`、`source`、`incomplete`、描述 500 |
| 2 | 机制 | aligned | 每 turn 观察 + 指纹；无 watcher，用每 turn 扫描代替 |
| 3 | 语义 | aligned | 不完整发确认+警告、重试；清空退休；空且从未发过不注入 |
| 4 | 不变量 | aligned | 目录在日志、回放从日志折叠 |
| 5 | 面 | aligned | 模型看目录消息；头部不含技能；命令面仍快照（simplified） |
| 6 | 失败与降级 | aligned | 不完整可观察、可恢复；按操作性读法（不保留严格 last-good） |
| 7 | 组合与扩展 | simplified | 子会话重放 preset 目录层；provider 层仍待 `skill-providers` |
| 8 | 资源与约束 | aligned | 描述截断；目录整套替换（DSH 同） |
| 9 | 信任与授权 | aligned | 策略过滤不变 |
| 10 | 回放与确定性 | aligned | 目录消息与 `incomplete` 都在日志 |

## 结论

提案/设计/规格/验收逐条兑现；十项 9 aligned、1 simplified（provider 层，已排 `skill-providers`）。`/skills` 快照与 watcher 为已记账简化。
