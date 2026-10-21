## ADDED Requirements

### Requirement: minihns chat 是一个会话的 REPL
系统 SHALL 提供 `minihns chat`：与 `minihns run` 共用同一份参数表、同一套配置层叠与同一个内核入口，跑一个**连续会话**——一次 chat 恰有一份 session 日志、恰有一个 `session_id`，`session/start` 在第一条输入之前写出，`session/end` 只在会话收尾时写出。会话是否继续由**入口**决定，内核 MUST NOT 知道 REPL 的存在（ADR-0011）。`session/start` 的 payload 里 `entry` 为 `chat`、`prompt` 为空串。

#### Scenario: 两条输入一份日志
- **WHEN** 一次 chat 里人输入两条内容后结束会话
- **THEN** 只创建一份 session 日志，里面恰有一条 `session/start` 与一条 `session/end`，两条输入各是一条 `user/message`

#### Scenario: chat 与 run 共用配置层叠
- **WHEN** 工作区根写着 `max_turns = 2` 与 `tools = ["read"]`，执行 `minihns chat`
- **THEN** `session/start` 的 payload 里 `max_turns` 为 2、`tools` 只含 `read`，与同一形态的 run 一致

#### Scenario: 会话开始之前失败不建日志
- **WHEN** 执行 `minihns chat --provider openai` 而密钥环境变量未设
- **THEN** 退出码为 2、stderr 指出变量名，且没有创建任何 session 日志

### Requirement: REPL 的每条输入是一条 user/message
系统 SHALL 把 REPL 里每一条非空输入写成一条 `user/message` 记录，payload 含 `turn_id`（该输入开启的那个回合段的第一个回合）与 `content`（原文），位置在该段的 `turn/start` 之后、该段的 `context/assembled` 之前。空输入 MUST NOT 产生记录，也 MUST NOT 开启回合段。REPL 的 `session/start.payload.prompt` MUST 是空串：一个会话的人话只住在 `user/message` 里。

#### Scenario: 输入按顺序折成 user 消息
- **WHEN** 一次 chat 有两条输入
- **THEN** 第二次输入时的折叠结果里，对话体中恰有两条 `role` 为 `user` 的消息，顺序与输入顺序一致

#### Scenario: 空输入不开回合
- **WHEN** 人在提示符上只提交空白内容
- **THEN** 日志里没有新的 `user/message`，也没有新的 `turn/start`

### Requirement: 每条输入是一个回合段，段内上限是 max_turns
系统 SHALL 把一条输入展开成一个回合段：段内回合数上限是有效 `max_turns`（默认 8），`turn_id` 在整个会话里连续编号（`t1`、`t2`…）且 MUST NOT 跨段重置。一段用完 `max_turns` MUST NOT 结束会话，系统 SHALL 回到提示符等下一条输入。

#### Scenario: 段用完上限会话继续
- **WHEN** 一条输入的段跑满了 `max_turns = 2`
- **THEN** 该段有两个 `turn/end`、最后一个 `stop_reason` 是 `MAX_TURNS`、日志里没有 `session/end`，下一条输入开启 `t3`

#### Scenario: turn_id 跨段连续
- **WHEN** 一次 chat 跑两个段共 5 个回合
- **THEN** 日志里 `turn_id` 恰为 `t1` 至 `t5`，每个恰对应一条 `turn/start` 与一条 `turn/end`

### Requirement: REPL 里取消终止当前段而不是会话
当回合段进行中收到取消信号时，系统 SHALL 按既有的回合级取消形状收尾（`error/abort` 与 `turn/end`（`stop_reason: ABORTED`））并 MUST NOT 写 `session/end`，会话 SHALL 回到提示符等下一条输入。当没有回合段在跑时收到取消信号，系统 SHALL 结束会话：写 `session/end`（`stop_reason: MODEL_COMPLETED`）、退出码 0。

#### Scenario: 段中取消会话继续
- **WHEN** 一个回合段进行中收到 SIGINT
- **THEN** 该段以 `error/abort` 与 `turn/end`（`stop_reason: ABORTED`）收尾，日志里没有 `session/end`，进程不退出

#### Scenario: 提示符上取消是正常收尾
- **WHEN** 没有回合在跑时收到 SIGINT
- **THEN** 日志以 `session/end`（`stop_reason: MODEL_COMPLETED`）收尾，退出码为 0

### Requirement: chat 在 stdin 不是终端时照跑
系统 SHALL NOT 依赖 tty：`minihns chat` 从 stdin 按行读输入，读到 EOF 即结束会话——写 `session/end`（`stop_reason: MODEL_COMPLETED`）、退出码 0。管道或重定向进来的每一行都是一条输入。

#### Scenario: 管道喂行
- **WHEN** stdin 是管道且含两行非空内容
- **THEN** 日志里有两条 `user/message`，会话以 `session/end` 收尾，退出码为 0

#### Scenario: 空 stdin 也是合法会话
- **WHEN** stdin 立刻 EOF
- **THEN** 日志里只有 `session/start` 与 `session/end`，没有任何 `turn/start`，退出码为 0

### Requirement: chat 的 stdout 只打印模型回复正文
系统 SHALL 在 stdout 上按发生顺序打印每条 `model/response` 的 `content` 原文，并打印一行固定提示符；MUST NOT 打印工具结果、`context/assembled` 或日志的其它投影。

#### Scenario: 工具结果不上 stdout
- **WHEN** 一个回合派发一次 `read` 并拿到结果
- **THEN** stdout 里没有出现该工具结果的内容，只有模型回复正文与提示符

#### Scenario: 收尾不打印日志
- **WHEN** 一次 chat 正常结束
- **THEN** stdout 里没有 `session/end` 的 JSON，且日志里的事实与 stdout 上看到的没有冲突
