# Spec Delta: cli

## ADDED Requirements

### Requirement: 步数上限用 --max-steps

`run` / `chat` SHALL 用 `--max-steps` 限制**一轮**的步数，默认 8。旧 flag `--max-turns` MUST NOT 被接受：argparse 视它为未知参数，命令以 `INVALID_ARGUMENT` 退出（退出码 2），不建日志。

#### Scenario: 旧 flag 不再被接受

- **WHEN** 用 `--max-turns 2` 跑一次 run
- **THEN** 退出码 2，stderr 里是 `unrecognized arguments`，不建日志
