# chat-repl Specification

## Purpose

定义 `minihns chat` 这个入口：一次 chat 是一个连续会话，一条输入开一轮，人话住在 `user/message` 里，会话是否继续由入口决定而不是由内核决定。
## Requirements
### Requirement: minihns chat 是一个会话的 REPL
系统 SHALL 提供 `minihns chat`：与 `minihns run` 共用同一份参数表、同一套配置层叠与同一个内核入口——`chat` 只少两个 flag：没有 `-p/--prompt`（人话从 stdin 按行进来），也没有 `--events`（stdout 上只有模型回复正文与提示符）。它跑一个**连续会话**：一次 chat 恰有一份 session 日志、恰有一个 `session_id`，`session/start` 在第一条输入之前写出，`session/end` 只在会话收尾时写出。会话是否继续由**入口**决定，内核 MUST NOT 知道 REPL 的存在（ADR-0011）。`session/start` 的 payload 里 `entry` 为 `chat`、`prompt` 为空串。

#### Scenario: 两条输入一份日志
- **WHEN** 一次 chat 里人输入两条内容后结束会话
- **THEN** 只创建一份 session 日志，里面恰有一条 `session/start` 与一条 `session/end`，两条输入各开一轮

#### Scenario: chat 与 run 共用配置层叠
- **WHEN** 工作区根写着 `max_steps = 2` 与 `tools = ["read"]`，执行 `minihns chat`
- **THEN** `session/start` 的 payload 里 `max_steps` 为 2、`tools` 只含 `read`，与同一形态的 run 一致

#### Scenario: 会话开始之前失败不建日志
- **WHEN** 执行 `minihns chat --provider openai` 而密钥环境变量未设
- **THEN** 退出码为 2、stderr 指出变量名，且没有创建任何 session 日志

### Requirement: REPL 的每条输入是一条 user/message
系统 SHALL 把 REPL 里每一条非空输入写成一条 `user/message` 记录，payload 含 `turn_id`（该输入开启的那一轮）与 `content`（原文），位置在该轮的 `turn/start` 之后、该轮的第一个 `step/start` 之前。空输入 MUST NOT 产生记录，也 MUST NOT 开启新轮。REPL 的 `session/start.payload.prompt` MUST 是空串：一个会话的人话只住在 `user/message` 里。

#### Scenario: 输入按顺序折成 user 消息
- **WHEN** 一次 chat 有两条输入
- **THEN** 第二次输入时的折叠结果里，对话体中恰有两条 `role` 为 `user` 的消息，顺序与输入顺序一致

#### Scenario: 空输入不开轮
- **WHEN** 人在提示符上只提交空白内容
- **THEN** 日志里没有新的 `user/message`，也没有新的 `turn/start`

### Requirement: 每条输入是一轮，轮内上限是 max_steps
系统 SHALL 让一条输入开一轮（`turn/start` … `turn/end`，见 `turn-loop`）：轮内步数上限是有效 `max_steps`（默认 8），`turn_id` 与 `step_id` 都在整个会话里连续编号且 MUST NOT 跨轮重置。一轮用完 `max_steps` MUST NOT 结束会话，系统 SHALL 回到提示符等下一条输入，下一条输入照样有完整的 `max_steps` 额度。

#### Scenario: 轮用完上限会话继续
- **WHEN** 一条输入的轮跑满了 `max_steps = 2`
- **THEN** 该轮有两条 `step/end`、`turn/end` 的 `stop_reason` 是 `MAX_STEPS` 且 `steps` 为 2、日志里没有 `session/end`，下一条输入开 `s2` 并从 `t3` 起编号

#### Scenario: 两个编号都在会话内连续
- **WHEN** 一次 chat 跑两轮共 5 步
- **THEN** 日志里 `turn_id` 恰为 `s1` 与 `s2`，`step_id` 恰为 `t1` 至 `t5`，每个 `step_id` 恰对应一条 `step/start` 与一条 `step/end`

### Requirement: REPL 里取消终止当前轮而不是会话
当轮进行中收到取消信号时，系统 SHALL 按既有的步级取消形状收尾（`error/abort`、`step/end`（`stop_reason: ABORTED`）与 `turn/end`（`stop_reason: ABORTED`））并 MUST NOT 写 `session/end`，会话 SHALL 回到提示符等下一条输入。当没有轮在跑时收到取消信号，系统 SHALL 结束会话：写 `session/end`（`stop_reason: MODEL_COMPLETED`）、退出码 0，且 MUST NOT 留下未捕获异常或 traceback。

#### Scenario: 轮中取消会话继续
- **WHEN** 一轮进行中收到 SIGINT
- **THEN** 该轮以 `error/abort`、`step/end`（`stop_reason: ABORTED`）与 `turn/end`（`stop_reason: ABORTED`）收尾，日志里没有 `session/end`，进程不退出

#### Scenario: 提示符上取消是正常收尾
- **WHEN** 没有轮在跑时收到 SIGINT
- **THEN** 日志以 `session/end`（`stop_reason: MODEL_COMPLETED`）收尾，退出码为 0

#### Scenario: 提示符上取消没有 traceback
- **WHEN** 没有轮在跑时收到取消信号（含在提示符刚打印出来、还没读入任何输入的那一刻）
- **THEN** 进程以退出码 0 结束，stderr 里没有出现 `Traceback`

### Requirement: chat 在 stdin 不是终端时照跑
系统 SHALL NOT 依赖 tty：`minihns chat` 从 stdin 按行读输入，读到 EOF 即结束会话——写 `session/end`（`stop_reason: MODEL_COMPLETED`）、退出码 0。管道或重定向进来的每一行都是一条输入。

#### Scenario: 管道喂行
- **WHEN** stdin 是管道且含两行非空内容
- **THEN** 日志里有两条 `user/message` 与两轮，会话以 `session/end` 收尾，退出码为 0

#### Scenario: 空 stdin 也是合法会话
- **WHEN** stdin 立刻 EOF
- **THEN** 日志里只有 `session/start` 与 `session/end`，没有任何 `turn/start` 与 `step/start`，退出码为 0

### Requirement: 轮不以正常回复收尾时 stderr 看得见一行
当一轮**不以** `MODEL_COMPLETED` 收尾时（`PROVIDER_ERROR`、`CONTEXT_WINDOW_EXCEEDED`、`MAX_STEPS`、`FENCE_DENIED`、`ABORTED` 都在其中），系统 SHALL 往 stderr 打印一行说明：先打印该轮的停止理由；当造成它的失败结果的 `code` 与停止理由**不同**时追加那个 `code`，相同时 MUST NOT 把同一个词打印两遍；当该失败结果带非空 `detail` 时追加那句 `detail`。没有失败结果时只有停止理由。stdout 的投影规则 MUST NOT 因此改变，这一行 MUST NOT 写进事件日志。轮以 `MODEL_COMPLETED` 收尾时 MUST NOT 打印这一行。

#### Scenario: provider 失败的轮在屏幕上有一行
- **WHEN** 一次 chat 的某轮以 `error/model`（`code: PROVIDER_HTTP_STATUS`）收尾
- **THEN** stderr 里有一行含 `PROVIDER_ERROR` 与 `PROVIDER_HTTP_STATUS`，stdout 里没有出现这一行，日志里也没有

#### Scenario: 溢出的轮在屏幕上有一行
- **WHEN** 一次 chat 的某轮以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** stderr 里有一行含 `CONTEXT_WINDOW_EXCEEDED` 与造成它的失败结果的那句非空 `detail`，`CONTEXT_WINDOW_EXCEEDED` 这个词在这一行里只出现一次，且会话继续接受下一条输入

#### Scenario: 用完步数的轮在屏幕上有一行
- **WHEN** 一次 chat 的某轮用完 `--max-steps` 并以 `MAX_STEPS` 收尾
- **THEN** stderr 里有一行含 `MAX_STEPS`，会话继续接受下一条输入

#### Scenario: 围栏拒绝收尾的轮在屏幕上有一行
- **WHEN** 一次 chat 的某轮以 `FENCE_DENIED` 收尾（stdin 不是终端，审批问不到人）
- **THEN** stderr 里有一行含 `FENCE_DENIED` 与造成它的失败结果的 `code`，stdout 里没有出现这一行，日志里也没有，会话继续接受下一条输入

#### Scenario: 取消的轮在屏幕上有一行
- **WHEN** 一次 chat 的轮进行中收到取消信号并以 `ABORTED` 收尾
- **THEN** stderr 里有一行含 `ABORTED`，stdout 里没有出现这一行，日志里也没有这一行，会话继续接受下一条输入

#### Scenario: 正常收尾不打扰
- **WHEN** 一次 chat 的轮以 `MODEL_COMPLETED` 收尾
- **THEN** stderr 里没有这一行

### Requirement: 压缩与遮蔽在屏幕上看得见
当一轮里写出了 `compaction/summary` 时，系统 SHALL 往 stderr 打印一行遮蔽反馈，含该条记录的 `shadowed_range`（起点与终点的 `seq`）、`tokens_before` 与 `tokens_after`。这一行 MUST NOT 出现在 stdout，也 MUST NOT 写进事件日志。轮里没有压缩时 MUST NOT 打印这一行。同一条 `compaction/summary` MUST NOT 被打印第二次：每轮只报该轮里新写出的那些记录。

#### Scenario: 压缩发生的那一轮有一行遮蔽反馈
- **WHEN** 一次 chat 的某轮里写出了一条 `compaction/summary`
- **THEN** stderr 里有一行含该条记录的 `shadowed_range` 起点与终点、`tokens_before` 与 `tokens_after`

#### Scenario: 同一条压缩记录只报一次
- **WHEN** 一次 chat 有两条输入开两轮，压缩只发生在第一轮里
- **THEN** 那条记录的遮蔽反馈在 stderr 里恰出现一次

#### Scenario: 没有压缩就没有遮蔽反馈
- **WHEN** 一次 chat 的轮跑完且日志里没有 `compaction/summary`
- **THEN** stderr 里没有遮蔽反馈那一行

#### Scenario: 遮蔽反馈不是日志的投影
- **WHEN** 一次 chat 的某轮发生了压缩
- **THEN** stdout 里没有那一行，事件日志里也没有；`minihns replay` 对同一份日志的输出不因这一行改变

### Requirement: chat 在 stderr 给出 session id
系统 SHALL 在会话开始时往 stderr 打印一行 session id，与这次会话的日志文件名里那串一致。它 MUST NOT 出现在 stdout，MUST NOT 写进事件日志，也 MUST NOT 改变 stdout 的投影规则。

#### Scenario: 启动时 stderr 上有 session id
- **WHEN** 一次 `minihns chat` 开始
- **THEN** stderr 里有一行含该会话的 session id，且用那个 id 跑 `minihns replay` 找得到这次会话的日志

#### Scenario: session id 不在 stdout 也不在日志
- **WHEN** 一次 chat 跑完并正常收尾
- **THEN** stdout 上只有模型回复正文与提示符，该会话的日志里没有任何一条记录是为了打印这个 id 而存在

### Requirement: 溢出之后屏幕上说清楚
当一轮以 `CONTEXT_WINDOW_EXCEEDED` 收尾时，stderr 上那一行 SHALL 含造成它的失败结果的非空 `detail`（含当时的预算读数与触发线，或「无可遮蔽的内容」那一句）。当同一个会话里**连续两轮**以 `CONTEXT_WINDOW_EXCEEDED` 收尾时，系统 SHALL 额外往 stderr 打印一行说明：这份会话的表层已经降不下去，退出并新开一个会话是可选动作。这一句在每个会话里 MUST NOT 打印第二次。这两行 MUST NOT 出现在 stdout，也 MUST NOT 写进事件日志。会话 MUST NOT 因此结束，也 MUST NOT 因此改变退出码。

#### Scenario: 溢出那一行带读数与触发线
- **WHEN** 一次 chat 的某轮因为「无可遮蔽的内容」以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** stderr 那一行含当时的预算读数与触发线两个数

#### Scenario: 连续两次溢出时多出一行说明
- **WHEN** 一次 chat 里第一轮与第二轮都以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** stderr 里多出一行说明这份会话已经降不下去，且这一行不在 stdout、不在日志里

#### Scenario: 那句说明只说一次
- **WHEN** 一次 chat 里连续三轮都以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 那句说明在 stderr 里恰出现一次

#### Scenario: 溢出之后会话照旧继续
- **WHEN** 一轮以 `CONTEXT_WINDOW_EXCEEDED` 收尾
- **THEN** 提示符回来、下一条输入开新一轮，会话收尾的退出码仍是 0

### Requirement: chat 的斜杠命令是人机直连的 UI 动作

`chat` SHALL 接受 `/<name>` 形式的斜杠命令：`/skills` 打印技能清单（名字、描述、rank）；`/skill <name>` 打印正文（**查看路径**，不开轮）；`/<技能名>` 把技能正文与一句默认指令（「用户调用了技能 X，请按技能执行」）拼成一条 `user/message` 并开一轮，让模型执行；`/<技能名> <指令>` 用指令替换默认句；`/help` 打印命令清单（内置命令 + 当前会话的技能命令）。命令本身 MUST NOT 创建模型消息（展开消息由命令结果触发）；`/skills`、`/skill`、`/<技能名>`、`/<技能名> <指令>` SHALL 落 `command/run` + `command/done`；`/help` 与未知命令 MUST NOT 落日志（未知命令在 stderr 提示）。命令名与参数的分隔 SHALL 是一个空格。

#### Scenario: `/skills` 不开轮

- **WHEN** 在提示符输入 `/skills`
- **THEN** 屏幕列出清单，日志里只有 `command/run` 与 `command/done`，没有 `turn/start`

#### Scenario: `/skill` 是查看路径

- **WHEN** 输入 `/skill tdd`
- **THEN** 屏幕打印正文，日志里只有 `command/run` 与 `command/done`，没有 `user/message` 或新轮

#### Scenario: 直接技能名开轮执行

- **WHEN** 输入 `/tdd` 或 `/tdd 帮我改个函数`
- **THEN** 日志里有 `command/run`（`name="tdd"`）、`command/done`、含正文的 `user/message`，随后 `turn/start`

### Requirement: 自动轮次在 stderr 留下边界

REPL 里由目标驱动自动开的轮（带 goal 轮次），系统 SHALL 在该轮开始前向 stderr 打印一行 `[轮] <n>/<cap>`，其中 `<n>` SHALL 只对**目标驱动自动开的轮**计数——人类轮（用户输入直接开的轮）MUST NOT 消耗或推进 `<n>`，`<cap>` 仍是目标账本里的轮次上限（显示镜像账本事实，两者不得为对齐观感而改账）。收尾时：额度用尽 SHALL 打印一行含 `已用尽 <n>/<cap>` 与 `round-limit`；因未决问题交回控制权 SHALL 打印一行含 `目标保持 active` 与「回答后自动继续」；零工具调用的空转 SHALL 打印一行含「已停止自动推进」与 `/goal resume` / `/goal complete`。这些行 MUST NOT 写进事件日志、MUST NOT 出现在 stdout；人工轮、`run` 与 `serve` 上的输出 MUST NOT 因此改变。「轮不以 `MODEL_COMPLETED` 收尾时打印一行」那条既有规则不变。

#### Scenario: 两轮续跑看得见边界

- **WHEN** 一个上限为 2 的目标在 chat 里连跑两轮
- **THEN** stderr 依次出现 `[轮] 1/2`、`[轮] 2/2` 与含 `已用尽 2/2` 的一行；stdout 里没有这些行

#### Scenario: 未决问题停在哪里看得见

- **WHEN** 第 1 轮问了一个人答不了的问题
- **THEN** stderr 有 `[轮] 1/3` 与含 `目标已暂停` 的一行，没有 `[轮] 2/3`；提示符回到人手里

#### Scenario: 人类轮不消耗自动轮编号

- **WHEN** 建目标发生在人类轮（人类轮里模型写了正文、调了工具），随后目标驱动自动续跑 3 个轮、目标上限为 3
- **THEN** stderr 依次出现 `[轮] 1/3`、`[轮] 2/3`、`[轮] 3/3`，编号与目标自述的第 N 轮一致；人类轮没有 `[轮]` 行、也没有让任何一个自动轮从 2 起跳

> 本 delta 不改任何实现行为——`<n>` 只计自动轮是既定账本语义（`goal-round-pacing` 落地、场次 3 tty 人跑与会话 `8ec5e70e…` 实机复核）；把语义显式钉进规格，是为了防止后续 change 以「对齐观感」为由把人类轮计入编号。`[轮]` 编号与模型自述轮次的日常对齐靠验收跑法（UAT 场次 3 提示词要求「建目标的本轮不要写任何正文」，change `round-label-prompt-alignment` 的 proposal），不靠改机制。

### Requirement: 提示符只在回到等待状态时出现

`minihns chat` 的提示符 SHALL 出现在两种时刻：会话开始后第一次等待输入、以及处理完一条非空输入（一轮或一条命令）之后。空白输入 MUST NOT 紧接着再出现一条提示符。提示符 MUST NOT 进事件日志，stdout 上模型回复正文的投影规则 MUST NOT 因本条改变。

#### Scenario: 粘贴末尾的空行不多出提示符

- **WHEN** 人向提示符提交一条带尾随空行的粘贴（等价于非空输入后紧跟一条空白输入）
- **THEN** stdout 上该次交互之后恰有一条提示符，没有第二条紧挨着出现

#### Scenario: 故意按回车后输入照常提交

- **WHEN** 人在提示符上只提交空白内容，然后在光标所在空行输入一句话
- **THEN** 这句话照常作为一条输入处理（写 `user/message`、开一轮），日志规则与投影规则不变

#### Scenario: 命令之后提示符照常回来

- **WHEN** 人输入 `/skills` 后再提交一条空白输入
- **THEN** `/skills` 的清单照常打印，之后提示符恰出现一次，空白没有再追加一条

### Requirement: chat 的思考帧走 stderr，正文投影不变

`chat` 在流式模式下 SHALL 把 `reasoning/delta` 增量写到 **stderr**，并在本轮第一次思考增量前打一次 `[thinking]` 头行（标记独占一行、自带换行，思考文本从头行下一行开始流式追加）；正文增量仍只写 stdout，`[answer]` 头行仍走 stderr 且每步至多一次。`[thinking]` 与 `[answer]` MUST 同构：都是独占一行的头，内容另起——不依赖模型正文是否恰好以前导换行开头（2026-11-26 UAT 人裁，thinking 对齐 answer）。思考 MUST NOT 出现在 stdout（stdout 仍只有模型回复正文与提示符）。

只有思考流、正文走步末回退的那一轮 SHALL 在 `finish_turn` 时补一个 `[answer]` 头行，且 MUST 先封住未收行的思考流再补标记，不让正文标记插进思考流中间；纯无增量的步仍不打标记（既有「空 delta 不触发标记」不变）。

#### Scenario: 思考不进 stdout

- **WHEN** 一次流式调用先发 reasoning 增量再发正文增量
- **THEN** stdout 只有正文；stderr 有 `[thinking]` 与 `[answer]` 头行各一次，`[thinking]` 在 `[answer]` 之前，两个标记各自独占一行

#### Scenario: 正文不带前导换行也不粘连

- **WHEN** 正文增量不以换行开头（如 `content` 是 `答案`）
- **THEN** stderr 以 `[answer]\n` 收尾，正文从头行下一行开始，不与标记粘在同一行

#### Scenario: 思考帧的取消不回归既有判据

- **WHEN** 正文已滚出几个字后按 Ctrl-C
- **THEN** 已显示前缀保留、不补打整段、`[轮] 收尾 ABORTED` 可见、进程回到提示符（`restore-chat-streaming` 的四项判据不变）

