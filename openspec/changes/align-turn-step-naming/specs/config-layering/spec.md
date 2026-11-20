# Spec Delta: config-layering

## ADDED Requirements

### Requirement: max_steps 是主键，max_turns 只读兼容

`mini.config.toml` 的会话段 SHALL 用 `max_steps` 表示一轮的步数上限。旧键 `max_turns` SHALL 仍被接受并映射到同一字段，装载时打一次弃用提示；两个键同时出现且值不同时 SHALL 是配置层失败（`INVALID_ARGUMENT`），MUST NOT 静默取其一。

#### Scenario: 旧键仍可用

- **WHEN** 配置文件只写 `max_turns = 4`
- **THEN** 会话按 4 步上限运行，stderr 有弃用提示

#### Scenario: 两键冲突

- **WHEN** 配置文件同时写 `max_steps = 4` 与 `max_turns = 6`
- **THEN** 会话开始之前失败，退出码 2，不建日志
