# Design

## Context

- `serve` 是 M7 的第三个入口：一进程一会话、只读 SSE、会话收尾即进程退出（ADR-0021）。UI 壳要的是常驻、多会话、可写回。
- 装配在 `cli/main.py::_prepare_or_fail`（私有，约 130 行），`run` / `chat` / `serve` 三处共用；`_Prepared` 只活在外壳里。
- 内核只认 `SessionEnv` 与 `run_turn_segment` / `start_session` / `end_session`；`chat` 的段循环在 `cli/main.py::_chat_session`。
- 审批是一个 `Protocol`：`ApprovalGate.request(tool_name, detail)`（`tools/fences.py`），默认实现 `StdinApprovalGate`；`dispatch_tool_call` 在提问前用 `on_approval_request` 写 `approval/request`。
- 日志信封是 `schema_version` / `type` / `session_id` / `seq` / `ts` / `payload`；`LogTail` 已能按 `seq` 增量读（M7）。
- DSH 对照：`session/follow` 是 opening snapshot + gap-free durable 帧 + 可选 cursorless assistant-stream 帧；`$events` 是另一条 27 条 allowlist 的流；回程是 unary HTTP RPC。H1 只照 durable + snapshot + unary POST，逐字帧归 H2。

## Goals / Non-Goals

**Goals:**

- 一个 host 进程持有 N 个会话，服务比会话活得久；壳能开会话、发消息、取消、审批、列会话、订阅事件。
- 内核不改语义：host 只是新入口，`entry` 多一个值；`serve` 的既有契约不变。
- 装配从 CLI 私有函数里抽出来，四个入口共用；失败仍在建日志之前。
- 鉴权、来源、session id、资源上限这些宿主事实在 spec 里写死，不靠实现顺手决定。

**Non-Goals:**

- 流式与逐字帧（H2）；WebSocket mux；TLS；多租户；公网暴露；UI 实现。
- fork / resume / session index 的磁盘扫描（M11）；子代理（M12）；OS 沙箱（M15）。
- 浏览器 `EventSource` 的 query token 与一次性 ticket（壳阶段再定）。

## Decisions

**D1 新命令 `minihns host --http`，不改 `serve` 的模式。** `serve` 的「一进程一会话、退出码 0/1/3/4/5、收尾即退出」是 M7 的成文判据；把它改成常驻会同时改 CLI 契约与 UAT。`host` 是旁边的新入口，复用 `serve` 的 SSE 分帧与 `LogTail`，但生命周期不同。

**D2 装配抽成 `session/assembly.py::assemble(...) -> Prepared | Failure`。** 返回的 `Prepared` 含 `provider` / `settings` / `log` / `registry`；`Failure` 含 `code` / `detail` / `exit_code`。CLI 把 `_Failure` 映射到 stderr 与退出码，host 把同一个 `Failure` 映射到 400 JSON。装配接受「请求体 + 环境变量」而不是 `argparse.Namespace`，这样 host 与 CLI 都能调用；`run` / `chat` / `serve` 改成 adapter，行为不变。这是 H1 唯一的内部重构，判据在 seam ⑥ 的既有黑盒用例上保持绿。

**D3 宿主会话对象：一个会话一个 task、一个队列、一个取消事件、一组审批 future。** `SessionHandle` 持有 `env`、`status`（`idle` / `running` / `ended`）、`queue`（深度 1）、`cancel`、`approvals: dict[tool_call_id, Future]`、`task`。同一会话同一时刻只有一个段在跑；队列空时 `POST /messages` 直接起段，段进行中入队；段收尾后由 host 的调度循环取队首开下一段。`DELETE` 只在 `idle` 允许；`ended` 的会话留着给 `GET /sessions` 读，直到进程退出。

**D4 协议是 HTTP/JSON + SSE。** 端点表：

| 方法 | 路径 | 成功 | 说明 |
|---|---|---|---|
| POST | `/sessions` | 201 `{session_id, cursor}` | 请求体含设置；`entry=host`、`prompt=""` |
| POST | `/sessions/{id}/messages` | 202 `{segment_id, cursor, queued}` | 空消息 400；队满 429 |
| POST | `/sessions/{id}/cancel` | 202 / 200 | 只结束当前段 |
| POST | `/sessions/{id}/approvals/{tool_call_id}` | 200 | `{decision: "approve"\|"deny"}` |
| GET | `/sessions` | 200 `{sessions: [...]}` | 内存里的会话 |
| GET | `/sessions/{id}` | 200 | 状态与 `last_seq` |
| DELETE | `/sessions/{id}` | 200 | 只在 idle |
| GET | `/sessions/{id}/events` | 200 SSE | `from` / `Last-Event-ID`；`snapshot=1` |
| GET | `/health` | 200 `{protocol: 1, sessions: n}` | 免鉴权 |

**D5 鉴权与安全基线。** token 从 `MINIHNS_HOST_TOKEN` 读（≥32 字符），不进 argv、不进日志、不进 `session/start`；启动时缺失即退出码 2、不建日志。默认绑 `127.0.0.1`；`--host 0.0.0.0` 仍要 token。`Origin` 只放行同源与 `null`；其它 403；`OPTIONS` 预检走同一判定并允许 `Authorization` / `Content-Type`。session id 只接受 `^[0-9a-f]{32}$`，日志路径由 id 派生。默认会话上限 4；`danger-full-access` 与 `approval: auto` 都需要启动时显式给 `--allow-danger-full-access` / `--allow-auto-approval`，否则请求 400。错误 detail 不回显密钥、Authorization 或完整日志行。

**D6 会话生命周期。** 创建：写 `session/start`（`entry=host`、`prompt=""`、其余字段由装配来）→ 状态 `idle`。发消息：写 `user/message`（段边界内）→ 起段 → `run_turn_segment`。段收尾：按 `SegmentOutcome` 更新状态；`MODEL_COMPLETED` / `MAX_TURNS` / `PROVIDER_ERROR` / `FENCE_DENIED` / `CONTEXT_WINDOW_EXCEEDED` / `ABORTED` 都回到 `idle`（溢出与围栏只停段，ADR-0019）；内核失败（`failure_code` 非空，日志层坏了）把会话标成 `ended` 并让触发它的请求回 500，因为写不出 `session/end`。关闭：`session/end(MODEL_COMPLETED)` → `ended`。SIGINT：取消所有段；运行中的等它写完 `error/abort` / `turn/end` / `segment/end`，空闲的直接写 `session/end(MODEL_COMPLETED)`；全部收完再退出 0。

**D7 审批门。** `ApprovalGate.request` 加 `tool_call_id` 关键字；`dispatch_tool_call` 把当前 `call.id` 传进去。host 的门：`approval/request` 已由 `ask_logged` 在提问前落盘；门把 `tool_call_id` 登记成 future，等 `POST /approvals/{id}`；300 s 超时 → `UNAVAILABLE`；`DELETE` / 段取消 / 进程退出时未决的 future 一律 `UNAVAILABLE`，不默认批准。CLI 的 `StdinApprovalGate` 只多收一个参数，行为不变。key 用 `tool_call_id`：同一个会话里同一时刻只可能有一个待审批项（段内工具串行到审批这一步，且 provider 的 `tool_call_id` 在一次响应内唯一）；实现若撞到重复登记，按 409 `SESSION_BUSY` 处理并在 detail 里写明，不新造错误码。

**D8 事件流。** `GET /sessions/{id}/events`：先解析 `from` / `Last-Event-ID`（`0` 合法，负数/非整数 400）；`snapshot=1` 时先发一帧 `event: snapshot`（`session_id` / `status` / `last_seq` / `fold()` 的 `messages`），随后从 `last_seq + 1` 送 durable 帧；无 snapshot 时从游标之后送。durable 帧沿用 M7 的形状：`id=seq`、`event=type`、`data=整行记录`。每个连接各自一个 `LogTail`；断开/慢读者不影响会话。H1 不送逐字帧；H2 在同一路径上加 `event: model/delta`（ephemeral、无 `id`），不改 durable 帧形状。

**D9 错误信封。** `{"error": {"code": ..., "detail": ...}}`；状态码与 code 固定映射（见 host-api spec）。401/403/404/409/429 这些宿主层错误不写会话日志；只有已经进入内核的失败才写 `error/*`。

**D10 装配失败与「不建日志」。** `assemble` 在 `EventLog.start` 之前完成全部校验（配置、密钥、窗口、工具白名单、sandbox/approval 词表、danger-full-access 许可）；失败返回 `Failure`，host 映射 400，日志目录不出现新文件。成功后才 `EventLog.start`。

**D11 测试策略。** 不新增测试缝：

| seam | 落点 | 判什么 |
|---|---|---|
| ⑥ CLI/HTTP 黑盒 | `tests/test_cli_host.py`（真实子进程 `minihns host` + httpx） | 开会话/发消息/排队/取消/审批/列表/关闭/SSE/401/403/404/409/429/路径穿越/退出收尾 |
| ① 回合循环 | `tests/test_turn_loop.py`、`tests/test_turn_cancel.py` | `entry: host` 的段形状；取消只结束段；队列不产生两个段 |
| ② 工具注册与管线 | `tests/test_approval_gate.py`、`tests/test_tool_registry.py` | `ApprovalGate` 收到 `tool_call_id`；host 门不读 stdin；装配复用 |
| ④ 日志 | `tests/test_event_log_append.py` | snapshot 的 `last_seq` 与日志一致；`from` 游标不重不漏 |

**D12 风险。** 端口冲突沿用 M7 的「取空闲端口再关」helper；Windows 上子进程 SIGINT 仍可能不稳，退出判据在 Linux runner 上补；队列深度 1 是产品决定，E1 量到丢消息再谈；浏览器 `EventSource` 不能带 header，壳阶段再做 ticket；多会话并发要防一个段把事件循环钉住（工具本身已异步）。

## Open Questions

- `GET /sessions` 在 host 重启后要不要扫盘列已结束会话？H1 只列本进程；M11 的 session index 再补。
- `POST /sessions` 要不要接受一个可选的 `prompt` 直接跑一段？H1 不做，保持「创建即空闲」。
- 会话上限 4 与审批超时 300 s 要不要做成配置？H1 先做常量，E1 量到再改。
