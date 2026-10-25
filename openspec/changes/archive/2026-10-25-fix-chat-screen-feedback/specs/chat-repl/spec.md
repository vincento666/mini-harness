## MODIFIED Requirements

### Requirement: chat 的 stdout 只打印模型回复正文
系统 SHALL 在 stdout 上按发生顺序打印每条**不带 `purpose`**、且 `content` 去掉首尾空白后非空 的 `model/response` 的 `content` 原文。提示符 SHALL 打印在**不带换行**的同一行上，用户输入紧跟在提示符之后。MUST NOT 打印工具结果、`context/assembled` 或日志的其它投影；MUST NOT 因为一条空或全空白的 `content` 而在 stdout 上留下空行。带 `purpose` 的那次 `model/response` 是请求级压缩产出的内部摘要，不是给人的回复。

#### Scenario: 工具结果不上 stdout
- **WHEN** 一个回合派发一次 `read` 并拿到结果
- **THEN** stdout 里没有出现该工具结果的内容，只有模型回复正文与提示符

#### Scenario: 请求级压缩的摘要不上 stdout
- **WHEN** 一次请求级压缩写出带 `purpose` 的 `model/response`
- **THEN** stdout 里没有那条摘要的内容

#### Scenario: 收尾不打印日志
- **WHEN** 一次 chat 正常结束
- **THEN** stdout 里没有 `session/end` 的 JSON，且日志里的事实与 stdout 上看到的没有冲突

#### Scenario: 提示符不自带换行
- **WHEN** 一次 chat 的一条输入开一个段、该段以 `MODEL_COMPLETED` 收尾，stdin 是管道
- **THEN** stdout 上提示符与紧随其后的模型回复正文之间没有换行（该段只有一条带正文的回复时，stdout 恰为 `> <正文>\n> `）

#### Scenario: 只带工具调用的回合不留空行
- **WHEN** 一个段里前三个回合的 `model/response` 只带工具调用（`content` 为空）、第四个带正文
- **THEN** stdout 里那三个回合不各自产生空行，正文之前不出现连续空行

### Requirement: 段不以正常回复收尾时 stderr 看得见一行
当一个段**不以** `MODEL_COMPLETED` 收尾时（`PROVIDER_ERROR`、`CONTEXT_WINDOW_EXCEEDED`、`MAX_TURNS`、`FENCE_DENIED`、`ABORTED` 都在其中），系统 SHALL 往 stderr 打印一行说明：先打印该段的停止理由；当造成它的失败结果的 `code` 与停止理由**不同**时追加那个 `code`，相同时 MUST NOT 把同一个词打印两遍；当该失败结果带非空 `detail` 时追加那句 `detail`。没有失败结果时只有停止理由。stdout 的投影规则 MUST NOT 因此改变，这一行 MUST NOT 写进事件日志。段以 `MODEL_COMPLETED` 收尾时 MUST NOT 打印这一行。

#### Scenario: provider 失败的段在屏幕上有一行
- **WHEN** 一次 chat 的某段以 `error/model`（`code: PROVIDER_HTTP_STATUS`）收尾
- **THEN** stderr 里有一行含 `PROVIDER_ERROR` 与 `PROVIDER_HTTP_STATUS`，stdout 里没有出现这一行，日志里也没有

#### Scenario: 溢出的段在屏幕上有一行
- **WHEN** 一次 chat 的某段以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** stderr 里有一行含 `CONTEXT_WINDOW_EXCEEDED` 与造成它的失败结果的那句非空 `detail`，`CONTEXT_WINDOW_EXCEEDED` 这个词在这一行里只出现一次，且会话继续接受下一条输入

#### Scenario: 用完回合数的段在屏幕上有一行
- **WHEN** 一次 chat 的某段用完 `--max-turns` 并以 `MAX_TURNS` 收尾
- **THEN** stderr 里有一行含 `MAX_TURNS`，会话继续接受下一条输入

#### Scenario: 围栏拒绝收尾的段在屏幕上有一行
- **WHEN** 一次 chat 的某段以 `FENCE_DENIED` 收尾（stdin 不是终端，审批问不到人）
- **THEN** stderr 里有一行含 `FENCE_DENIED` 与造成它的失败结果的 `code`，stdout 里没有出现这一行，日志里也没有，会话继续接受下一条输入

#### Scenario: 取消的段在屏幕上有一行
- **WHEN** 一次 chat 的段进行中收到取消信号并以 `ABORTED` 收尾
- **THEN** stderr 里有一行含 `ABORTED`，stdout 里没有出现这一行，日志里也没有这一行，会话继续接受下一条输入

#### Scenario: 正常收尾不打扰
- **WHEN** 一次 chat 的段以 `MODEL_COMPLETED` 收尾
- **THEN** stderr 里没有这一行

### Requirement: REPL 里取消终止当前段而不是会话
当段进行中收到取消信号时，系统 SHALL 按既有的回合级取消形状收尾（`error/abort`、`turn/end`（`stop_reason: ABORTED`）与 `segment/end`（`stop_reason: ABORTED`））并 MUST NOT 写 `session/end`，会话 SHALL 回到提示符等下一条输入。当没有段在跑时收到取消信号，系统 SHALL 结束会话：写 `session/end`（`stop_reason: MODEL_COMPLETED`）、退出码 0，且 MUST NOT 留下未捕获异常或 traceback。

#### Scenario: 段中取消会话继续
- **WHEN** 一个段进行中收到 SIGINT
- **THEN** 该段以 `error/abort`、`turn/end`（`stop_reason: ABORTED`）与 `segment/end`（`stop_reason: ABORTED`）收尾，日志里没有 `session/end`，进程不退出

#### Scenario: 提示符上取消是正常收尾
- **WHEN** 没有段在跑时收到 SIGINT
- **THEN** 日志以 `session/end`（`stop_reason: MODEL_COMPLETED`）收尾，退出码为 0

#### Scenario: 提示符上取消没有 traceback
- **WHEN** 没有段在跑时收到取消信号（含在提示符刚打印出来、还没读入任何输入的那一刻）
- **THEN** 进程以退出码 0 结束，stderr 里没有出现 `Traceback`

## ADDED Requirements

### Requirement: chat 在 stderr 给出 session id
系统 SHALL 在会话开始时往 stderr 打印一行 session id，与这次会话的日志文件名里那串一致。它 MUST NOT 出现在 stdout，MUST NOT 写进事件日志，也 MUST NOT 改变 stdout 的投影规则。

#### Scenario: 启动时 stderr 上有 session id
- **WHEN** 一次 `minihns chat` 开始
- **THEN** stderr 里有一行含该会话的 session id，且用那个 id 跑 `minihns replay` 找得到这次会话的日志

#### Scenario: session id 不在 stdout 也不在日志
- **WHEN** 一次 chat 跑完并正常收尾
- **THEN** stdout 上只有模型回复正文与提示符，该会话的日志里没有任何一条记录是为了打印这个 id 而存在

### Requirement: 溢出之后屏幕上说清楚
当一个段以 `CONTEXT_WINDOW_EXCEEDED` 收尾时，stderr 上那一行 SHALL 含造成它的失败结果的非空 `detail`（含当时的预算读数与触发线，或「无可遮蔽的内容」那一句）。当同一个会话里**连续两个**段以 `CONTEXT_WINDOW_EXCEEDED` 收尾时，系统 SHALL 额外往 stderr 打印一行说明：这份会话的表层已经降不下去，退出并新开一个会话是可选动作。这一句在每个会话里 MUST NOT 打印第二次。这两行 MUST NOT 出现在 stdout，也 MUST NOT 写进事件日志。会话 MUST NOT 因此结束，也 MUST NOT 因此改变退出码。

#### Scenario: 溢出那一行带读数与触发线
- **WHEN** 一次 chat 的某段因为「无可遮蔽的内容」以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** stderr 那一行含当时的预算读数与触发线两个数

#### Scenario: 连续两次溢出时多出一行说明
- **WHEN** 一次 chat 里第一个段与第二个段都以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** stderr 里多出一行说明这份会话已经降不下去，且这一行不在 stdout、不在日志里

#### Scenario: 那句说明只说一次
- **WHEN** 一次 chat 里连续三个段都以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 那句说明在 stderr 里恰出现一次

#### Scenario: 溢出之后会话照旧继续
- **WHEN** 一个段以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 提示符回来、下一条输入开一个新的段，会话收尾的退出码仍是 0
