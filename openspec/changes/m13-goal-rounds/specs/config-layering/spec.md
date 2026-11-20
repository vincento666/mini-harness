# Spec Delta: config-layering

## ADDED Requirements

### Requirement: `[goal]` 段承载轮次、停滞与并行策略

`mini.config.toml` SHALL 支持 `[goal]` 段，含四个键：

- `max_rounds`：正整数，缺省 `32`；`create_goal` 未给 `max_rounds` 时用它；
- `blocked_after_consecutive_rounds`：正整数，缺省 `3`，且 MUST 不大于 `max_rounds`——否则阻塞门槛永远够不到，配置层直接拒；
- `allow_parallel_in_progress`：布尔，缺省 `true`；
- `stall_rounds`：非负整数，缺省 `0`。`0` 表示关闭停滞闸门（对齐 DSH：完成只由模型声明）；正整数表示「连续 N 个 goal 轮次零工具调用就停自动推进」。

非法取值（非正整数、非布尔、零、负数、非整数）MUST 在会话开始之前以参数错误失败，MUST NOT 产生日志。取值优先级与其它设置类字段一致：CLI flag > 配置文件 > 内置默认。

#### Scenario: 缺省值生效

- **WHEN** 配置文件没有 `[goal]` 段，模型调用 `create_goal` 且未给轮次上限
- **THEN** 快照的 `max_rounds == 32`

#### Scenario: 非法值当场失败

- **WHEN** 配置文件写 `max_rounds = 0`
- **THEN** 命令以参数错误退出，`sessions/` 下不新增日志

#### Scenario: 并行关闭生效

- **WHEN** 配置文件写 `allow_parallel_in_progress = false`，一次 `todo` 调用标两个 `in_progress`
- **THEN** 结果是 `TODO_PARALLEL_DISABLED`

#### Scenario: 停滞闸门默认关

- **WHEN** 配置文件没有 `stall_rounds`，一个 goal 轮次零工具调用后正常收尾
- **THEN** 驱动照常开下一轮；日志里 `segment/end.tool_calls == 0` 只作审计，不触发停止

#### Scenario: 开了闸门按连续轮数停

- **WHEN** 配置文件写 `stall_rounds = 2`，连续两个 goal 轮次零工具调用
- **THEN** 第二轮之后不再开新段、武装位解除，目标 `phase` 仍为 `active`
