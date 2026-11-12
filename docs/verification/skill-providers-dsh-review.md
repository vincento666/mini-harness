# skill-providers 对齐复核

**日期**：2026-11-12。对齐对象：提案（Why / What / Impact / 非目标）、设计 D1–D7、规格两条 Requirement 与十个 Scenario、tasks 验收，以及 DSH 十项。基线 `main@2528d53`，范围 `2528d53...HEAD`。

## 提案

| 类别 | 对照点 | 实现 | 结论 |
|---|---|---|---|
| Why | preset 层从目录糖换成挂载 provider，源可替换 | `SkillProvider` + `SkillRegistry.scoped`；`[subagent.presets.<id>.skills]` 取代 `skill_dirs` | aligned |
| 形状 | `SkillProvider { name, list, get }`；注册表分层 | `skill_providers.py` 同名协议与 `SkillRegistry`（提案写 `skills_provider.py`，仅文件名差异） | aligned |
| 机制 | 近层同名直接胜出，rank 只在层内裁决 | `snapshot()` 按 `(*scopes, global)` 顺序 `setdefault`；层内 rank 由 `discover_skills` / `discover_skill_layer` 自己裁决 | aligned |
| 语义 | 未知/失败按结果词返回 | 未知技能 → `TOOL_ARGS_INVALID`；配置非法 → `CONFIG_*` + 退出码 2 | aligned |
| 形状 | summary 带 `source` / `provider` / `rank` | `session/start.payload.skills` 只有 `name/description/rank/path/两个策略位`；层名只在 `FilesystemProvider.name`，不进摘要 | simplified |
| Impact | 代码清单 | `skill_providers.py` 新增；`skills.py`、`session/assembly.py`、`tools/subagent.py`、`tools/skill.py`、`cli/main.py`、`session/host.py`、`config/assembly.py` 改动；`commands.py` 未改（命令面改在调用侧） | aligned |
| Impact | ADR-0035 加句 + ADR-0040 | 两份都在 `HEAD`；ADR-0039 标 `superseded by ADR-0040` | aligned |
| 非目标 | 远程 provider、热插拔、插件容器 | 未做；`SKILL_KINDS = {"filesystem"}` | aligned |
| 验收 | tasks 1.1–1.3 | 提交 `5c0e6f1`；判据 9 条（含近层低 rank 胜出断言） | aligned |
| 验收 | tasks 2.1–2.3 | 提交 `4e67836`；目录消息读快照，`settings.skills` 只做 payload | aligned |
| 验收 | tasks 3.1–3.2 | 提交 `113d161`；CLI 与 host 命令面读同一快照 | aligned |
| 验收 | tasks 4.1–4.4 | 提交 `8ccae5b`；配置校验、`skill_dirs` 删除、子会话挂层、父会话不受影响 | aligned |
| 验收 | task 5.3 变异一轮 | `docs/verification/skill-providers-mutation.md`：9 个变异全被杀（两个首轮存活，补判据后杀死） | aligned |
| 验收 | task 5.6 ADR | 同上（ADR-0035 修订 + ADR-0040） | aligned |
| 验收 | task 5.1 真实端点 | `docs/verification/skill-providers-real-endpoint.md`：子会话 preset 层覆盖同名、层独有技能、`skill` 正文来自该层；`/skills` 与目录消息两次观察一致 | aligned |
| 验收 | task 5.2 UAT | 场次手册已立骨架，人未跑 | deferred |

## 规格

### Requirement：子代理 preset 配置

| 对照点 | 实现 | 结论 |
|---|---|---|
| `skills` 表：`kind` 只接受 `filesystem`、`dirs` 必填字符串数组 | `config/assembly.py` 的 `_presets`：未知键 → `CONFIG_UNKNOWN_KEY`；kind/dirs → `CONFIG_INVALID_VALUE` | aligned |
| 非法配置 → 退出码 2 + `INVALID_ARGUMENT` + 不建日志 | 配置失败在装配前返回；`test_assemble_failure_happens_before_any_log` 守「无日志」 | aligned |
| 没有 `[subagent]` 段合法 | `test_an_empty_subagent_section_is_legal` | aligned |
| `dirs` 目录不存在不是配置错误 | `test_a_preset_skills_table_is_accepted` 一类只校验形状，不 stat | aligned |
| `skill_dirs` 已删除、按未知键处理 | `test_skill_dirs_is_a_removed_key` | aligned |
| Scenario：skills 表合法 | `test_a_preset_skills_table_is_accepted` | aligned |
| Scenario：未知 kind | `test_a_skills_table_needs_a_known_kind_and_string_dirs`（`kind = "remote"`） | aligned |
| Scenario：dirs 类型错误 | 同上（`dirs = "sk"`） | aligned |
| Scenario：`skill_dirs` 已删除 | `test_skill_dirs_is_a_removed_key` | aligned |
| Scenario：目录不存在不是配置错误 | 同上 + `test_a_missing_preset_skill_directory_starts_the_child_anyway` | aligned |

### Requirement：preset 作用域技能层

| 对照点 | 实现 | 结论 |
|---|---|---|
| 子会话 = 全局层 + preset 层，近层同名胜、不看 rank | `SkillRegistry.scoped` + `snapshot` 的 `setdefault` | aligned |
| 同层内按 rank 与注册顺序 | 全局层是 `discover_skills` 的四根 rank；层是目录顺序 `RANK_PRESET_LAYER + index` | aligned |
| 根会话没有 preset 层 | `assemble` 只建全局层；spawn 才 `scoped` | aligned |
| 命令面与模型目录读同一份注册表快照 | `skills_view` 是唯一入口：CLI `/help`、`/<技能名>`、其他命令、host `/commands` 与 `/<name>` | aligned |
| Scenario：preset 层覆盖同名 | `test_a_preset_skill_layer_reaches_the_child_only`（父 `全局`、子 `preset`） | aligned |
| Scenario：层独有的技能 | 同上（`extra` 只在子会话目录与 `session/start`） | aligned |
| Scenario：近层低 rank 仍胜 | `test_the_near_layer_wins_by_name_across_ranks`（全局 100、层 600，胜出 600） | aligned |
| Scenario：不存在的目录是空层 | `test_a_missing_layer_directory_is_an_empty_complete_layer` + `test_a_missing_preset_skill_directory_starts_the_child_anyway`（子会话照常起、无 `skills_incomplete`） | aligned |
| Scenario：命令面与模型目录同源 | `test_the_chat_command_face_reads_the_live_registry`、`test_the_host_command_face_sees_a_skill_added_mid_session` | aligned |

## 设计决策

| 决策 | 实现 | 结论 |
|---|---|---|
| D1 窄 provider（list/get、无生命周期） | `SkillProvider` 两方法；`FilesystemProvider` 包 `discover_skills` / `read_skill_body` | aligned |
| D2 注册表与层 | `snapshot()` 近层先占、全局补空、按名字排序；`_providers()` 顺序即优先级 | aligned |
| D3 配置形状 | 同规格表；`SKILL_KINDS` 单一取值 | aligned |
| D4 装配与刷新 | `assemble` 建 `SkillRegistry(FilesystemProvider.global_roots(...))`，放进 `Prepared` 与 `SessionEnv`；目录消息读它 | aligned |
| D5 子会话作用域 | spawn 时相对 `workspace` 解析 dirs、`scoped`、完整性取与；catalog 与命令面都读该视图 | aligned |
| D6 `skill` 工具走注册表 | `context.session.skills_registry` 找技能、`registry.get` 取正文；无注册表回落到构造元组 | aligned |
| D7 删除目录糖 | 配置面已无 `skill_dirs`；`discover_skills` 成为 provider 内部实现。**`merge_skill_layer` 仍被 spawn 调用**——只在「裸 env 没有注册表」的回落分支 | simplified |

D7 的偏差说明：`assemble` 总会建注册表，所以那条分支在生产路径不可达，只有直接构造 `SessionEnv` 的测试会走到；保留它是为了让裸 env 的判据不失明。代价是多一条无消费者的分支。**建议**：保留，或在下个 change 里把 `SessionEnv.skills_registry` 收成必填并删掉回落——由人裁决。

summary 字段的偏差说明（对应上表 simplified）：DSH 的摘要带来源，mini 只带 `rank` 与 `path`，层名不进 payload。代价是审计里看不出一个技能来自哪一层；触发条件：远程或打包 provider 进来、同名的两个来源需要区分时再加 `source`。**由人裁决**。

## DSH 十项

| # | 项 | 结论 | 记账 |
|---|---|---|---|
| 1 | 形状 | simplified | provider 两方法同构；摘要缺 `source`/`provider`（见上） |
| 2 | 机制 | aligned | DSH 在插件 `apply()` 同步注册、读时合并 scope 链；mini 在装配期建全局层、spawn 时挂层，读时合并。没有插件生命周期，触发点等价 |
| 3 | 语义 | aligned | 近层胜、rank 只在层内；未知 kind 退出码 2；目录不存在是空层；`skill_dirs` 按未知键 |
| 4 | 不变量 | aligned | A：目录仍是日志里的消息，正文不进日志；B：未知/不可调用是 `TOOL_ARGS_INVALID` 结果词；E：preset 的相对目录按 workspace 解析 |
| 5 | 面 | aligned | 模型目录、`/skills`、host 命令清单、`skill` 工具正文读同一份快照；`session/start` 仍记装配快照供审计 |
| 6 | 失败与降级 | aligned | 缺目录空层；层不完整与全局取与；未知名字结果词；无注册表回落元组 |
| 7 | 组合与扩展 | simplified | 只有「全局 + 一层 preset」，没有多级 scope、没有 `apply/dispose`；触发条件：需要多级作用域或第二个 provider 类型 |
| 8 | 资源与约束 | aligned | 正文仍按 `BODY_LIMIT` 截断；命令面每次快照 = 扫一遍根，代价已写进 design 的 Risks |
| 9 | 信任与授权 | aligned | 策略位（模型/人可调）不变；preset 的 dirs 由运营配置，绝对路径与 `skill_dirs` 时期一致 |
| 10 | 回放与确定性 | aligned | 目录消息与 `session/start.skills` 都在日志；回放不重读磁盘上的注册表 |

## 结论

提案、规格、设计逐条兑现，实现与判据对得上：两条 Requirement 的十个 Scenario 每条都有判据，变异 9 个全杀。

三处需要人裁决：

1. D7 的 `merge_skill_layer` 回落分支（`simplified`）：保留还是收掉 `SessionEnv.skills_registry` 的可选性；
2. 摘要缺 `source`/`provider`（`simplified`）：现在加还是等远程 provider；
3. `5.2` UAT（`deferred`）：需人坐终端跑，归档前必须补上。
