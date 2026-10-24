# Spec Delta

## ADDED Requirements

### Requirement: 运行平台事实记录进 session/start
系统 SHALL 在 `session/start` 的 payload 里记录本次运行的平台事实 `platform`：`os`（运行所在操作系统的名字）与 `shell`（`bash` 工具实际用来执行命令的 shell 形态）。`run`、`chat`、`serve` 三个入口 SHALL 都记录。`platform` MUST NOT 是命令行开关或配置文件里的键，也 MUST NOT 记录密钥、环境变量值或用户名。

#### Scenario: run 记下 os 与 shell
- **WHEN** 执行 `minihns run -p "x" --workspace <dir>`
- **THEN** `session/start` 的 payload 里 `platform` 含非空的 `os` 与 `shell`，且 `shell` 与这份日志里 `bash` 实际执行命令用的形态一致

#### Scenario: chat 与 serve 同样记录
- **WHEN** 分别跑一次 `chat`（EOF 退出）与一次 `serve`
- **THEN** 两份日志的 `session/start` payload 里都有 `platform`，且两处的 `os` 与 `shell` 相同

#### Scenario: 平台事实不来自可配置性
- **WHEN** 不给任何命令行开关、也不给配置文件
- **THEN** `session/start` 的 payload 里 `platform` 仍非空，且 `os` 与 `shell` 都有值
