# Spec Delta: cli

## ADDED Requirements

### Requirement: 步数上限用 --max-steps，旧 flag 保留一个兼容窗口

`run` / `chat` SHALL 用 `--max-steps` 限制**一轮**的步数，默认 8。旧 flag `--max-turns` SHALL 仍被接受并映射到同一字段，但 MUST NOT 出现在 `--help` 的主列表里；使用旧 flag 时 SHALL 在 stderr 打一次弃用提示。两个 flag 同时给出且值不同时 SHALL 以 `INVALID_ARGUMENT` 退出（退出码 2），MUST NOT 猜。

#### Scenario: 两个 flag 等价

- **WHEN** 同一 fixture 分别用 `--max-steps 2` 与 `--max-turns 2` 跑一次 run
- **THEN** 两次的 `session/end` 与每轮步数相同；旧 flag 那次 stderr 多一行弃用提示

#### Scenario: 冲突即拒绝

- **WHEN** 同时给 `--max-steps 2` 与 `--max-turns 3`
- **THEN** 退出码 2，不建日志
