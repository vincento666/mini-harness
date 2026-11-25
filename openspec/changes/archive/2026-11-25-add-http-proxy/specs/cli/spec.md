# Spec Delta: cli

## ADDED Requirements

### Requirement: --proxy 让真实端点经显式代理出去

`run` / `chat` / `host` SHALL 接受 `--proxy URL`，把它交给 provider 的 HTTP transport。它 MUST 只支持 `http://` 与 `https://` 且主机非空；其它形状（含 `socks5://`）SHALL 以 `INVALID_ARGUMENT` 退出（退出码 2），MUST NOT 建日志、MUST NOT 发请求。`--provider mock` 时给 `--proxy` SHALL 被接受但无效果（mock 不发 HTTP）。

#### Scenario: 坏代理值当场拒绝

- **WHEN** 用 `--proxy socks5://127.0.0.1:1080` 跑一次 run
- **THEN** 退出码 2，stderr 说明只支持 http/https，且没有新建 session 日志

#### Scenario: 好代理值不改日志形状

- **WHEN** 用 `--proxy http://127.0.0.1:7897` 跑一次 run
- **THEN** `session/start` 的键集合与不给 `--proxy` 时完全相同（代理不进 payload）
