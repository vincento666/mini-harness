# Spec Delta: config-layering

## ADDED Requirements

### Requirement: max_steps 是步数上限的唯一键

`mini.config.toml` 的会话段 SHALL 用 `max_steps` 表示一轮的步数上限。旧键 `max_turns` MUST NOT 被接受：它是一条未知键（`CONFIG_UNKNOWN_KEY`），会话开始之前失败，且不建日志。

#### Scenario: 旧键被拒

- **WHEN** 配置文件只写 `max_turns = 4`
- **THEN** 会话开始之前失败，退出码 2，不建日志
