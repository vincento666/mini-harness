# Proposal

## Why

`skill-invocation-policy` 的 preset 层是配置里的 `skill_dirs` 目录糖；DSH 的层是**挂载的 provider**（filesystem / remote / embedded），注册表按 scope 分层合并。目录糖能做同名覆盖，但做不出「preset 挂一个不同的源」——远程技能、打包技能都接不进来。这是第 7 项残留。

## DSH 对齐（十项里与本次相关的项）

**形状**：`SkillProvider`（`list` 返回 candidates + 完整性，`get` 读正文）；注册表分 host 层与每个 scope 一层；summary 带 `source`/`provider`/`rank`。

**机制**：provider 在插件 `apply()` 里同步注册，落进调用上下文的 scope 层；读时合并全局层与当前 scope 链，**近一层的同名条目直接胜出**，rank 只在同一层内裁决；preset 的 standing composition 把 provider 挂进该 preset 的层。

**语义**：同一层内重复名按 rank、provider 注册顺序、local 顺序；不完整观察不进缓存；未知/加载失败按结果词返回。

## mini 的映射

- **provider 接口**：`SkillProvider { name, list() -> SkillDiscovery, get(skill) -> str }`；只有 `filesystem` 一种实现（包装现有四根 + preset 目录），**没有生命周期/热更新**——窄接口，不是插件容器。
- **注册表**：`SkillRegistry(global)` + `scoped(preset_provider)`；`snapshot()` 先取近层、再补全局层没被覆盖的名字，按名字排序。
- **配置**：`[subagent.presets.<id>.skills]` 表：`kind = "filesystem"`、`dirs = [...]`；替换 `skill_dirs`（无已发布用户，直接换）。
- **顺带关掉 A 的 D7**：命令面（`/skills`、host）改为读注册表快照——不再与模型目录短暂不一致。

## DSH 十项（propose 阶段的全量对照）

**补录说明（2026-11-12）**：本节在 propose 时只写了「形状 / 机制 / 语义」三项，缺其余七项；归档前按 `docs/reference/dsh-alignment-checklist.md` 补齐，结论与 `docs/verification/skill-providers-dsh-review.md` 的复核一致。

**不变量**：DSH 的 provider 只在注册与读取两处生效，目录仍是可观测事实。mini 的 A「日志唯一真源」不变——目录是日志里的 user 消息，正文不进日志；B「失败也是结果」——未知技能或不可调用返回 `TOOL_ARGS_INVALID`；E 的工作区边界与写前必读不受影响（本 change 不碰文件工具）。建议：aligned。

**面**：DSH 的模型面看 summary，人机面看 `/skills`，宿主面看命令清单。mini 的四个面（模型目录、`/skills`、`session/start`、host `/commands`）读同一份注册表快照，`session/start` 仍记装配快照供审计。本 change 做的正是把命令面从装配快照挪到活视图（关闭 A 的 D7）。建议：aligned。

**失败与降级**：DSH 对未知 provider、加载失败按结果词返回，缺目录是空层。mini 同：`dirs` 不存在 → 空层且 `complete=true`；层不完整与全局取与；未知名字 → `TOOL_ARGS_INVALID`；没有注册表 → 回落构造元组。建议：aligned。

**组合与扩展**：DSH 有插件 `apply()` 与多层 scope。mini 只有「全局 + 一层 preset」，没有生命周期、没有热更新（ADR-0040）。建议：simplified，触发条件：需要多级作用域或第二个 provider 类型。

**资源与约束**：DSH 对 summary 有预算。mini 的目录仍按 `CATALOG_BUDGET` 截断、正文按 `BODY_LIMIT` 截断；命令面每次快照 = 扫四个根 + 一层，代价写进 design 的 Risks。建议：aligned。

**信任与授权**：DSH 的 preset 由运营配置，provider 只读不执行。mini 同：`dirs` 可绝对路径，与 `skill_dirs` 时期一致；工具审批与沙箱两轴不变。建议：aligned。

**回放与确定性**：DSH 从日志折叠目录。mini 的目录消息与 `session/start.skills` 都在日志里，回放不重读磁盘上的注册表。建议：aligned。

## Capabilities

### Modified Capabilities

- `skills`：preset 层从「目录糖」改为「挂载 provider」；命令面改读注册表快照。
- `config-layering`：`[subagent.presets.<id>.skills]` 的形状与校验，删除 `skill_dirs`。

## Impact

- 代码：新增 `skills_provider.py`（协议 + filesystem 实现 + 注册表）；`skills.py` 的 `discover_skills`/`merge_skill_layer` 被 provider/registry 包装；`session/assembly.py`、`tools/subagent.py`、`tools/skill.py`、`commands.py`、`cli/main.py`、`session/host.py`、`config/assembly.py`。
- 测试：seam ②（provider/registry/配置）、①（目录刷新）、⑥（命令面活视图）、⑦（子会话层）。
- **ADR**：ADR-0035 加一句「窄 provider 接口不在此列」；新 ADR-0040 写边界（无生命周期、无热更新、只有 filesystem）。
- 非目标：远程 provider、provider 热插拔、插件容器。
