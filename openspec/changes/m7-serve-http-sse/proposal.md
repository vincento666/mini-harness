# Proposal

## Why

第一阶段只剩 M7。内核已经能从两个入口跑完一个会话（一次性 `minihns run`、连续会话 `minihns chat`），日志是唯一真源——可今天人要看「正在发生什么」，只能等进程结束再去读 JSONL，或者跑 `replay`。DSH 的 shell 是拿事件流实时驱动的（HTTP + WebSocket `/api/remote.mux` @ `127.0.0.1:19387`，27 条转发事件），mini 版没有这一层，不变量 F「全程可观测」就只落在盘上、不落在人眼前。M7 把日志变成一条能断线续读的事件流，同时用它带出第三套入口的门与上下文——ADR-0002 第 21、38、39、40、41、50 条都写着「等 serve 这个消费者出现才收」。

## What Changes

- 新增 `minihns serve --http`：**一个进程跑一个会话**（prompt 从 `-p/--prompt` 来，必填非空），会话的日志同时作为 SSE 事件流输出；会话收尾就是进程退出，退出码沿用固定表（人裁决）。
- 新增断线续读：每条 SSE 帧的 `id` 是日志的 `seq`；客户端带 `Last-Event-ID` 或 `?from=<seq>` 时从该点之后续读，两者都在场时 query 覆盖 header（人裁决）。
- 客户端断开不改变会话：会话继续跑到它自己的收尾，日志完整；断开不写任何事件。
- `session/start.payload.entry` 词表从 `run` / `chat` 扩成 `run` / `chat` / `serve`（人裁决）。
- 新增 `--host` / `--port`：`--host` 只接受 `127.0.0.1` / `0.0.0.0`（照 DSH `dsh-host-webserver` 的 `host: union("127.0.0.1","0.0.0.0")`、`port: natural().max(65535)`）；取值越界与绑定失败都是 session 开始之前的失败，退出码 2、不建日志（人裁决）。
- 服务端用 **aiohttp**（人裁决）：新增一个运行时依赖，进 `pyproject.toml` 与 AGENTS.md 的技术选型行。
- `bash` 的非 UTF-8 输出**按 DSH 结案**：lossy UTF-8（无效字节成 U+FFFD）是承诺不是缺陷，实现不改、补一条判据（人裁决「照 DSH」；证据 `dsh-subprocess-local/lib/output.js:193` 与 `:232` 的 `Buffer.concat(chunks).toString("utf8")`，对照文件工具 `dsh-fs-local/lib/index.js:333` 的 `TextDecoder("utf-8", { fatal: true })`）。

## Capabilities

### New Capabilities

- `event-stream`: `minihns serve --http` 的事件流形状（帧与日志逐字段一致）、续读游标、断开语义、绑定失败、会话收尾与进程退出码。

### Modified Capabilities

- `cli`: 新增 `serve` 子命令与 `--host` / `--port`；`entry` 词表加 `serve`；「退出码只取自固定表」里「一次性入口」从 `run` 扩成 `run` 与 `serve`。
- `turn-loop`: 四条入口相关的 Requirement 把「一次性入口」从 `run` 扩成 `run` / `serve`（`chat` 仍是段级收尾）；「一条输入开一个段」把 serve 写进「一条输入」的来源。
- `bash-tool`: 「bash 的输出有上限并标记截断」补一条 scenario，把 lossy UTF-8 写成承诺。

## 明确不做

- 不做工具事件（`tool/call` / `tool/result`）在 chat 的 stdout 上的投影，也不做 chat 的流式输出（ADR-0002 第 46 条，归 M7 之后）。
- 不做输入排队：段跑着的时候来的输入仍读不到（第 49 条，归 M7 之后）。
- 不做多会话并发、不做 POST 起会话、不做任何 web / Electron 外壳（第三阶段）。
- 不做 WebSocket 与 `remote.mux`：DSH 的会话流式是 `session/follow`（seq 游标 + snapshot + gap-free durable 帧），事件回显是另一条 `$events`（27 条 allowlist、两条 waterfall）；mini 版**故意**只照前者的 durable 那一半，用 SSE（单向、无握手、续读靠 `seq`）。将来要补的是 snapshot 帧与一条回程 POST 端点——DSH 的回程 `$events/result` 本来就是 unary HTTP RPC，所以 SSE 与 `seq` 游标都不是要换掉的东西。代价写进要新开的 ADR-0021。
- 不做输出 spill 文件与 `lossy` 标记：DSH 溢出时把完整字节流写进文件并留 `[output truncated; full output: <path>]`（`dsh-bash-local/lib/index.js:108-154`、`dsh-tool-bash/lib/index.js:137`），mini 的 16384 字节截断没有这一层——新开一条账，归 M10 的 `finalizeContent` 段。
- 不做审批的 HTTP 化：serve 里审批仍走 `StdinApprovalGate`（问题写 stderr）。
- 不做 OS 级围栏、不做 MCP、不做 resume 与折叠缓存（M11）。

## Impact

- 新依赖 aiohttp（`pyproject.toml`、`uv.lock`、AGENTS.md 技术选型行）；测试里的 HTTP 客户端用已有的 httpx。
- 新代码住在入口层：`src/mini_harness/cli/serve.py`（路由、SSE 分帧、续读游标）；`cli/main.py` 加 `serve` 子命令并复用 `_prepare_or_fail` 这条装配路。
- 判据只写在 seam ⑥（真实子进程 + 真实 HTTP 客户端）与 seam ①（`entry: "serve"` 的会话形状）上，不新增测试缝。
- 收账：ADR-0002 第 21、38、39、40、41、50 条在 serve 复用参数表与失败码表时收；第 30 条按 DSH 结案；新开 ADR-0021（aiohttp 与 SSE 而非 DSH 的 HTTP + WebSocket）。
