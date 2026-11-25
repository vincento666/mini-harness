# 设计：显式代理

## D1 用 transport，不用 `trust_env=True`

`httpx.AsyncClient(trust_env=True)` 会走 `urllib.getproxies()`：读 `HTTP_PROXY` / `HTTPS_PROXY` /
`NO_PROXY`，还要解析 `.netrc`。两个已知问题会立刻回来：

1. `NO_PROXY=...[::1]` 让 httpx 在**构造客户端**时抛 `InvalidURL`，它不是 `httpx.HTTPError`，
   会绕过 `generate` 的失败捕获（ADR-0006 的原文）。
2. 大小写两份变量并存时（本机就是：工具链注入了小写 `https_proxy`），`getproxies()` 的胜者
   取决于 dict 顺序——`--proxy` 显式给了却仍从别的出口出去，属于「看起来生效、其实没生效」。

所以走 `httpx.AsyncHTTPTransport(proxy=url)`：只吃一个 URL，不做环境解析，失败点收敛在装配期。

## D2 每次 `generate` 新建 transport

现在 `generate` 每次调用新建一个 `AsyncClient`（`openai_compat.py:347`）。`AsyncClient.aclose()`
会把传入的 transport 一起关掉，复用同一个 transport 的第二次调用会撞「transport is closed」。
所以 provider 只存 URL 字符串，transport 在 `generate` 里现建——与现有的「每步一个 client」
同一条生命周期，不引入连接复用这个新话题。

注入的 `transport=`（测试用的 `MockTransport`）优先级最高：给了它就不看 `proxy`，否则测试会被
真实 transport 顶掉。

## D3 不进日志

`session/start` 的记录是长期资产，而代理 URL 常带凭据（`http://user:pass@host:port`）。
代理只影响「包怎么出去」，不影响日志内容与折叠结果；replay 用的是同一份前缀，不需要知道出口。
所以 payload 不变，schema 不变，`replay` 的判据不动。

## D4 校验点放在装配期

`--proxy` 的坏值（不是 URL、`socks5://`、没有主机）在 `assemble` 里就判掉，返回
`INVALID_ARGUMENT` + 退出码 2。理由与端点三项一致：一个注定打不出去的会话不该先建日志、
先花钱再报错。校验用 `httpx.URL` 解析 + scheme 白名单，不自己写正则。
