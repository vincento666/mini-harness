# Spec Delta

## Purpose

定义常驻宿主服务的外部契约：一个服务进程如何开会话、收发消息、取消一段、应答审批、列出与关闭会话，以及事件流、鉴权、错误信封与资源上限。它是 UI 壳与内核之间的运行时边界，不是 CLI 的另一个模式。

## ADDED Requirements

### Requirement: 宿主是常驻多会话服务

系统 SHALL 提供 `minihns host --http`：一个进程常驻、可同时持有多个会话，服务生命周期 MUST NOT 绑定单个会话的收尾；`serve` 的一次性语义 MUST NOT 改变。绑定失败或启动期参数错误 SHALL 以退出码 2 结束且不创建会话日志。

#### Scenario: 服务比会话活得久

- **WHEN** 启动 `minihns host --http` 并在一个会话收尾后继续请求 `GET /health`
- **THEN** 服务仍在运行，`GET /sessions` 仍能列出该会话

#### Scenario: 绑定失败不建日志

- **WHEN** `--port` 已被占用时启动 host
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，会话目录里没有新日志

### Requirement: 创建会话记录宿主入口

`POST /sessions` SHALL 用请求体里的设置创建会话，写一条 `session/start`，其 `entry` 为 `host`、`prompt` 为空串，并返回 `201` 与 `{session_id, cursor}`；设置非法、缺必需项或配置失败 SHALL 是 `400` 且不创建日志，鉴权失败 SHALL 是 `401`。

#### Scenario: 创建一个空闲会话

- **WHEN** 带 Bearer token 向 `POST /sessions` 发送 `{"workspace": "<dir>", "provider": "mock", "fixture": "<f>"}`
- **THEN** 返回 201，`session_id` 是 32 位小写十六进制，日志第一条是 `session/start`、`entry` 为 `host`、`prompt` 为空串

#### Scenario: 缺密钥不建日志

- **WHEN** 请求体选 `deepseek` 且 `DEEPSEEK_API_KEY` 未设
- **THEN** 返回 400，`error.code` 为 `INVALID_ARGUMENT`，会话目录里没有新日志

### Requirement: danger-full-access 要服务器显式允许

宿主 SHALL 拒绝请求体里 `sandbox` 为 `danger-full-access` 的会话创建，除非启动时给了 `--allow-danger-full-access`；拒绝 SHALL 是 `400`、`error.code` 为 `INVALID_ARGUMENT`，且不创建日志。

#### Scenario: 未允许时拒绝

- **WHEN** 服务器没有 `--allow-danger-full-access`，`POST /sessions` 的请求体写 `"sandbox": "danger-full-access"`
- **THEN** 返回 400，会话目录里没有新日志

#### Scenario: 允许后创建

- **WHEN** 服务器启动时给了 `--allow-danger-full-access`，同一请求
- **THEN** 返回 201，`session/start` 的 `sandbox` 为 `danger-full-access`

### Requirement: auto 审批要服务器显式允许

宿主 SHALL 拒绝请求体里 `approval` 为 `auto` 的会话创建，除非启动时给了 `--allow-auto-approval`；拒绝 SHALL 是 `400`、`error.code` 为 `INVALID_ARGUMENT`，且不创建日志；允许后该会话的 `write` / `edit` MUST NOT 产生 `approval/request` 或 `approval/response`。

#### Scenario: 未允许时拒绝

- **WHEN** 服务器没有 `--allow-auto-approval`，`POST /sessions` 的请求体写 `"approval": "auto"`
- **THEN** 返回 400，会话目录里没有新日志

#### Scenario: 允许后不产生审批记录

- **WHEN** 服务器给了 `--allow-auto-approval`，同一请求创建会话并让它 `write`
- **THEN** `write` 直接 `OK`，日志里没有任何 `approval/*` 记录

### Requirement: 消息开一个段，段进行中排队

`POST /sessions/{id}/messages` SHALL 在会话空闲时开一个段、写 `user/message` 并返回 `202`；段进行中再发 SHALL 进入深度为 1 的队列并返回 `202` 与 `queued: true`；队列已满 SHALL 返回 `429`；空消息 SHALL 返回 `400`。同一会话同一时刻 MUST NOT 有两个段在跑。

#### Scenario: 第二句在段进行中排队

- **WHEN** 第一句已经让段跑起来，立刻再 POST 一句
- **THEN** 第二次返回 202 且 `queued` 为 true，第一段收尾后第二句自动开下一个段，日志里两条 `user/message` 的先后与请求一致

#### Scenario: 队满拒绝

- **WHEN** 已有一段在跑、队列里已有一句，再 POST 第三句
- **THEN** 返回 429，`error.code` 为 `SESSION_BUSY`，不写 `user/message`

### Requirement: 取消只结束当前段

`POST /sessions/{id}/cancel` SHALL 只取消当前正在跑的段：日志写 `error/abort`、`turn/end(ABORTED)`、`segment/end(ABORTED)`，会话回到空闲并返回 `202`；没有段在跑时 SHALL 是 `200` 且不写任何记录；会话 MUST NOT 因此结束。取消 MUST NOT 清空队列：队列里的下一条在段收尾后照常开新段。

#### Scenario: 取消后会话还能继续

- **WHEN** 段进行中 POST cancel，等它收尾后再 POST 一条消息
- **THEN** 取消段以 `ABORTED` 收尾，第二条消息正常开新段并跑完

#### Scenario: 取消不清空已排队的消息

- **WHEN** 段进行中已经排了一条消息，然后 cancel
- **THEN** 当前段以 `ABORTED` 收尾，排队的那条随后开新段，日志里两条 `user/message` 都在

### Requirement: 审批应答是 HTTP 回程

`POST /sessions/{id}/approvals/{tool_call_id}` SHALL 用请求体的 `decision`（`approve` 或 `deny`）回答该会话里正在等待的审批，并让内核写 `approval/response`（`APPROVED` 或 `DENIED`）；未知或已失效的 `tool_call_id` SHALL 是 `404`；等待超过 300 s SHALL 以 `APPROVAL_UNAVAILABLE` 塌成拒绝结果；host 的审批 MUST NOT 读 stdin。

#### Scenario: 批准一次写

- **WHEN** 段因 `write` 停在审批上，POST 该 `tool_call_id` 且 `decision` 为 `approve`
- **THEN** 返回 200，日志写 `approval/response(APPROVED)`，随后该 `tool/result` 为 `OK`

#### Scenario: 拒绝一次写

- **WHEN** 同一形状的请求 `decision` 为 `deny`
- **THEN** 日志写 `approval/response(DENIED)`，该调用是 `DENIED_BY_APPROVAL`，段以 `FENCE_DENIED` 收尾

### Requirement: 会话列表与状态

`GET /sessions` SHALL 返回本进程持有的会话列表，每项含 `session_id`、`status`（`idle` / `running` / `ended`）、`workspace`、`created_at`、`last_seq` 与 `turns`；`GET /sessions/{id}` SHALL 返回同一形状的一条；未知 id SHALL 是 `404`。列表 MUST NOT 返回密钥或 `Authorization` 内容。

#### Scenario: 列表能看见刚开的会话

- **WHEN** 创建两个会话后 `GET /sessions`
- **THEN** 返回两条，`status` 与 `last_seq` 与各自日志一致

### Requirement: 关闭会话

`DELETE /sessions/{id}` SHALL 在会话空闲时写 `session/end(MODEL_COMPLETED)`、停止该会话并返回 `200`；段进行中 SHALL 是 `409`；未知 id SHALL 是 `404`；已关闭的会话再次 DELETE SHALL 是 `404`。

#### Scenario: 空闲时关闭

- **WHEN** 一个空闲会话收到 DELETE
- **THEN** 返回 200，日志最后一条是 `session/end`，`status` 变为 `ended`

#### Scenario: 段进行中拒绝关闭

- **WHEN** 会话正在跑段时 DELETE
- **THEN** 返回 409，段照常跑完，不写 `session/end`

### Requirement: 事件流是日志的逐行镜像

`GET /sessions/{id}/events` SHALL 是 SSE：每个 durable 帧的 `id` 是该记录的 `seq`、`event` 是类型、`data` 是整行记录的 JSON；游标来自 `?from=` 或 `Last-Event-ID`，`0` 合法、负数与非整数是 `400`；`?snapshot=1` 时 SHALL 先发一帧 `event: snapshot`（含 `session_id`、`status`、`last_seq` 与折叠后的 `messages`），随后从 `last_seq + 1` 继续送 durable 帧。H1 MUST NOT 送逐字 delta 帧。

#### Scenario: 帧与日志逐字段相等

- **WHEN** 跑完一个会话后从 0 读事件流
- **THEN** 帧数等于日志行数，逐帧的 `data` 解析后与对应记录相等

#### Scenario: snapshot 后只送新帧

- **WHEN** 会话已有 10 条记录时带 `snapshot=1` 连接
- **THEN** 第一帧是 `snapshot` 且 `last_seq` 为 9，之后只送 `seq > 9` 的帧

### Requirement: 鉴权是 Bearer token

除 `GET /health` 外，所有端点 SHALL 要求 `Authorization: Bearer <token>`；token 从 `MINIHNS_HOST_TOKEN` 读，至少 32 字符，缺失或过短 SHALL 让启动以退出码 2 结束且不建日志；token MUST NOT 进日志、错误 detail 或 `session/start`。缺 token 或 token 不符 SHALL 返回 `401` 且不写会话记录。

#### Scenario: 无 token 被拒

- **WHEN** 不带 Authorization 请求 `GET /sessions`
- **THEN** 返回 401，`error.code` 为 `UNAUTHORIZED`，没有新日志

#### Scenario: health 免鉴权

- **WHEN** 不带 token 请求 `GET /health`
- **THEN** 返回 200 与 `{protocol: 1, sessions: <n>}`

### Requirement: 来源与绑定

`host` SHALL 默认只绑 `127.0.0.1`；`--host 0.0.0.0` 仍要求 token。请求带 `Origin` 时 SHALL 只放行同源与 `Origin: null`，其它来源 SHALL 返回 `403` 且不写会话记录。带 `Origin` 的 `OPTIONS` 预检 SHALL 走同一来源判定，放行时 SHALL 允许 `Authorization` 与 `Content-Type` 请求头。

#### Scenario: 陌生 Origin 被拒

- **WHEN** 带 `Origin: https://example.com` 与正确 token 请求 `POST /sessions`
- **THEN** 返回 403，不创建日志

#### Scenario: 同源预检放行

- **WHEN** 同源页面发 `OPTIONS /sessions`，带 `Access-Control-Request-Headers: authorization,content-type`
- **THEN** 返回 2xx，允许头里含 `Authorization` 与 `Content-Type`

### Requirement: 会话 id 与资源上限

`session_id` 路径参数 SHALL 只接受 `^[0-9a-f]{32}$`，否则 `400`；日志路径 MUST 由 id 派生，MUST NOT 接受客户端给路径；本进程同时持有的会话数 SHALL 有上限（默认 4），超过 SHALL 返回 `429` 与 `TOO_MANY_SESSIONS`；同一会话同时在跑的工具仍受 8 个上限约束。

#### Scenario: 路径穿越被拒

- **WHEN** 请求 `GET /sessions/../secret/events`
- **THEN** 返回 400，不读任何日志

#### Scenario: 超过会话上限

- **WHEN** 已有 4 个会话时再 POST /sessions
- **THEN** 返回 429，`error.code` 为 `TOO_MANY_SESSIONS`，不建日志

### Requirement: 错误是 JSON 信封

宿主的错误响应 SHALL 是 `{"error": {"code": "...", "detail": "..."}}`，HTTP 状态与 `code` 固定对应：`INVALID_ARGUMENT` 400、`UNAUTHORIZED` 401、`FORBIDDEN` 403、`SESSION_NOT_FOUND` 404、`SESSION_BUSY` 409、`TOO_MANY_SESSIONS` 429、`INTERNAL` 500；`detail` MUST NOT 含密钥、Authorization 或完整日志行。

#### Scenario: 未知会话是 404

- **WHEN** 请求一个不存在的 32 位 id
- **THEN** 返回 404 与 `SESSION_NOT_FOUND`，stderr 没有 traceback

### Requirement: 服务退出取消所有段并收尾

收到 SIGINT 时，host SHALL 取消所有正在跑的段，并为每个会话写 `session/end`（运行中的先写 `error/abort` / `turn/end` / `segment/end`，空闲的直接写 `session/end(MODEL_COMPLETED)`），再退出；退出码 SHALL 为 0；MUST NOT 留下没有 `session/end` 的空转会话。收尾已经开始的段 MUST NOT 被写成半条。

#### Scenario: 退出时收干净

- **WHEN** 一个段正在跑时向 host 发 SIGINT
- **THEN** 该会话以 `ABORTED` 收尾、日志有 `session/end`，进程退出码为 0

### Requirement: 装配复用且失败不建日志

`host` SHALL 与 `run` / `chat` / `serve` 共用同一条装配路（配置层叠、工具白名单、provider 与密钥、窗口预算）；配置、密钥或工具白名单失败 SHALL 在创建日志之前塌成 `400` / 启动退出码 2，MUST NOT 留下空日志；成功会话的 `session/start` payload 字段表 MUST 与其它入口一致。

#### Scenario: 配置失败不建日志

- **WHEN** `POST /sessions` 的 `workspace` 根有一份非法 `mini.config.toml`
- **THEN** 返回 400，`error.code` 为 `INVALID_ARGUMENT`，会话目录没有新文件
