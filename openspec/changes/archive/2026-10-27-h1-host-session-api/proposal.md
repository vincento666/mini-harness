# Proposal

## Why

`serve` 是一次性、只读的：会话由进程启动时决定，客户端只能看、不能说、不能批、不能停。UI 壳要的是相反的形状——服务先起、会话随时开、消息随时发、审批与取消从壳回来。装配又锁在 `cli/main.py::_prepare_or_fail` 里，壳要复用只能 import 私有函数。H1 把这条宿主边界立起来，H2 再补流式；没有 H1，第三阶段的壳只能绑在 CLI 进程的 stdin/stdout 上。对照 DSH：`session/follow` 的 durable 帧与 `seq` 游标照，`$events` 的 27 条 allowlist 与 WebSocket mux 不做（ADR-0021、ADR-0031）。

## What Changes

- 新增 `minihns host --http`：常驻、多会话，服务比会话活得久；`serve` 的 one-shot 语义保持不变（ADR-0031）。
- 装配抽成 `session/assembly.py::assemble(...)`，`run` / `chat` / `serve` / `host` 共用；失败仍是 `(code, detail, exit_code)` 结果，不是异常。
- 端点：会话的创建 / 消息 / 取消 / 审批 / 列表 / 关闭，加一条 `GET /sessions/{id}/events`（`snapshot` 可选 + `seq` 游标）；写操作与读列表要 `Authorization: Bearer <MINIHNS_HOST_TOKEN>`，`GET /health` 免鉴权。
- 会话：`session/start.entry` 加 `host`、`prompt` 为空；一条 `POST /messages` 开一个段，段进行中再发排队（深度 1）、队满 429；取消只结束当前段；`DELETE` 只在空闲时允许。
- 审批：`ApprovalGate` 的接口带上 `tool_call_id`，`host` 用 HTTP 应答实现它；stdin 门保留给 CLI；超时（300 s）塌成 `UNAVAILABLE`。
- 安全：默认绑 `127.0.0.1`；session id 只接受 32 位小写十六进制；同时在跑的会话上限 4；错误信封不回显密钥；`Origin` 只放行同源与 `null`；`danger-full-access` 与 `approval: auto` 都要服务器启动时显式允许。
- UAT 骨架：`docs/verification/h1-host-session-api-uat.md`。
- 本 change 明确不做：流式（H2）、WebSocket mux、TLS、多租户、公网暴露、UI 实现、浏览器 `EventSource` 的 query token、fork / resume（M11）、子代理（M12）、OS 沙箱（M15）。

## Capabilities

### New Capabilities
- `host-api`: 常驻宿主服务的会话生命周期、消息与排队、取消、审批应答、会话列表/状态、关闭、SSE 事件流（snapshot + durable 帧）、鉴权、错误信封与会话上限。

### Modified Capabilities
- `cli`: `session/start.payload.entry` 的词表加 `host`；`host` 与其它入口共用装配、配置与密钥判据。
- `fences`: 「ask 档位往 stdin 提问」一般化成「ask 档位向本次入口的 approval 门提问」；stdin 是 CLI 的门，host 的门是 HTTP 应答；非 tty 那条限定为 CLI 入口。

## Impact

代码：新 `cli/host.py`、`session/assembly.py`、`session/host.py`（宿主会话对象）；`cli/main.py` 三处入口改用装配；`loop/turn_loop.py` 的 `SessionEntry` 加 `host`；`tools/fences.py::ApprovalGate` 加 `tool_call_id`；`tools/dispatch.py` 传递它。测试：seam ⑥（真实子进程 `minihns host` + httpx）、seam ①（`entry: host` 的段形状）、seam ②（装配与 approval 门）；不新增测试缝。文档：ADR-0031、`docs/stage-map.md`、UAT 骨架。依赖：aiohttp 已在；无新依赖。
