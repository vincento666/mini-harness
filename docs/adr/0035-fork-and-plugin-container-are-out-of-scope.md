---
status: proposed
---

# fork 与插件容器暂不做；扩展面先走 skills 与外部触发

八阶段图把 `fork` 放进「会话与存储」、把「插件容器」放进「组合与委派」，mini 的 MVP 两阶段都不含它们：`fork` 要先决定「新日志里能不能带旧 `session_id` 的记录」（要么读方认旧 id、要么重写前缀，二者都动「只追加」的直觉），插件容器 / 热更新 / MCP / 完整 hooks allowlist 要的是第二套注册与生命周期，而 M14 只做 `SKILL.md` 发现 + `skill` 工具 + 一条可重放的外部触发。这两项写进本条，是为了让 `docs/stage-map.md` 的「⑧ 组合与委派」不被读成「忘了」，而不是为了现在做。

Considered options：现在就做 `fork`——否，UI 的分支/重来不是 v1 必需，日志语义的代价先付不值；做插件容器——否，没有消费者，M14 的 skills/触发是更小的扩展面；不记账、让它留在冻结的 handoff 里——否，handoff 不是权威，下一个读者会以为图上的 stage 8 只剩 M12–M14。

Consequences：stage 8 不会字面完成；如果壳需要「从这条消息重来」，要另开一个 change 并把「新日志的旧 id / 前缀重写」写成 ADR；M14 是扩展层的边界，MCP 与完整 hooks 明确在外；等壳落地、真有插件需求时再回来看这一条。
