# Proposal

## Why

M12 的子代理工具集默认继承父表、并允许**父模型**用 `subagent.tools` 再收窄。这一层 DSH 没有：DSH 的工具集来自**部署侧**的 `agentPreset`（persona + `toolFilter`），模型只能在 `allowedAgentPresets` 白名单里选 preset，不能提交任意工具名。ADR-0037 已定案：M14 起完全对齐 DSH，删除 `subagent.tools`。

关键事实（决定了删除是安全的）：**DSH 在没有 preset 时不会失效**——子级「加入父方当前的 preset 代际」，派发照常。所以 mini 去掉模型侧裁剪后，仍然有「继承父组合」这个缺省，不会因为没配置而失去委派能力。

## What Changes

- `mini.config.toml` 新增 `[subagent]` 段：`preset`（默认 preset id）、`allowed_presets`（模型可选的白名单）、`[subagent.presets.<id>].tools`（该 preset 的工具名列表）。`persona` 字段留给 M14。
- `subagent` 工具删掉 `tools` 参数；`allowed_presets` 存在时 schema 暴露 `agent_preset` **枚举**（白名单外的 id 模型看不见）。
- 子级工具表 = **preset 工具 ∩ 父工具表**（只裁剪，不授权）；**没有 preset 时子级继承父的当前组合**；未知 preset → `TOOL_ARGS_INVALID`，不建子会话。
- 子 `session/start.payload` 记 `preset` id（`tools` 仍然记实际工具名）。
- 配置校验：`[subagent]` 的未知键、preset 里的未知工具名、`allowed_presets` 不含默认 `preset`、重复或空 id，都是 `INVALID_ARGUMENT`，且不产生 session 日志。

## Capabilities

### Modified Capabilities

- `subagent-delegation`：spawn 的参数面（去掉 `tools`、加白名单枚举）、子级工具集的来源。
- `config-layering`：配置文件新增 `[subagent]` 段与它的校验。

## Impact

- 代码：`config/load.py`、`config/layering.py`、`config/assembly.py`、`tools/subagent.py`、`loop/turn_loop.py`（子会话的 `session/start.payload`）。
- 测试：seam ②（配置校验、工具表）与 seam ⑦（preset 解析、白名单枚举、无 preset 继承）。
- 兼容：删除 `subagent.tools` 是破坏性变更；M12 刚合入、没有外部使用者。
- 非目标：`persona` 与技能（M14）、子级冷恢复（届时把 preset 写进 descriptor）、`agentPreset` 之外的第二套注册表。
