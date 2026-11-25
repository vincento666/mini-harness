# Spec Delta: chat-streaming

## ADDED Requirements

### Requirement: chat 的 `--stream` 是默认的 shell 模式

`minihns chat` SHALL 接受互斥的 `--stream` 与 `--no-stream`；不传时 MUST 为 `--stream`。`--no-stream` 的 stdout、stderr、日志与退出码 MUST 与加这个能力之前逐点相同。`--stream` SHALL 复用 `SessionEnv.on_delta`，MUST NOT 新造 provider 方法、内核流式路径或事件类型。

#### Scenario: 不传 flag 就是流式

- **WHEN** 执行 `minihns chat`，provider 的 fixture 声明 `deltas: ["你", "好"]`，人输入一行后等待该轮结束
- **THEN** stdout 在该轮结束之前依次出现 `你`、`好`，轮末不再重复整段 `你好`

#### Scenario: 显式关掉是旧行为

- **WHEN** 执行 `minihns chat --no-stream`，同一份 fixture
- **THEN** 该轮进行中 stdout 没有输出；轮末一次性打印 `你好`；stderr 没有 `[answer]`；日志与退出码与加这个能力之前相同

#### Scenario: 两个 flag 互斥

- **WHEN** 同一条命令同时给 `--stream` 与 `--no-stream`
- **THEN** 参数解析失败，退出码 2，不建日志

### Requirement: 正文增量写 stdout，`[answer]` 每轮一次

`--stream` 时，非空正文 delta SHALL 写 stdout，并在每个 delta 之后 flush。每一轮第一次非空正文 delta 之前，系统 SHALL 在 stderr 写一次 `[answer] ` 并 flush；同一轮内后续步的正文 MUST NOT 再写 `[answer] `。正文 MUST NOT 写 stderr；`[answer]` MUST NOT 写 stdout，也 MUST NOT 写进事件日志。

#### Scenario: 增量按序落到 stdout

- **WHEN** fixture 的 `deltas` 是 `["你", "好"]`，`content` 是 `你好`
- **THEN** stdout 里 `你` 在 `好` 之前出现，且 `你` 出现时该轮尚未结束（发生在轮末打印之前）

#### Scenario: 一轮两步只有一个标记

- **WHEN** 一轮里两步都产生非空正文 delta
- **THEN** stderr 里 `[answer] ` 恰出现一次

#### Scenario: 空 delta 不触发标记

- **WHEN** provider 只发空字符串 delta，最终 `content` 非空
- **THEN** stderr 里没有 `[answer] `，正文在轮末按回退规则打印

### Requirement: 按步去重与无 delta 回退

`--stream` 下，某一步已经流过非空正文 delta 时，轮末 MUST NOT 再打印该步 `model/response` 的整段 `content`。某一步没有流过任何非空正文 delta 时，系统 SHALL 在该步 `step/end` 落盘之后、下一步 `step/start` 之前，用该步的正文补一次输出（回退），MUST NOT 等到轮末——否则同轮里「前一步回退、后一步流式」会把顺序倒成 2→1。回退的正文 MUST 是该 `step_id` 下 `purpose` 不在 payload 里的那条 `model/response.content`，且 `content.strip()` 非空才输出；步末已经回退打印过的步，轮末 MUST NOT 再打印（同一步恰输出一次）。

去重与回退的判断单位 SHALL 是步，不是轮或会话。回复计数的游标 SHALL 按**非 `purpose`** 的 `model/response` 条数推进，MUST NOT 因跳过打印而回退。`--no-stream` 与会话入口为 `host` 时 MUST NOT 安装步末回退钩子：前者由轮末投影打印，后者由 SSE 的 durable 帧承载。

#### Scenario: 有 delta 不重复

- **WHEN** 某步流过 `你`、`好`，该步最终 `content` 是 `你好`
- **THEN** stdout 里 `你好` 恰出现一次

#### Scenario: 无 delta 在步末回退且只出现一次

- **WHEN** `--stream` 下某步的 provider 不发正文 delta，最终 `content` 是 `答案`
- **THEN** 该步结束、下一步开始之前，stdout 已出现 `答案`，且整轮结束时 `答案` 仍只出现一次

#### Scenario: 同一轮里混合不倒序

- **WHEN** 一轮两步：第一步没有 delta，第二步流过正文 delta
- **THEN** stdout 先出现第一步的 `content`，再出现第二步的增量；顺序不是 2→1，第一步也不在轮末重打

#### Scenario: 空 delta 不算流式

- **WHEN** provider 只发空字符串 delta，最终 `content` 非空
- **THEN** 该步按「没有流过非空 delta」处理，在步末回退打印 `content`

#### Scenario: 空白正文不出空行

- **WHEN** 某步 `content` 是空串或全空白（只调工具的步）
- **THEN** 步末不回退、不输出空行，与 `--no-stream` 的投影规则一致

#### Scenario: 压缩摘要不进 stdout

- **WHEN** 同一轮里发生过请求级压缩（`purpose == "compaction"` 的 `model/response`）
- **THEN** 该摘要从不出现在 stdout；回退只取该步真正的回复

### Requirement: 按轮收尾，目标多轮不粘连

每一轮的流式正文结束后，系统 SHALL 写一个换行并重置该轮的 `[answer]` 标记。`chat` 在目标活跃时连续开的多轮 MUST 各自成行；该轮的 `[轮] n/cap` 说明 SHALL 出现在该轮正文之前。一条输入只对应一个提示符，自动轮次之间 MUST NOT 打印提示符。

#### Scenario: 目标两轮各占一行

- **WHEN** 目标连续跑两轮，每轮正文非空，两轮之间没有人的输入
- **THEN** stdout 是两行正文，第一轮正文后换行；stderr 有 `[轮] 1/…` 与 `[轮] 2/…` 各一行

#### Scenario: 提示符只出现一次

- **WHEN** 一条输入触发一轮人类轮与两次自动续跑，随后回到提示符
- **THEN** 提示符在该条输入的整个过程中恰出现一次（在最后一轮结束后）

### Requirement: 流式取消按「该步回复是否已落盘」分叉

`--stream` 下轮进行中收到取消信号时，系统 SHALL 先看**该步的 `model/response` 是否已经落盘**，不是只看有没有流过 delta：

- 未落盘（流式读取中途被中断）：按既有轮级取消收尾，已经写出的 stdout 片段 MUST NOT 被撤回，MUST NOT 写该步的 `model/response`；日志写 `error/abort` 与 `step/end`（`stop_reason` 为 `ABORTED`）。
- 已落盘（模型已完整返回，取消落在工具派发或轮内其他窗口）：MUST 保留这条完整记录；MUST NOT 再补第二段正文（屏幕上已显示的增量就是这条记录的前缀）。

无论哪条路，`model/response` 要么不存在、要么是完整记录，MUST NOT 出现半条。进程 SHALL 回到提示符。

#### Scenario: 流式中途取消保留半句

- **WHEN** `--stream` 已显示正文 `半` 后收到 SIGINT，该步的 `model/response` 尚未落盘
- **THEN** stdout 只保留 `半`（加收尾换行），不再出现该步的最终 `content`；日志里该步是 `error/abort` + `step/end ABORTED`，没有 `model/response`

#### Scenario: 工具窗口取消保留完整记录

- **WHEN** 某步流过 delta 且 `model/response` 已落盘，取消发生在随后的工具派发中
- **THEN** 日志保留该条完整 `model/response`；stdout 不出现第二条正文；没有半条记录

#### Scenario: 没有增量时不吞整段

- **WHEN** `--stream` 下 provider 不发正文 delta，模型已完整返回并落盘，此时收到 SIGINT
- **THEN** 该步的完整 `content` 仍被写出（步末回退），日志里是完整 `model/response`

#### Scenario: 关闭流式时形状不变

- **WHEN** `--no-stream` 下轮进行中收到取消信号
- **THEN** 日志形状与加这个能力之前相同（生成已完成则仍写完整 `model/response`）

### Requirement: 流式不改变日志与 provider 契约

`--stream` MUST NOT 把 `model/delta` 或 `reasoning/delta` 写进日志，MUST NOT 新增事件类型，MUST NOT 改变 `model/response` 的载荷形状。Provider 仍只经 `generate(messages, tools, signal, on_delta=...)` 调用。

#### Scenario: 成功一轮的事件类型集合相同

- **WHEN** 同一份 fixture 分别用 `--stream` 与 `--no-stream` 跑完一轮成功回复
- **THEN** 两份日志的事件类型序列相同，`model/response` 的键集合相同，且都不含 `model/delta`

#### Scenario: replay 不受影响

- **WHEN** 对一份 `--stream` 跑出的日志执行 `minihns replay`
- **THEN** 退出码为 0，折叠结果与 `--no-stream` 的同内容日志一致
