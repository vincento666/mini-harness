# 提案：给 provider 一个显式的 HTTP 代理

## 为什么

2026-11-25 起，本机（出口 `111.55.211.222`，广州）直连 OpenRouter 的**推理请求**一律 400
`Request path cannot be relayed`，而同一把 key 的 `GET /api/v1/key`、`GET /api/v1/models` 都是 200；
换成经 `http://127.0.0.1:7897` 出去，同一条请求立刻 200。诊断记录在 `docs/reference/verification-endpoint.md` §5。

`provider` 规格现在明写「适配器不继承代理环境变量」（ADR-0006：本机 `NO_PROXY` 里的 `[::1]`
会让 httpx 抛 `InvalidURL`，而它不是 `httpx.HTTPError` 子类，会绕过失败捕获）。当时把代价写进了 ADR：
「处在公司代理之后的用户无法经代理访问远端端点」。现在这个代价到期了——用户在 harness 里没有任何出口可换。

## 要改什么

- `run` / `chat` / `host` 增加 `--proxy URL`：显式构造 `httpx.AsyncHTTPTransport(proxy=URL)`。
  **不读** `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` / netrc——那条要求原样保留。
- 配置键 `proxy`（顶层，字符串）；host 的 `POST /sessions` 请求体接受同名键。
- 只支持 `http://` 与 `https://` 且必须有主机；坏值在装配期当场 `INVALID_ARGUMENT`（退出码 2），
  不发任何请求、不建日志。

## 不做什么

- **不读环境变量代理**：`trust_env=False` 不动。把 `trust_env` 翻成 `True` 会让 `NO_PROXY=[::1]`
  那个 `InvalidURL` 回来，而它绕过失败捕获——违反不变量 B。
- **不把 `proxy` 写进 `session/start`**：代理 URL 可能带 `user:pass@`，日志是长期资产；
  它也不影响 replay 的确定性（相同前缀仍折叠出相同上下文）。
- **不做 SOCKS**：需要额外依赖 `httpx[socks]`，等真有需要再单独立项。
- **不改默认值**：不给 `proxy` 任何内置默认，没给就是直连，与现在完全一致。
