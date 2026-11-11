# Spec Delta

## MODIFIED Requirements

### Requirement: 子级工具集来自部署 preset

子代理的工具集与 persona SHALL 来自部署配置的 preset，而不是父模型的参数。解析顺序 SHALL 是：模型给的 `agent_preset`（仅白名单暴露时）→ 配置的 `subagent.preset` → 父会话当前的组合。三步都没有时，子会话 SHALL 继承父的工具表、派发照常（MUST NOT 因为没有 preset 而失败）。

选中的 preset 的工具集 SHALL 从内置工具目录取，MUST NOT 被父会话的局部工具表收窄（「不导入父方的 Agent 局部工具限制」）；preset 里出现内置目录之外的名字 SHALL 在配置校验期报错。工具是能力而非授权：子会话继承的档位/边界/审批照常生效。未知或已被移除的 preset id SHALL 使该次调用返回 `TOOL_ARGS_INVALID`，MUST NOT 创建子会话。子 `session/start.payload` SHALL 记 `preset`（选中的 id；继承父组合时不写），`tools` SHALL 记实际生效的工具名。

preset 可选带一段 `persona`（字符串）。选中的 preset 有 persona 时，子 `session/start.payload.preset_persona` SHALL 记这段文本，且受保护头部 SHALL 含它（排在委派声明之后、追加文本之前）；没有 persona 时 payload 与头部都不出现。

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

#### Scenario: persona 进子会话头部

- **WHEN** `[subagent.presets.writer] persona = "你是一位严格的评审者。"`
- **THEN** 子 `session/start.payload.preset_persona` 是这段文本，受保护头部里也有它
