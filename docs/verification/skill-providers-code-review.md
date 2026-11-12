# skill-providers 代码审查（两轴）

**日期**：2026-11-12。范围 `2528d53...HEAD`（8 个提交）。两轴：Standards（风格、重复、命名、错误处理、判据质量）与 Spec（规格 ↔ 实现）。

## Standards

| # | 发现 | 处置 |
|---|---|---|
| C1 | `discover_skill_layer` 与 `merge_skill_layer` 是同一段「按目录顺序扫入、层内先到先得、complete 取与」的第三份拷贝（前两份在 `discover_skills` 与 `merge_skill_layer`） | **已修**：`discover_skill_layer` 转发 `merge_skill_layer((), directories)`，删掉重复的 12 行；65 条相关判据复跑全绿 |
| C2 | `skill` 工具在注册表分支里先 `registry.snapshot()` 找技能、再 `registry.get()` 取正文，同一次调用扫两遍根 | 记账不修：加缓存要引入失效语义（会话中途新增技能就看不见），代价大于收益；扫描有界（四个根 + 一层） |
| C3 | `session/host.py::visible_skills` 是 `skills_view` 的薄封装，两个名字并存 | 接受：两处 host 调用点要的是「从 handle 取视图」，封装让调用点不必知道 `env.skills_registry` 与 `settings.skills` 的配对 |
| C4 | `SkillRegistry.scoped` 先构造对象再写 `_scopes` 私有字段 | 接受：同类内部，链上只有一份全局层；改 `dataclasses.replace` 不会更清楚 |
| C5 | 提案写 `skills_provider.py`，实现落在 `skill_providers.py` | 接受：仅命名差异，对齐复已注明；不改代码也不改提案（提案是历史记录） |
| C6 | 旧字段残留 | 已核：`src` / `tests` / `docs/reference` 里 `skills_refresh`、`skill_dirs` 均无残留；历史 ADR 与旧验收文档保留原文不动 |

## Spec

| # | 对照点 | 结论 |
|---|---|---|
| S1 | 两条 Requirement、十个 Scenario | 对齐复 `skill-providers-dsh-review.md` 逐条核过，每条都有判据，无偏离 |
| S2 | D7「`merge_skill_layer` 不再被 spawn 调用」 | 字面不符：`tools/subagent.py` 的 `elif directories:`（裸 env 无注册表）仍调它。人裁决：**保留回落**，记 `simplified` |
| S3 | `settings.skills` 只做 payload 快照 | 符合 D4：装配期取一次注册表快照写 `session/start`，目录与命令面读活视图 |
| S4 | 摘要缺 `source` / `provider` | 人裁决「现在就加」，已实现：`Skill.source` 记层名，`session/start.payload.skills[].source` 与目录消息都写它，指纹含 `source`；判据 `test_a_skill_records_which_root_it_came_from`、`test_the_catalog_message_names_the_layer_a_skill_came_from`、`test_digest_includes_the_layer_name` |
| S5 | 判据质量 | 变异 9 条全杀（两条首轮存活已补判据）；真实端点两场、UAT 四场均通过 |

## 结论

两轴无阻塞项：一处重复实现已修（C1），五处记账（C2–C6）；两处待人裁决的都已裁：D7 保留回落、`source` 已加。
