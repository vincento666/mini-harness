---
status: proposed
---

# 技能 provider 是窄接口，不是插件容器

DSH 的技能注册表按 scope 分层，preset 通过挂载 provider 参与组合。mini 只做**窄接口**：`SkillProvider` 两个方法（`list` / `get`），唯一实现是 filesystem（包装四个根与预设目录），**没有 apply/dispose、没有热更新、没有生命周期**。这样能表达「preset 挂不同的源」，但不引入 ADR-0035 排除的插件容器。

Considered options：继续用 `skill_dirs` 目录糖——否，接不进远程/打包源，且与 DSH 的 provider 形状差一层；直接做插件容器——否，没有生命周期消费者，ADR-0035 的边界仍成立。

Consequences：provider 只能同步、只能本地；远程或热插拔要另开 change 并重新审视 ADR-0035；`skill_dirs` 被删除，配置面换成 `[subagent.presets.<id>.skills]`。
