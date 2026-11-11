# Spec Delta

## MODIFIED Requirements

### Requirement: 子代理 preset 配置

配置文件 SHALL 接受 `[subagent]` 段：`preset`（默认 preset id，字符串）、`allowed_presets`（非空字符串数组，模型可选的白名单）、`[subagent.presets.<id>].tools`（工具名数组）与可选的 `[subagent.presets.<id>].persona`（字符串）。`<id>` SHALL 非空且不重复。

下列情形 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与出问题的键，且 MUST NOT 创建 session 日志：`[subagent]` 段里的未知键；`preset` 指向的 id 不在 `[subagent.presets]` 里；`preset` 不在 `allowed_presets` 里（两者都配时）；`allowed_presets` 里有不在 `[subagent.presets]` 里的 id；preset 的 `tools` 里有内置工具之外的名字；`persona` 不是字符串；preset id 为空或重复。没有 `[subagent]` 段 SHALL 合法，此时子代理继承父的工具表。

#### Scenario: 未知键是参数错误

- **WHEN** 配置文件写 `[subagent] unknown = 1`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `unknown`，且没有创建 session 日志

#### Scenario: 默认 preset 必须在白名单里

- **WHEN** 配置 `preset = "reader"`、`allowed_presets = ["writer"]`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`

#### Scenario: 默认 preset 必须真的存在

- **WHEN** 配置 `preset = "reader"`，但 `[subagent.presets]` 里没有 `reader`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: 白名单里的 id 必须真的存在

- **WHEN** 配置 `allowed_presets = ["reader", "reviewer"]`，但 `presets` 里没有 `reviewer`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `reviewer`

#### Scenario: preset 里的工具名必须内置

- **WHEN** 配置 `[subagent.presets.reader] tools = ["read", "web_search"]`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `web_search`，且没有创建 session 日志

#### Scenario: persona 是合法键

- **WHEN** 配置 `[subagent.presets.writer] persona = "你是一位严格的评审者。"`
- **THEN** 配置通过，preset 编译成功

#### Scenario: persona 类型不对是参数错误

- **WHEN** 配置 `[subagent.presets.writer] persona = 1`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `persona`

#### Scenario: 没有配置段是合法的

- **WHEN** 配置文件没有 `[subagent]` 段
- **THEN** run 正常进行，子代理继承父的工具表
