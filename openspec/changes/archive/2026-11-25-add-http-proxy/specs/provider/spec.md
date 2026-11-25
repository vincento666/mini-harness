# Spec Delta: provider

## MODIFIED Requirements

### Requirement: 适配器不继承代理环境变量

系统 SHALL 以不读取环境的方式发出请求：`HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY`、netrc MUST NOT 影响 provider 的请求。若调用方显式给出代理（`--proxy` / 配置键 `proxy`），系统 SHALL 用该 URL 构造 `httpx.AsyncHTTPTransport(proxy=...)` 并把请求交给它；显式代理 MUST NOT 改变「不读环境」这一条——两者是两条独立来源，环境代理始终无效。

#### Scenario: 主机的 NO_PROXY 里带方括号 IPv6

- **WHEN** 进程环境里 `NO_PROXY` 含 `[::1]`，执行一次 `--provider openai` 的 run
- **THEN** 请求照常发出，进程没有未捕获异常

#### Scenario: 显式代理只从 flag 来

- **WHEN** 进程环境里 `HTTPS_PROXY=http://10.0.0.1:1`，而命令行给的是 `--proxy http://127.0.0.1:7897`
- **THEN** 请求经 `127.0.0.1:7897` 发出，`10.0.0.1:1` 不被使用

#### Scenario: 没有 proxy 时行为不变

- **WHEN** 既没给 `--proxy`，配置文件里也没有 `proxy`
- **THEN** 发出的请求不经过任何代理，与加这个能力之前完全一致
