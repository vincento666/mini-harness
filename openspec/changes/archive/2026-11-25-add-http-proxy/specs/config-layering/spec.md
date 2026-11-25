# Spec Delta: config-layering

## ADDED Requirements

### Requirement: proxy 是端点出口的可配键

`mini.config.toml` SHALL 接受顶层键 `proxy`（字符串），取值优先级与其它可配字段一致：命令行 `--proxy` > 配置文件 `proxy` > 没有（直连）。值 MUST 是 `http://` 或 `https://` 的绝对 URL；类型不对按 `CONFIG_INVALID_VALUE` 拒，形状不对在装配期以 `INVALID_ARGUMENT` 拒。`proxy` MUST NOT 写进 `session/start` 的配置快照。

#### Scenario: 配置文件给 proxy

- **WHEN** 配置文件写 `proxy = "http://127.0.0.1:7897"` 且命令行不给 `--proxy`
- **THEN** 该会话的请求经这个代理发出

#### Scenario: 命令行覆盖配置文件

- **WHEN** 配置文件写 `proxy = "http://127.0.0.1:7897"`，命令行给 `--proxy http://127.0.0.1:8888`
- **THEN** 请求经 `8888` 发出

#### Scenario: 类型不对是配置错误

- **WHEN** 配置文件写 `proxy = 7897`
- **THEN** 会话开始之前失败，`CONFIG_INVALID_VALUE`，退出码 2
