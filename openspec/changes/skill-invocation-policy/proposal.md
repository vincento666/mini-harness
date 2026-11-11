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

## 与 mini 现状的差异（本 change 要消除的）

| 面 | mini 现状 | DSH | 本 change |
|---|---|---|---|
| 策略位 | 无，所有技能两面都暴露 | 两个独立布尔 | 加 `model_invocable` / `user_invocable` |
| 模型清单 | 全部技能 | 只 `modelInvocable` | 过滤 |
| `skill` 工具 | 全部技能 | 只 `modelInvocable`，否则报不可用 | 校验 |
| 命令面 | 全部技能 | 只 `userInvocable` | 过滤 |
| 布尔语法 | 无 | 宽松布尔 + 非法丢弃 | 实现 |
| `description` | 可选 | 必填 | 改为必填（无 frontmatter 即跳过） |

**保留简化**：DSH 的 `/name` 消息手势仍未做（`skill-inline-mention`，M14c 之后）；本 change 的 user 面是行首 `/<技能名>` 与 `/skill`。

## Capabilities

### Modified Capabilities

- `skills`：新增「技能调用策略」；发现、清单注入、`skill` 工具、命令面按策略过滤。

## Impact

- 代码：`skills.py`（解析与 `Skill` 形状）、`loop/turn_loop.py`（payload 只写模型可调）、`events/fold.py`（头部来自 payload，无需再过滤）、`commands.py`（命令面按 `user_invocable` 过滤）、`config/assembly.py`（`skill` 工具的可见技能表）、`cli/host.py`（命令清单同源）。
- 测试：seam ②（解析与工具）、seam ④（payload）、seam ⑥（命令面）。
- 非目标：`whenToUse`、`metadata`、watcher、`/name` 手势。
