# Proposal

## Why

M14 把所有发现到的技能都当成「模型可调 + 用户可调」。DSH 有两道独立的策略位：`disable-model-invocation` 把技能挡在模型目录与 `skill` 工具之外，`user-invocable: false` 把技能挡在人机命令面之外。没有这两道位，用户既做不出「只给人用的技能」，也做不出「只给模型用的技能」。

按 2026-11-11 的流程：先对齐 DSH 的实现，再落规格。

## DSH 对齐（形状 / 机制 / 语义）

**形状**（`packages/skill/skill`、`dsh-skill-filesystem`、`dsh-tool-skill` 的公开文档）：

- `SkillInvocationPolicy { modelInvocable: boolean; userInvocable: boolean }`，每个 summary / candidate / definition 都带它；
- 本地文件的 frontmatter 键是 `disable-model-invocation` 与 `user-invocable`；省略即**允许**该面（两者默认 `true`）；
- 两个都 `false` 的技能只留给可信的 `ctx.skills.get()` 调用方，两个目录都不出现。

**机制**：

- 模型目录只收 `modelInvocable` 的技能；`skill` 工具在加载前校验，非 `modelInvocable` 返回「not available for model invocation」；
- 人机命令面只收 `userInvocable` 的技能；`/name` 手势只对 `user-invocable` 生效，未知/禁用的名字保持普通文本；
- `SkillListRequest` 返回 user-invocable 条目时同时给「模型是否可调」的可用性标记。

**语义**：

- 布尔取值：YAML 布尔 + 大小写不敏感的 `true/false`、`yes/no`、`on/off`、`1/0`；
- **非法拼写或非布尔值丢弃整个技能**（warn），不静默放行任何一面；
- `name` 与 `description` 都是必填；无 frontmatter 的文件不是技能（本 change 顺带对齐）。

## 十项对齐（`docs/reference/dsh-alignment-checklist.md`）

| # | 项 | DSH | mini 落成 | 结论 |
|---|---|---|---|---|
| 1 | 形状 | `SkillInvocationPolicy { modelInvocable, userInvocable }` | `Skill` 两个布尔；payload 项带两个字段 | aligned |
| 2 | 机制 | 发现期解析策略，各消费者在出口过滤 | 同：`settings.skills` 保留全部，出口各自过滤 | aligned |
| 3 | 语义 | 缺省都允许；宽松布尔；非法值丢弃整个技能；description 必填 | 同（两处是行为变化，见「待人裁决」） | aligned |
| 4 | 不变量 | 策略是事实，目录是投影；日志是唯一真源 | payload 只写模型可调；头部/回放从 payload 折叠 | aligned |
| 5 | 面 | 模型目录/工具 vs 人机命令 vs 日志各取所需 | 模型面 = payload/头部/工具；人机面 = 命令；日志 = payload + 命令事件 | aligned |
| 6 | 失败与降级 | `SkillCatalogSnapshot { skills, complete }`；根失败→不完整、不缓存、警告、下一步重试；单文件坏→跳过 | 发现结果带 `complete`；根扫描失败→不完整、payload 记 `skills_incomplete`、头部警告、下一会话重试；单文件坏→跳过 | **aligned-target**（本 change 做；快照式发现下「重试」= 下一次装配） |
| 7 | 组合与扩展 | host + per-scope 分层；近层同名直接胜出；rank 只在层内裁决 | preset 层 = `[subagent.presets.<id>].skill_dirs`；子会话 = 全局层 + preset 层，preset 层同名直接胜出；根无 preset 层 | **aligned-target**（本 change 做；机制从「挂载 provider」简化为「目录根」，语义同） |
| 8 | 资源与约束 | 描述 500；正文无上限（工具层另算） | 描述 500；正文 32 KiB | aligned（正文上限是 mini 的既有约束） |
| 9 | 信任与授权 | 策略只管可见性，授权仍由审批/沙箱判 | 同；不改围栏 | aligned |
| 10 | 回放与确定性 | 目录消息进历史，正文按需 | 清单进 payload，正文进 `tool/result`；命令展开从 settings 取 | aligned |

## 6/7 的 mini 映射（对齐语义，简化机制）

**第 6 项（发现完整性）**：`discover_skills` 返回 `(skills, complete)`。根目录 `iterdir` 读失败 → `complete=false`，其它根照常；单个文件读失败或 frontmatter 非法 → 跳过该文件（不算不完整）。`settings.skills_complete` 进 `session/start.payload`（`skills_incomplete: true`），受保护头部加一行警告；下一次装配重新发现（DSH 的「下一步重试」在 mini 的快照发现里就是下一会话）。

**第 7 项（preset 作用域层）**：配置增加 `[subagent.presets.<id>].skill_dirs`（字符串数组，相对 workspace 或绝对路径）。子会话的技能 = 全局四根 + preset 的目录层；**preset 层同名直接胜出**（不看 rank），层内按目录顺序、同目录内按名字；根会话没有 preset 层。DSH 的层由「preset 挂载 provider」产生，mini 用「目录根」表达，语义（近层胜出、层内裁决）一致。

## 与 mini 现状的差异（本 change 要消除的）

| 面 | mini 现状 | DSH | 本 change |
|---|---|---|---|
| 策略位 | 无，所有技能两面都暴露 | 两个独立布尔 | 加 `model_invocable` / `user_invocable` |
| 模型清单 | 全部技能 | 只 `modelInvocable` | 过滤 |
| `skill` 工具 | 全部技能 | 只 `modelInvocable`，否则报不可用 | 校验 |
| 命令面 | 全部技能 | 只 `userInvocable` | 过滤 |
| 布尔语法 | 无 | 宽松布尔 + 非法丢弃 | 实现 |
| `description` | 可选 | 必填 | 改为必填（无 frontmatter 即跳过） |

**建议（待人裁决）**：DSH 的 `/name` 消息手势保持简化（`skill-inline-mention`，M14c 之后）；本 change 的 user 面是行首 `/<技能名>` 与 `/skill`。

## 已裁决（2026-11-11）

1. `/skill <名字>` 要求 `user-invocable`——同意；
2. `description` 改必填——同意；
3. 第 6/7 项**也要对齐**（不是简化）——本 change 实现；`/name` 手势仍按 `skill-inline-mention` 排在 M14c 之后。

## Capabilities

### Modified Capabilities

- `skills`：新增「技能调用策略」；发现、清单注入、`skill` 工具、命令面按策略过滤。

## Impact

- 代码：`skills.py`（解析、策略、完整性、层合并）、`loop/settings.py`（`skills_complete`）、`loop/turn_loop.py`（payload 过滤与 `skills_incomplete`）、`events/fold.py`（头部警告）、`commands.py`（命令面过滤）、`config/assembly.py`（`skill` 工具可见表 + `skill_dirs` 校验）、`tools/subagent.py`（spawn 时合并 preset 层）、`cli/host.py`（命令清单同源）。
- 测试：seam ②（解析与工具）、seam ④（payload）、seam ⑥（命令面）。
- 非目标：`whenToUse`、`metadata`、watcher、`/name` 手势。
