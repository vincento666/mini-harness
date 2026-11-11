# Spec Delta

## MODIFIED Requirements

### Requirement: 子代理 preset 配置

配置文件 SHALL 接受 `[subagent]` 段：`preset`（默认 preset id，字符串）、`allowed_presets`（非空字符串数组，模型可选的白名单）、`[subagent.presets.<id>].tools`（工具名数组）、可选的 `[subagent.presets.<id>].persona`（字符串）与可选的 `[subagent.presets.<id>].skill_dirs`（字符串数组）。`<id>` SHALL 非空且不重复。

下列情形 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与出问题的键，且 MUST NOT 创建 session 日志：`[subagent]` 段里的未知键；`preset` 指向的 id 不在 `[subagent.presets]` 里；`preset` 不在 `allowed_presets` 里（两者都配时）；`allowed_presets` 里有不在 `[subagent.presets]` 里的 id；preset 的 `tools` 里有内置工具之外的名字；`persona` 不是字符串；`skill_dirs` 不是字符串数组；preset id 为空或重复。没有 `[subagent]` 段 SHALL 合法，此时子代理继承父的工具表。`skill_dirs` 里的目录不存在 SHALL NOT 是配置错误（发现时视为空层）。

#### Scenario: 未知键是参数错误

- **WHEN** 配置文件写 `[subagent] unknown = 1`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `unknown`，且没有创建 session 日志

#### Scenario: skill_dirs 必须是字符串数组

- **WHEN** 配置 `[subagent.presets.reader] skill_dirs = "skills"`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `skill_dirs`

#### Scenario: 目录不存在不是配置错误

- **WHEN** `skill_dirs = ["/nope"]`
- **THEN** 配置通过；子会话启动时该层为空
