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
| 6 | 失败与降级 | 非法策略丢弃技能；未知与禁用分开报 | 同；不引入「不完整发现」状态 | **simplified**（无 incomplete 快照；触发：远程/慢 provider） |
| 7 | 组合与扩展 | host + scope 分层、遮蔽 | 单层、内置 | **simplified**（ADR-0038；触发：preset 级技能集） |
| 8 | 资源与约束 | 描述 500；正文无上限（工具层另算） | 描述 500；正文 32 KiB | aligned（正文上限是 mini 的既有约束） |
| 9 | 信任与授权 | 策略只管可见性，授权仍由审批/沙箱判 | 同；不改围栏 | aligned |
| 10 | 回放与确定性 | 目录消息进历史，正文按需 | 清单进 payload，正文进 `tool/result`；命令展开从 settings 取 | aligned |

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

## 待人裁决

1. `/skill <名字>` 是否也要求 `user-invocable`（建议：是，它是人机入口，照 DSH 的 `/name` 面）；
2. `description` 改必填（建议：对齐；代价是无 frontmatter 的扁平文件不再是技能）；
3. 第 6/7 项的简化是否接受（建议：接受，触发条件已写）。

## Capabilities

### Modified Capabilities

- `skills`：新增「技能调用策略」；发现、清单注入、`skill` 工具、命令面按策略过滤。

## Impact

- 代码：`skills.py`（解析与 `Skill` 形状）、`loop/turn_loop.py`（payload 只写模型可调）、`events/fold.py`（头部来自 payload，无需再过滤）、`commands.py`（命令面按 `user_invocable` 过滤）、`config/assembly.py`（`skill` 工具的可见技能表）、`cli/host.py`（命令清单同源）。
- 测试：seam ②（解析与工具）、seam ④（payload）、seam ⑥（命令面）。
- 非目标：`whenToUse`、`metadata`、watcher、`/name` 手势。
