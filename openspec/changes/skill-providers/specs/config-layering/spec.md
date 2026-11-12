# Spec Delta

## MODIFIED Requirements

### Requirement: 子代理 preset 配置

配置文件 SHALL 接受 `[subagent]` 段：`preset`（默认 preset id，字符串）、`allowed_presets`（非空字符串数组，模型可选的白名单）、`[subagent.presets.<id>].tools`（工具名数组）、可选的 `[subagent.presets.<id>].persona`（字符串）与可选的 `[subagent.presets.<id>.skills]`（表：`kind` 只接受 `filesystem`，`dirs` 是必填的字符串数组）。`<id>` SHALL 非空且不重复。

下列情形 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与出问题的键，且 MUST NOT 创建 session 日志：`[subagent]` 段里的未知键；`preset` 指向的 id 不在 `[subagent.presets]` 里；`preset` 不在 `allowed_presets` 里（两者都配时）；`allowed_presets` 里有不在 `[subagent.presets]` 里的 id；preset 的 `tools` 里有内置工具之外的名字；`persona` 不是字符串；`skills` 不是表、`kind` 不是 `filesystem`、`dirs` 不是字符串数组；preset id 为空或重复。没有 `[subagent]` 段 SHALL 合法。`dirs` 里的目录不存在 SHALL NOT 是配置错误。

`skill_dirs` 已删除：出现在 preset 里 SHALL 按未知键处理（退出码 2）。

#### Scenario: skills 表是合法配置

- **WHEN** 配置 `[subagent.presets.reader.skills] kind = "filesystem"`、`dirs = ["sk"]`
- **THEN** 配置通过

#### Scenario: 未知 kind 是参数错误

- **WHEN** `kind = "remote"`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `kind`

#### Scenario: dirs 类型错误

- **WHEN** `dirs = "sk"`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `dirs`

#### Scenario: skill_dirs 已删除

- **WHEN** preset 里写 `skill_dirs = ["sk"]`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `skill_dirs`

#### Scenario: 目录不存在不是配置错误

- **WHEN** `dirs = ["/nope"]`
- **THEN** 配置通过；子会话启动时该层为空
