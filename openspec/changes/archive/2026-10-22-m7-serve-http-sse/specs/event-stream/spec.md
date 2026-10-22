## ADDED Requirements

### Requirement: serve 把会话日志作为事件流输出
系统 SHALL 提供 `minihns serve --http`：启动一个会话（prompt 来自 `-p/--prompt`，必填非空）并在 `GET /events` 上以 SSE 输出该会话的日志——每条记录一帧，帧的 `id` 是该记录的 `seq`、`event` 是记录的事件类型、`data` 是**该记录整行的 JSON**（信封与 payload 都在里面）。事件流 MUST NOT 重排、合并、新增或改写日志里没有的事件，也 MUST NOT 把 HTTP 层的事实（连接、断开、状态码）写进日志。

#### Scenario: 一帧对应一条记录
- **WHEN** 一次 serve 会话跑完一个回合后正常收尾，客户端从连接开始读到底
- **THEN** 帧数与日志行数相同，每帧的 `id` 与 `event` 分别等于对应记录的 `seq` 与事件类型，`data` 解析后与日志那一行解析出的对象逐字段相等

#### Scenario: 事件流里没有日志里没有的事实
- **WHEN** 一次 serve 会话跑完，事件流与日志都在手上
- **THEN** 事件流里每个 `event` 值都在事件词表里，且日志里没有任何一条记录由连接、断开或 HTTP 请求产生

#### Scenario: 其它路径不给出事件流
- **WHEN** 客户端请求 `GET /`
- **THEN** 响应状态码为 404 且不是事件流，会话照常跑到自己的收尾

### Requirement: 续读游标是日志的 seq
系统 SHALL 支持从给定 `seq` 之后续读：请求带 SSE 标准的 `Last-Event-ID` 时 SHALL 从该 `seq` 之后开始；带查询参数 `from=<seq>` 时 SHALL 以它为准，且它 MUST 覆盖 `Last-Event-ID`；两者都没有时 SHALL 从第一条记录开始。游标指向尚未写出的 `seq` 时 MUST NOT 报错，SHALL 在后续记录写出时开始送帧。游标是负数或非整数时该请求 SHALL 是 400，会话不受影响；`0` 是合法游标（日志的第一条 `seq` 是 0）。

#### Scenario: 断开之后续读不重复不丢
- **WHEN** 客户端读到 `seq` 为 n 的帧后断开，再带 `Last-Event-ID: n` 重连并读到底
- **THEN** 重连后第一帧的 `id` 是 n+1，且整个会话的每条记录在两次连接里合计恰好出现一次

#### Scenario: from 覆盖 Last-Event-ID
- **WHEN** 一个请求同时带 `Last-Event-ID: 5` 与 `?from=2`
- **THEN** 第一帧的 `id` 是 3

#### Scenario: 游标指向还没写出的位置
- **WHEN** 会话还在跑，客户端带 `?from=<比已写出的条数大的 seq>` 连接
- **THEN** 请求不报错、不返回 400，客户端在后续记录写出时开始收到帧

#### Scenario: 游标是负数或非整数
- **WHEN** 客户端带 `?from=abc` 或 `?from=-1` 连接
- **THEN** 该请求的状态码是 400，会话不受影响、日志完整

#### Scenario: 游标 0 是从第一条记录之后续读
- **WHEN** 客户端带 `Last-Event-ID: 0` 连接
- **THEN** 第一帧的 `id` 是 1

### Requirement: 客户端断开不改变会话
系统 MUST NOT 因客户端断开、慢读或从未连接而改变会话：会话 SHALL 继续跑到它自己的收尾，日志 SHALL 完整。断开 MUST NOT 产生任何事件，也 MUST NOT 成为取消信号。多个客户端 SHALL 各按自己的游标读同一条流，互不遮蔽。

#### Scenario: 断开之后日志仍然完整
- **WHEN** 客户端读到中途断开且不再重连，会话继续跑到正常收尾
- **THEN** 日志的记录集合与一次不断开的同形会话相同（含 `session/end`），且日志里没有因断开产生的记录

#### Scenario: 两个客户端各读各的
- **WHEN** 两个客户端同时读同一条流，其中一个先断开
- **THEN** 另一个从自己的位置继续读到底，帧集合与单客户端读到底相同

### Requirement: serve 的会话收尾就是进程退出
系统 SHALL 在会话收尾时结束 serve 进程：`session/end` 写完之后进程结束，退出码 SHALL 取自固定表（正常收尾 0、provider 失败 1、围栏拒绝 3、预算溢出 4、取消 5）。serve 是一次性入口，一个会话恰一个段，MUST NOT 出现「段级收尾而进程继续」的形状。stdout SHALL 只打 session id 一行。

#### Scenario: 溢出在 serve 里就是进程退出
- **WHEN** 一次 serve 会话以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 日志里有 `error/context`、`turn/end`、`segment/end` 与 `session/end`，进程退出码为 4

#### Scenario: 取消在 serve 里就是进程退出
- **WHEN** serve 进程在会话进行中收到 Ctrl-C
- **THEN** 日志以 `error/abort`、`turn/end`（`stop_reason: ABORTED`）、`segment/end` 与 `session/end` 收尾，退出码为 5，且没有未捕获异常

### Requirement: host 与 port 在会话开始之前判掉
系统 SHALL 只接受 `--host` 取 `127.0.0.1` 或 `0.0.0.0`、`--port` 取 1 至 65535 的整数（照 DSH 的 `dsh-host-webserver`：`host: union("127.0.0.1","0.0.0.0")`、`port: natural().max(65535)`）。取值越界 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT`，且 MUST NOT 创建 session 日志。端口被占或绑定失败 SHALL 同样是 session 开始之前的失败：退出码 2、stderr 含 `INVALID_ARGUMENT` 与失败原因，MUST NOT 创建 session 日志、MUST NOT 发出任何模型请求。

#### Scenario: 端口被占不留下日志
- **WHEN** `--port` 指向一个已被占用的端口
- **THEN** 进程以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与该端口，session 目录里没有新日志文件

#### Scenario: 端口越界是参数错误
- **WHEN** 执行 `minihns serve --http -p "x" --port 0`
- **THEN** 退出码为 2、stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

### Requirement: serve 复用一次性入口的装配与参数表
系统 SHALL 让 `serve` 的 flag 表是一次性 `run` 的表减去 `--events`、加上 `--host` 与 `--port`；`serve` MUST NOT 接受 `--events`。`--http` 是装饰：M7 只有 HTTP 这一种传输，带不带它跑的是同一个会话。serve 的会话 SHALL 走与 `run` 同一条装配路（配置层叠、工具白名单、provider 与密钥、窗口预算），配置失败与 `run` 同形。`session/start` 的 payload 里 `entry` SHALL 是 `serve`、`prompt` 是 `-p/--prompt` 的原文。

#### Scenario: serve 的 entry 是 serve
- **WHEN** 执行 `minihns serve --http -p "x"` 带 mock provider 与 fixture
- **THEN** `session/start` 的 payload 里 `entry` 为 `serve`、`prompt` 为 `x`

#### Scenario: 不带 --http 也是同一个会话
- **WHEN** 执行 `minihns serve -p "x"`（不带 `--http`）带 mock provider 与 fixture
- **THEN** 退出码为 0、stdout 只有 session id 一行，`session/start` 的 payload 里 `entry` 为 `serve`

#### Scenario: serve 不接受 --events
- **WHEN** 执行 `minihns serve --http -p "x" --events jsonl`
- **THEN** 退出码为 2、stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: serve 的窗口预算失败与 run 同形
- **WHEN** 执行 `minihns serve --http -p "x"` 带使触发线为 0 的 `--window` 与 `--reserve`
- **THEN** 退出码为 2、stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志
