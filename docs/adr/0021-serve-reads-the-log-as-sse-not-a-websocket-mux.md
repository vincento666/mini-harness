---
status: accepted
---

# 事件流是 SSE 单向读，只照 DSH `session/follow` 里 durable 的那一半

M7 的 `minihns serve --http` 用 aiohttp 起一个 HTTP 服务，`GET /events` 是一条 SSE：日志每追加一行就一帧，`id` 是记录的 `seq`、`event` 是事件类型、`data` 是整行记录的 JSON；游标就是日志的 `seq`（`Last-Event-ID` 或 `?from=`，`0` 合法）。DSH 的对照是 WebSocket `/api/remote.mux` 上 `session/follow` 的 durable 事件那一半（`dsh-api-session-controller/lib/typert.host.js:1554-1557`、`:1530`；客户端断言相邻帧 `right === left + 1`，`lib/types/client/transport.js:63`）。**不做**的两样：`$events` 那 27 条转发（25 `emit` + 2 `waterfall`，无游标、不补历史，`dsh-api-remotes/lib/types/remote-events.js:12-40`），以及 assistant-stream 逐字帧——那是 provider 流式，归 ADR-0006 第 1 条与 M11。

为什么不是 WebSocket mux：mini 的 serve 只有一条「读日志」的流，SSE 是 HTTP 上的一条单向流，它的游标与日志的 `seq` 同构，断线续读是 HTTP 客户端的默认行为。取舍是拿不到 DSH 的双向 multiplex——回程（approval 应答、取消）M7 没有。**将来加什么是明确的**：opening snapshot 帧（分页，游标语义不动）与一条回程 unary POST 端点；DSH 的 `$events/result` 本来就是「Gateway 内部的 unary 端点」（`dsh-api-gateway/lib/types/stream-protocol.js:8`），所以 SSE 与 `seq` 游标都不是将来要换掉的东西。可插拔 approval 门归 ADR-0002 第 28 条与 M10。

窄化：`--host` / `--port` 是 CLI-only flag，不进配置文件——DSH 的 `dsh-host-webserver` 把两者做成配置（`host: union("127.0.0.1", "0.0.0.0")`、`port: natural().max(65535)`），mini 只把词表照过来。代价：配置文件写不出「这台机器的 serve 默认端口」，ADR-0002 第 38 条那笔「四处平行」的账因此没被 serve 触发（改判到 M10）。默认 `127.0.0.1:19400`：`19387` 是 DSH 的 desktop profile 在这台机器上占着的端口（`dsh-desktop-host/lib/index.js:231-235`），mini 的 serve 要能与它并存。

尾读是 20 ms 轮询加「只消费整行」：`events/reader.py::LogTail` 从游标之后读，`rfind(b"\n")` 之前的字节才消费。取舍是不做「追加即推送」，代价是最多 20 ms 的延迟，以及一条只能在缝 ④ 杀死的判据（design D6 记的那个存活变异）。

Considered options：WebSocket mux（否：M7 没有回程，双向 multiplex 是空架子，而 DSH 那 27 条 allowlist 是 shell 侧的概念，mini 的缝 ⑥ 判的是日志）；`EventLog.append` 直接推给 HTTP 层（否：ADR-0002 第 3 条刚把 `_replay` 下沉进事件层，反向再绑一次是把刚拆开的东西绑回去）；host / port 做成配置字段（否：见上面那条窄化）。

Consequences：`serve` 是第三个入口，`session/start.payload.entry` 的词表加一个值；会话收尾即进程退出，退出码表与 `run` 同（0 / 1 / 3 / 4 / 5）；HTTP 客户端断开、慢、从不连接都不改变会话，也不往日志里写任何 HTTP 事实。一个卡住的慢读者最多把进程退出拖到 aiohttp 的 `shutdown_timeout`（60 s），这条没测，记进 ADR-0002 第 54 条。
