# Spec Delta: config-layering

## MODIFIED Requirements

### Requirement: 配置文件的发现顺序

系统 SHALL 按固定顺序找配置文件：`--config <path>` 显式指定的路径优先；未给 `--config` 时 SHALL 找**发现根**里的 `mini.config.toml`——发现根是显式 `--workspace` 解析后的目录，未给 `--workspace` 时是当前目录（启动目录）；两处都没有时 SHALL 只用内置默认。发现根 MUST NOT 锚默认的会话专属工作区：未给 `--workspace` 时，默认工作区落在 `$MINIHNS_HOME/workspaces/<session_id>/`，配置文件不从那里找，也不因会话目录里恰好有一份同名文件而生效。

#### Scenario: 显式指定的配置文件生效

- **WHEN** 执行 `minihns run -p "x" --config <dir>/other.toml`，且发现根也有一份 `mini.config.toml`
- **THEN** 生效的是 `other.toml`，发现根那份被忽略

#### Scenario: 没有 --config 时读发现根

- **WHEN** 发现根存在 `mini.config.toml` 且未给 `--config`
- **THEN** 该文件里的设置生效

#### Scenario: 未给 --workspace 时发现根是启动目录

- **WHEN** 启动目录放着 `mini.config.toml`，不传 `--workspace` 执行一次 run
- **THEN** 该配置生效；`$MINIHNS_HOME/workspaces/<session_id>/` 里就算有一份 `mini.config.toml` 也不被读取

#### Scenario: 两处都没有时是内置默认

- **WHEN** 发现根没有 `mini.config.toml` 且未给 `--config`
- **THEN** 全部设置取内置默认，`session/start` 的 payload 与 M8 之前的形状一致

#### Scenario: 显式指定的文件不存在是参数错误

- **WHEN** `--config` 指向的路径不存在
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与所查找的路径，且没有创建 session 日志
