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

## Capabilities

### Modified Capabilities

- `skills`：preset 层从「目录糖」改为「挂载 provider」；命令面改读注册表快照。
- `config-layering`：`[subagent.presets.<id>.skills]` 的形状与校验，删除 `skill_dirs`。

## Impact

- 代码：新增 `skills_provider.py`（协议 + filesystem 实现 + 注册表）；`skills.py` 的 `discover_skills`/`merge_skill_layer` 被 provider/registry 包装；`session/assembly.py`、`tools/subagent.py`、`tools/skill.py`、`commands.py`、`cli/main.py`、`session/host.py`、`config/assembly.py`。
- 测试：seam ②（provider/registry/配置）、①（目录刷新）、⑥（命令面活视图）、⑦（子会话层）。
- **ADR**：ADR-0035 加一句「窄 provider 接口不在此列」；新 ADR-0040 写边界（无生命周期、无热更新、只有 filesystem）。
- 非目标：远程 provider、provider 热插拔、插件容器。
