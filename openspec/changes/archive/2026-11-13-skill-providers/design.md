# Design

## Decisions

**D1 窄 provider 协议。** `SkillProvider` 只有两个方法：`list() -> SkillDiscovery` 与 `get(skill) -> str`（正文）。filesystem 实现包装现有 `discover_skills` 与 `read_skill_body`；没有 apply/dispose/热更新，所以它不是插件容器（ADR-0040）。

**D2 注册表与层。** `SkillRegistry` 持有一个全局 provider；`scoped(provider)` 返回带一层 scope 的视图。`snapshot()` 先把近层条目放进表，再补全局层里没被覆盖的名字，按名字排序；同一层内按 provider 的 `rank`（filesystem 已按四根 rank 去重）。根会话只有全局层。

**D3 配置形状。** `[subagent.presets.<id>.skills]`：`kind`（只接受 `filesystem`）、`dirs`（字符串数组，必填）。未知键、未知 kind、`dirs` 不是字符串数组 → 退出码 2。目录不存在是空层、不是配置错误。删除 `skill_dirs`。

**D4 装配与刷新。** `assemble` 建全局 filesystem provider 与注册表，放进 `Prepared`；`SessionEnv` 带 `skills_registry`。目录消息与命令面都改读 `registry.snapshot()`（A 的 D7 关闭）；`settings.skills` 保留为 `session/start.payload` 的装配快照（审计）。

**D5 子会话作用域。** spawn 时用 preset 的 `skills` 表建一个 filesystem provider（dirs 相对 workspace 解析），`registry.scoped(provider)` 给子会话；完整性取与。子会话的 catalog/命令面都读这个视图。

**D6 `skill` 工具走注册表。** 执行时优先用 `env.skills_registry.snapshot()` 找技能与读正文；没有注册表（旧测试/裸 env）时回落到构造时传入的 skills 元组。

**D7 删除目录糖。** `merge_skill_layer` 不再被 spawn 调用；`discover_skills` 成为 filesystem provider 的内部实现。测试里的旧用法跟着改成 provider/registry。

## Risks

- **一次性换掉 `skill_dirs`** 会动配置与一批测试；没有已发布用户，直接换，不保留兼容。
- **层合并顺序**容易写成「rank 全局裁决」；判据要覆盖「近层低 rank 仍胜」。
- **命令面改活视图**会让 `/skills` 与模型目录同源；好处是一致，代价是每次命令都扫一遍根。

## 任务映射（任务 → 问题 → DSH 决策 → mini 缺陷）

| 任务 | 问题 | DSH 决策 | mini 缺陷 |
|---|---|---|---|
| 1 协议 + filesystem | 源可插拔 | provider 接口 | 只有目录糖，源不可换 |
| 2 注册表 + 层 | 近层胜出 | host+scope 分层、近层直接胜 | 扁平合并，只能靠 rank |
| 3 装配/刷新 | 目录读注册表 | 每个 step 从注册表取 | 目录读 `settings.skills` 快照 |
| 4 命令面活视图 | `/skills` 与模型一致 | 浏览器目录读注册表 | A 的 D7：命令面仍快照 |
| 5 配置 | preset 挂 provider | preset 的 standing composition | `skill_dirs` 只能挂目录 |
| 6 子会话作用域 | 子会话带预设层 | scope 链 | spawn 时一次性合并 |
| 7 `skill` 工具 | 正文从注册表取 | 工具经 `ctx.skills.get` | 工具拿死元组 |
| 8 测试/收尾 | 验收 | — | — |
