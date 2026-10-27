---
status: proposed
---

# 宿主是常驻多会话 HTTP 服务：SSE 读、unary POST 写、Bearer token

H1 新增 `minihns host --http`：一个服务进程持有 N 个会话，`GET /sessions/{id}/events` 是 SSE（`snapshot` 帧 + durable `seq` 帧），写操作走 unary POST（`/sessions`、`/messages`、`/cancel`、`/approvals/{tool_call_id}`、`DELETE`），鉴权是 `Authorization: Bearer <MINIHNS_HOST_TOKEN>`，默认只绑 `127.0.0.1`，session id 只接受 `^[0-9a-f]{32}$`。装配从 `cli/main.py::_prepare_or_fail` 抽到 `session/assembly.py::assemble(...)`，`run` / `chat` / `serve` / `host` 四个入口共用同一条装配路。`serve` 的「一进程一会话、会话收尾即退出」保持不变，宿主是它旁边的新入口而不是它的模式开关。

Considered options：把 `serve` 直接改成常驻多会话——否，`serve` 的退出码 0/1/3/4/5 与「收尾即进程退出」是 M7 的成文判据，改它会同时改 CLI 契约与 UAT；用 WebSocket mux——否，DSH 的 `/api/remote.mux` 是为它自己的 27 条事件回显与双向流准备的，mini 的写操作是 unary、读是单向，SSE + POST 已经同形且少一层握手；用 stdio JSON——否，只能一个壳、一个进程，webview / 浏览器壳接不上。

Consequences：`session/start.payload.entry` 加第四个值 `host`（`run` / `chat` / `serve` / `host`），`prompt` 为空、人话走 `user/message`；宿主有自己的错误信封（`UNAUTHORIZED` / `SESSION_NOT_FOUND` / `SESSION_BUSY` / `TOO_MANY_SESSIONS` / `INVALID_ARGUMENT`），与 CLI 的退出码表分开；浏览器 `EventSource` 不能带 header，H1 的壳用 `fetch` 流，一次性 ticket 归壳阶段；测试落在 seam ⑥（真实子进程 + httpx）与 seam ②（装配），不新增测试缝；多租户、TLS、公网暴露都不做。
