# Design

## Context

M12 的 `subagent.tools` 是模型参数（只能收窄父表）；DSH 的工具集来自部署的 `agentPreset`，模型只能在 `allowedAgentPresets` 白名单里选。ADR-0037 定案对齐，本 change 是它的实现。

## Decisions

**D1 配置只有一处。** `mini.config.toml` 的 `[subagent]`：`preset`（默认 id）、`allowed_presets`（白名单）、`[subagent.presets.<id>].tools`（工具名列表）。没有 CLI flag；配置文件是唯一来源，和 `tools` 白名单同一条路。

**D2 解析顺序固定。** 模型给的 `agent_preset`（只有在白名单暴露时才能给）→ 配置的 `preset` → 父会话当前的组合。三步都空 = 继承父表，派发照常。这正是 DSH 的缺省语义。

**D3 preset 决定组合，不是授权。** 子工具表 = preset 的 `tools` 从**内置工具目录**取，MUST NOT 被父会话的局部工具表收窄——DSH 的 spawn README 写明「子级……不导入父方的 Agent 局部工具限制」，否则 Super-agent 那种「Router 没有 bash、Worker 有全工具」的形状做不出来。preset 里的未知工具名在配置校验期报错（与 `tools` 白名单同形），不在运行期静默丢弃。

工具只是能力：能不能用仍由子会话继承的档位/边界/审批判定。给 bash 但沙箱是 `read-only` 时，bash 照样在围栏处被拒。

**D4 枚举由配置生成。** 有 `allowed_presets` 时，`SubagentArgs` 用 `create_model` 动态生成，`agent_preset` 是 `Literal[白名单]`；没有白名单时不出现这个字段——模型连选都不能选（与 DSH 一致）。schema 里没有任意工具名列表。

**D5 「未知」以装配期的配置快照为唯一真理源。** 「已知」= 在装配时读入并校验过的 `[subagent.presets]` 里存在、id 非空且不重复的键。不读磁盘的当前文件（mini 没有热重载），不读父会话的运行时注册表。三种「未知」分开处理：

1. 模型给了白名单外的 id → 工具 schema 的枚举 + pydantic 入参校验挡住（`TOOL_ARGS_INVALID`），不进入 spawn；
2. 配置的默认 `preset` 指向 `presets` 里没有的 id，或 `allowed_presets` 里有不存在的 id → **装配期**配置错误（退出码 2、`INVALID_ARGUMENT`、不建日志）；
3. 运行期解析不到（今天跑不到；等 M11 的跨配置 resume 把「引用了已删掉的 preset」带进来才成为真路径）→ `TOOL_ARGS_INVALID` 结果、不建子会话、不抛异常。

回放不依赖配置：子 `session/start.payload.tools` 记的是实际生效的工具名，`replay` 读日志。

**D6 记录可审计。** 子 `session/start.payload.preset` 记选中的 id（没选中就不写）；`tools` 仍然记实际工具名——回放与审计都从日志读，不读进程内配置。

**D7 `persona` 留白。** 本 change 只做 `tools`；`[subagent.presets.<id>]` 的 `persona` 字段由 M14 补（那时 preset 与 DSH 的 `agentPreset` 同形）。

## Risks

- **动态模型**：`create_model` 让 schema 随配置变，判据要锁住「白名单外的 id 不可见、缺省用默认 preset」；没有白名单时字段不出现，也要有判据。
- **配置形状变化**：`mini.config.toml` 从扁平变成「扁平 + 一张嵌套表」，`validate_config` 要能区分「未知键」与「未知段内键」。
- **破坏性删除**：`subagent.tools` 消失会让 M12 的 spec 与测试同时改；M12 合入不久，没有外部使用者，代价可接受。
