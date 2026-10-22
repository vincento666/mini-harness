# Design

## Context

见 proposal.md - Why。设计要处理的现状约束：

- 日志是追加式 JSONL、唯一真源；`events/reader.py` 只有「全量重读」一个入口（ADR-0002 第 32 条：回合循环每回合全量重读，压缩让日志变长）。
- 装配路已收成一条：`cli/main.py::_prepare_or_fail` 返回 `_Prepared | int`，`run` 与 `chat` 共用（第 50 条）。serve 是第三个消费者。
- 内核不知道入口存在：`chat` 靠 `start_session(entry=ENTRY_CHAT)` + `run_turn_segment` + `end_session` 拼出连续会话，`run` 走 `run_session`。
- 记录信封是 `schema_version` / `type` / `session_id` / `seq` / `ts` / `payload`（`events/record.py:14-22`）。
- DSH 的对照：`19387` 是 desktop profile 启动时传的 `--port`（`dsh-desktop-host/lib/index.js:231-235`）；`/api/remote.mux` 的定义是「承载**所有** Typert Remote 流的 WebSocket 路由」（`dsh-api-gateway/lib/types/stream-protocol.js:4`），unary RPC 走 HTTP、stream 方法必须走这条 WebSocket（`dsh-api-gateway/lib/index.js:730`、`:756`）。会话的流式输出是 `session/follow`：请求带「调用方已持有的 last committed seq」，返回 opening snapshot（带 `hasMore` / `maxMessages` 分页）+ gap-free 的 durable 事件帧 + 可选 cursorless 的 assistant-stream 帧（`dsh-api-session-controller/lib/typert.host.js:1554-1557`、`:2141`；客户端断言相邻帧 `right === left + 1`，`lib/types/client/transport.js:63`）。事件回显是另一条逻辑流 `$events`：27 条 allowlist（25 `emit` + 2 `waterfall`），**没有游标、不补历史**（`dsh-api-remotes/lib/types/remote-events.js:12-40`、`dsh-api-gateway/lib/index.js:810`、`:823`）。`dsh-host-webserver` 把 host 与 port 做成配置。

## Goals / Non-Goals

**Goals:**

- 让「日志里发生了什么」与「人眼前收到什么」是同一份事实：判据是帧与日志逐字段相等，不是「看起来像」。
- 续读靠 `seq` 这一个游标，不引入第二套会话身份。
- 内核不动：serve 只是第三个入口，`entry` 多一个值。

**Non-Goals:**

- 不做双向通道（审批、输入、取消都不从 HTTP 进来）。
- 不做多会话、不做持久监听（进程随会话结束而结束）。
- 不做客户端重连的指数退避、心跳帧、鉴权——mini 没有客户端，判据用 httpx 手工构造。

## Decisions

**D1 服务端用 aiohttp（人裁决）。** 备选是标准库 `asyncio.start_server` 手写最小 HTTP/1.1（零新依赖，代价是自己写请求行解析与分帧）与 starlette + uvicorn（两个依赖）。选 aiohttp 的理由：它是 asyncio 原生、与「单事件循环」的既有选型一致；`web.StreamResponse` 正是 SSE 需要的分块写；`AppRunner` + `TCPSite` 让「绑定失败当场退出」可控。实现时踩到的顺序事实（aiohttp 3.14）：先
`await runner.setup()` 再建站点（`BaseSite.__init__` 在 `runner.server is None` 时抛 `RuntimeError`，
`web_runner.py:56-57`），真正的绑定在 `TCPSite.start()` 的 `loop.create_server` 里，端口被占时抛 `OSError`。代价：新增运行时依赖（连带 `aiosignal` / `frozenlist` / `multidict` 进 `uv.lock`），AGENTS.md 的技术选型行要加一项。

**D2 SSE 而不是 DSH 的 WebSocket mux；只照 `session/follow` 的 durable 那一半。** mini 版故意简化：M7 没有任何要写进会话的输入，客户端只需要读。三层的对应写死在这里：`session/follow` 的 seq 游标与 gap-free durable 事件**照它**（游标就是 `seq`、从 `cursor + 1` 起、连续性由「帧数等于日志行数」兜住）；`$events` 的 27 条 allowlist 与两条 waterfall **不做**；assistant-stream 的 cursorless 逐字帧**不做**（前置是 provider 流式，ADR-0006 第 1 条）。代价新开 **ADR-0021** 写明，并且要写明**将来加什么、不用换什么**：第三阶段要补的是 snapshot 帧（加分页，游标语义不动）与一条回程 POST 端点——DSH 的回程 `$events/result` 本来就是 **unary HTTP RPC**（`stream-protocol.js:7-8`、`dsh-api-gateway/lib/index.js:624`、`:772`）而不是 WebSocket 帧，所以「单向流 + HTTP 回程」与 DSH 同形，**SSE 与 `seq` 游标都不是将来要换掉的东西**。真正贵的两处不在事件流这一层：waterfall 要的是可插拔 approval gate 与客户端身份（ADR-0002 第 28 条，归 M10），逐字流要的是 provider 流式与「什么不落日志」的边界（归 M11）。

**D3 一个进程一个会话，绑定发生在开日志之前。** 顺序：参数校验（含 host/port 词表）→ `TCPSite.start()` 绑定 → `_prepare_or_fail`（里面才 `EventLog.start`）→ 跑会话 → `end_session` → 退出码。绑定失败因此天然满足「不建日志」。备选「先装配再绑定」会在端口被占时留下一份空日志，与 event-stream 规格相冲。

**D4 `--host` / `--port` 是 CLI-only flag，不进配置层叠、不进 `session/start` 的 payload。** DSH 把它们做成配置（`dsh-host-webserver`），mini 故意窄：监听地址是入口的形状，不是会话设置——它不进 payload 词表（那条 Requirement 已 489 / 500 字符），也不影响折叠与预算。窄化的代价记进 ADR-0021：配置文件起不来 serve。连带后果：ADR-0002 第 38 条（可配字段名四处平行）**不被 serve 触发**，本里程碑只改判、不收。

**D5 帧的形状：`data` 是整行记录的 JSON。** `id` 与 `event` 是同一份 `seq` 与类型的 SSE 路由字段。这样「事件流与 JSONL 内容一致」可逐字段判；只送 payload 会丢掉 `ts` 与 `schema_version`，完成判据就判不动。

**D6 追读用增量 tail，不放大第 32 条。** `events/reader.py` 加一个 tail 入口：记住字节偏移，只解析新追加的完整行，未完成的残行留在缓冲（追加写与读并发时读半行是真实风险）。游标 → 帧的映射：客户端给 `n`，服务端从第一条 `seq > n` 开始送；冷启动那一次扫描是续读连接的代价，不是每帧的代价。

**D7 代码落点：`cli/serve.py` 新增，`cli/main.py` 加 `serve` 子命令。** HTTP 路由、SSE 分帧、游标解析、断开处理都住在入口层；内核只多一个 `ENTRY_SERVE` 常量与 `SessionEntry` Literal 的一个值。理由与 chat 的 D11 同一条：stdout / 事件流是日志的投影，内核不需要知道有人在看着。

**D8 Ctrl-C 在 serve 里照 `run`：会话级取消。** 用现成的 `sigint_handler(cancel)`，取消 → `ABORTED` → `session/end` → 退出码 5 → 进程结束。不用 chat 的两级 handler：serve 没有「提示符上没有段在跑」这个状态。

**D9 收账范围。** 收两条：第 40 条（`ConfigFailure.code` 收成 `Literal` 与词表常量）与第 50 条（`_prepare_or_fail` 返回 `Prepared | Failure`，调用方不再 `isinstance(..., int)`）——serve 复用这条装配路，是它们的直接前提。第 21、38、39、41 条逐条改判：serve 复用同一个 `SessionEnv` 与同一份参数表，没有带出「第二套门与上下文」，也没有新增跨层可配字段，四条继续挂着并写明新的触发条件。

**D10 seam 与测试策略。** 判据只写在 **seam ⑥**（真实子进程 `minihns serve --http --provider mock --fixture …` + 真实 httpx streaming 客户端）与 **seam ①**（`entry: "serve"` 的会话形状：一个段、`session/end` 在盘上、退出码）上，不新增测试缝，也不给 `cli/serve.py` 写内部单测（水平切片禁止）。判据清单：帧与日志逐字段相等且帧数相同；`Last-Event-ID` 续读不重复不丢；`?from=` 覆盖 header；游标超前不报错；断开之后日志完整；两个客户端各读各的；`GET /` 是 404；游标非法是 400 且会话不受影响；端口被占与 `--port 0` 是退出码 2 且没有新日志文件；`--events` 在 serve 上是退出码 2；溢出与取消在 serve 里就是进程退出（4 / 5）；`entry` 是 `serve`。

## Risks / Trade-offs

- [测试抢端口竞态] → helper 用 `127.0.0.1:0` 取一个空闲端口再关闭，失败重试三次并在报错里写明端口；不用 `--port 0`（词表是 1 至 65535）。
- [慢客户端把 tailer 拖在后面] → 磁盘是唯一真源：tailer 从文件读、不在内存里堆帧，落后不丢事实；aiohttp 的写背压只 await 在 tailer 这个 task 上，不阻塞内核 task。
- [追加写与 tail 读撞上残行] → 只消费到最后一个换行符，残行留到下一次；判据里用「帧数等于日志行数」兜住。
- [Windows 上 SIGINT 子进程判据已知不稳（M6 两条 skip）] → serve 的取消判据在 seam ① 用进程内 cancel 判、在 seam ⑥ 留一条 Linux-only 的子进程判据，终端那一半进 `docs/verification/m7-serve-http-sse-manual.md` 等人跑。
- [aiohttp 的默认超时与 keep-alive 影响判据稳定性] → 判据里显式给客户端读超时，服务端不设请求超时（会话时长由内核决定）。
- [事件流与日志一致只判 mock provider 路径] → 真实 provider 那一半是人手验收那一半（模型层等人跑），不进 CI。

## Open Questions

- 要不要一条只读端点（列 sessions、读已结束会话的日志）——等 M11 的 resume 有形状之后再定。
- 心跳帧与客户端超时判定——纯客户端体验，不改规格也不改任务拆分。
- 多会话并发与鉴权——第三阶段加壳时再定。
