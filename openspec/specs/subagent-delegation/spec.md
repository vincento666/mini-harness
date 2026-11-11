# subagent-delegation Specification

## Purpose
TBD - created by archiving change m12-subagent-delegation. Update Purpose after archive.
## Requirements
### Requirement: subagent 是 spawn 工具

系统 SHALL 提供 `subagent` 工具，参数至少 `task`（非空、自足提示词）、可选 `max_turns` / `sandbox` / `agent_preset`。`agent_preset` 只在部署配置了 `allowed_presets` 时出现，取值 SHALL 是该白名单的枚举；它是**整套 preset 的选择**，模型 MUST NOT 在选中的 preset 内部再选择或排除单个工具。工具 MUST NOT 接受任意工具名列表（`tools` 参数已删除，见「子级工具集来自部署 preset」）。它 SHALL 创建一个独立子会话；MUST NOT 把父会话历史作为 seed（fork 不做）。结果 SHALL 是子会话最终文本（可含产物路径），MUST NOT 是子日志或完整过程。

#### Scenario: 子会话独立起步

- **WHEN** 父段调用 `subagent(task="读 a.md 并总结")`
- **THEN** 子会话从空对话开始，有自己的 `session/start` 与日志

#### Scenario: 没有白名单时模型不能选 preset

- **WHEN** 部署只配了 `[subagent] preset`、没配 `allowed_presets`
- **THEN** 工具 schema 里没有 `agent_preset`，该次调用用的是配置的默认 preset

### Requirement: 父子日志只通过 tool 结果相连

父日志 SHALL 只有该调用的 `tool/call` 与 `tool/result`；MUST NOT 写入子会话的 `model/*`、`tool/*` 或 delta。子 `session/start` SHALL 带 `entry=subagent`、`parent_session_id`、`depth`；父结果 SHALL 能通过 `tool_call_id` 与子会话对上。

#### Scenario: 父日志没有子过程

- **WHEN** 子会话内部调用了两次工具并产生两条 `model/response`
- **THEN** 父日志仍只有一条 `subagent` 的 `tool/call` 和一条 `tool/result`

### Requirement: 深度与容量是结果词

`maxDepth` 默认 1（0 禁止委派）；`maxActiveSubagents` 默认每父会话 8。超限 SHALL 返回 `DEPTH_EXCEEDED` / `ACTIVATION_LIMIT_REACHED`，作为 `tool/result` 的结果，MUST NOT 抛异常打断父回合。

#### Scenario: 深度超限

- **WHEN** 子会话在 `maxDepth=1` 下再调 `subagent`
- **THEN** 结果是 `DEPTH_EXCEEDED`，父回合继续

### Requirement: 子会话不继承 approval 放行

子会话 SHALL 继承档位/边界；approval 问人时 MUST 返回 `UNAVAILABLE`，MUST NOT 由父代答或自动放行。结果词为 `DENIED_BY_APPROVAL` 或现有审批结果。

子会话的运行时上下文 SHALL 带一条委派声明：权限范围在启动时固定、需要审批的操作会被自动拒绝、不要重试被拒绝的操作、把限制写进回复交给发起委派的代理。声明进受保护头部（`session/start.payload.delegated`），因此 `replay` 重算的是同一份头部。

#### Scenario: 子会话问人不可用

- **WHEN** 子会话的工具需要 approval
- **THEN** 门返回 `UNAVAILABLE`，不阻塞等待父；父拿到的那条 `tool/result` 也是 `DENIED_BY_APPROVAL`（带围栏码与子会话最后的文本）

#### Scenario: 子会话被告知权限固定

- **WHEN** 子会话装配上下文
- **THEN** 受保护头部里有委派声明；根会话的头部里没有

### Requirement: subagent 同批真并发

`subagent` SHALL 标为 `parallel` 类别；同一批多个调用 SHALL 并发执行，结果按完成顺序落盘。子会话内部仍受自己的工具并发与 `max_turns` 约束。

#### Scenario: 两个子代理并发

- **WHEN** 同一批声明两个 `subagent`
- **THEN** 两者并行，wall-clock 小于串行基线；父日志两条结果

### Requirement: 取消传播到子会话

父段取消 SHALL 传播到该段派生且仍在跑的子会话；子会话 SHALL 按 ABORTED 收尾，已完成结果保留。父 MUST NOT 留下孤儿任务。

#### Scenario: 父取消子收尾

- **WHEN** 父段在子代理运行中取消
- **THEN** 子日志有 ABORTED 收尾，父取消照常返回

### Requirement: Host 视图带父子字段

Host 的 `GET /sessions` / `GET /sessions/{id}` 视图 SHALL 带 `parent_session_id`（根为空/null）与 `depth`；MUST NOT 转发子事件到父 SSE 流。

#### Scenario: 父视图多两个字段

- **WHEN** 查询一个由 subagent 创建的子会话
- **THEN** view 有 parent_session_id 与 depth，父 SSE 流不含子事件

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

