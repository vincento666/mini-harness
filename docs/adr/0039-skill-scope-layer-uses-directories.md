---
status: proposed
---

# 技能的 preset 作用域层用目录根表达，发现完整性用装配期快照的 complete 位

DSH 的技能注册表是 host + 每个 scope（preset 挂载的 provider）分层，近层同名直接胜出；mini 没有插件容器（ADR-0035），所以 preset 层用 `[subagent.presets.<id>].skill_dirs` 的目录根表达，语义（近层胜出、层内按顺序、根无层）照 DSH，机制从「挂载 provider」简化为「扫目录」。DSH 的 `SkillCatalogSnapshot { skills, complete }` 在 mini 里对应装配期发现的 `complete` 布尔：根目录扫不动即不完整，payload 记 `skills_incomplete`、头部警告；因为 mini 的发现是快照，「下一步重试」落在下一次装配。

Considered options：不做 preset 层，只保留全局四根——否，子会话需要自己的技能集，这正是 preset 组合的一半；把 preset 层做成「按名字选全局技能」——否，那是过滤不是分层，做不出同名覆盖；把完整性问题留到接远程 provider 时——否，本地根也会因权限/磁盘抖动失败，静默丢技能比多一个标志更糟。

Consequences：preset 配置多一个 `skill_dirs` 键；子会话的 `settings.skills` 是合并视图，父会话不变；`skill_dirs` 的目录不存在是空层、不是错误；不完整发现没有「上次好目录」，会话内不会恢复，下一次装配才重试。触发条件：需要 preset 挂载真正的 provider（远程/打包技能）时，再把目录层换成 provider 层。
