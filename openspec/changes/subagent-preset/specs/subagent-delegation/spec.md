# Spec Delta

## MODIFIED Requirements

### Requirement: subagent 是 spawn 工具

系统 SHALL 提供 `subagent` 工具，参数至少 `task`（非空、自足提示词）、可选 `max_turns` / `sandbox` / `agent_preset`。`agent_preset` 只在部署配置了 `allowed_presets` 时出现，取值 SHALL 是该白名单的枚举；它是**整套 preset 的选择**，模型 MUST NOT 在选中的 preset 内部再选择或排除单个工具。工具 MUST NOT 接受任意工具名列表（`tools` 参数已删除，见「子级工具集来自部署 preset」）。它 SHALL 创建一个独立子会话；MUST NOT 把父会话历史作为 seed（fork 不做）。结果 SHALL 是子会话最终文本（可含产物路径），MUST NOT 是子日志或完整过程。

#### Scenario: 子会话独立起步

- **WHEN** 父段调用 `subagent(task="读 a.md 并总结")`
- **THEN** 子会话从空对话开始，有自己的 `session/start` 与日志

#### Scenario: 没有白名单时模型不能选 preset

- **WHEN** 部署只配了 `[subagent] preset`、没配 `allowed_presets`
- **THEN** 工具 schema 里没有 `agent_preset`，该次调用用的是配置的默认 preset

## ADDED Requirements

### Requirement: 子级工具集来自部署 preset

子代理的工具集 SHALL 来自部署配置的 preset，而不是父模型的参数。解析顺序 SHALL 是：模型给的 `agent_preset`（仅白名单暴露时）→ 配置的 `subagent.preset` → 父会话当前的组合。三步都没有时，子会话 SHALL 继承父的工具表、派发照常（MUST NOT 因为没有 preset 而失败）。

选中的 preset 的工具集 SHALL 从内置工具目录取，MUST NOT 被父会话的局部工具表收窄（「不导入父方的 Agent 局部工具限制」）；preset 里出现内置目录之外的名字 SHALL 在配置校验期报错。工具是能力而非授权：子会话继承的档位/边界/审批照常生效。未知或已被移除的 preset id SHALL 使该次调用返回 `TOOL_ARGS_INVALID`，MUST NOT 创建子会话。子 `session/start.payload` SHALL 记 `preset`（选中的 id；继承父组合时不写），`tools` SHALL 记实际生效的工具名。

#### Scenario: 无配置时继承父组合

- **WHEN** 配置文件没有 `[subagent]` 段
- **THEN** 子会话的 `tools` 与父会话一致，派发照常

#### Scenario: 默认 preset 决定子会话的工具表

- **WHEN** 配置 `[subagent] preset = "reader"`，`reader.tools = ["read", "glob"]`
- **THEN** 子会话的工具表恰是 `read` 与 `glob`；子会话调用 `bash` 得到 `UNKNOWN_TOOL`

#### Scenario: preset 可以给出父会话没有的工具

- **WHEN** 父会话的 `tools` 白名单只有 `["read"]`，子 preset 的 `tools` 是 `["read", "bash"]`
- **THEN** 子会话的工具表含 `bash`（工具面独立于父的局部限制）；若子会话的沙箱是 `read-only`，bash 的调用在围栏处被拒

#### Scenario: 白名单决定模型能选什么

- **WHEN** 配置 `allowed_presets = ["reader", "writer"]`
- **THEN** 工具 schema 的 `agent_preset` 枚举恰是这两个 id；传第三个 id 不会进入执行

#### Scenario: 未知 preset 是结果

- **WHEN** 默认 preset 指向一个配置里不存在的 id
- **THEN** 结果是 `TOOL_ARGS_INVALID`，不创建子会话日志

#### Scenario: preset 记录进子日志

- **WHEN** 子会话用 `writer` preset 启动
- **THEN** 它的 `session/start.payload.preset` 是 `"writer"`，`tools` 是实际生效的工具名
