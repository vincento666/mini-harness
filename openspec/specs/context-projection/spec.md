# context-projection Specification

## Purpose

定义如何从只追加的事件日志折叠出「当前算数的上下文」：受保护头部加保留尾部，冷启动全量重放，且折叠结果可被 replay 逐字段复现。
## Requirements
### Requirement: 当前上下文只由折叠派生
系统 SHALL 通过折叠事件日志得到每次模型调用的消息序列；MUST NOT 维护独立于日志的对话状态，也 MUST NOT 依赖缓存或检查点。冷启动时 SHALL 全量重放日志重建上下文。

#### Scenario: 冷启动逐点重建出同一上下文
- **WHEN** 进程结束后只给折叠器该 session 的日志文件
- **THEN** 对日志里每一条 `context/assembled`，用它之前的日志前缀折叠得到的消息序列与该记录的 payload 逐字段一致

### Requirement: 折叠产出形状为受保护头部加保留尾部

系统 SHALL 把受保护头部（内置系统提示 + 工具块 + 运行环境块 + 追加文本）放在折叠结果最前，其后按事件发生顺序保留对话体：`role` 为 `user` 的消息有**三个**来源——一次性 `run` 的 `session/start` payload 里的 prompt（对话体第一条）、REPL 的 `user/message` 记录，以及 goal 轮次注入的 `user/message`（`source.kind == "goal"`，与 REPL 同形，按 `seq` 顺序进对话体）。随后是 assistant 消息与工具结果消息。`user/message` 与其它正文记录一样可进遮蔽范围。`turn/start` 与 `turn/end` 与 `step/*` 一样是记账记录，MUST NOT 产出上下文里的消息，遮蔽它们对折叠结果没有效果。`goal/updated` MUST NOT 产出上下文里的消息——模型看到的目标事实来自 goal 轮次正文与工具调用历史。被 `compaction/summary` 遮蔽的记录不进入对话体（见「遮蔽范围由 compaction/summary 记录定义」）。

#### Scenario: 用户 prompt 是对话体第一条

- **WHEN** 一次 run 的 `session/start` payload 里 `prompt` 为「写一份报告」
- **THEN** 折叠结果里受保护头部之后的第一条消息 `role` 为 `user`、`content` 为该 prompt 原文

#### Scenario: goal 轮次正文进对话体

- **WHEN** 日志里有一条 `source.kind == "goal"` 的 `user/message`，正文为 `<goal_round>…</goal_round>`
- **THEN** 折叠结果里出现同内容的 `role: user` 消息，位置在 `seq` 顺序处，且 `goal/updated` 不产生任何消息

#### Scenario: 头部不被对话内容顶替

- **WHEN** fixture 的模型回复文本与内置系统提示完全相同
- **THEN** 折叠结果的第一条消息仍是内置系统提示

#### Scenario: 工具结果按顺序进入对话体

- **WHEN** 某步产生一次 `tool/call` 与对应 `tool/result`
- **THEN** 折叠结果按发生顺序包含该 assistant 工具请求消息与对应工具结果消息

#### Scenario: REPL 的输入按 seq 顺序进对话体

- **WHEN** 一份日志里有两条 `user/message`，中间夹着一组工具往返
- **THEN** 折叠结果里两条 `role` 为 `user` 的消息与那组往返按 `seq` 顺序出现，且头部之后第一条仍是第一条输入

#### Scenario: 被遮蔽的输入不进对话体

- **WHEN** 一条 `user/message` 落在某条 `compaction/summary` 的 `shadowed_range` 内
- **THEN** 折叠结果里没有它对应的 `user` 消息，该摘要的 `system` 消息在表层里

### Requirement: 每次模型调用前记录 context/assembled
系统 SHALL 在每一次要调模型的步调用 Provider 之前写入一条 `context/assembled` 记录，payload 含本次进入模型的完整消息序列与头部指纹（内容哈希）。带 `purpose: compaction` 的摘要调用 MUST NOT 写这条记录：它的上下文是该步装配点的表层再加一条固定的摘要指令。请求级压缩之后的那次重试 SHALL 在它之前再写一条 `context/assembled`，内容是遮蔽之后重新折叠的那份表层。照 DSH：一次 provider 尝试一条记录（`assistant/attempt`，`dsh-agent-loop/lib/index.js:1101-1134`），上下文记录只在表层变化之后补一条（`request/header` 只在头部变化时写，同文件 :1214-1225）。

#### Scenario: 每步恰有一条
- **WHEN** 一次 run 跑了 N 步，且没有步走到请求级重试
- **THEN** 日志里恰有 N 条 `context/assembled`，且每条都紧接在其对应的 `model/request` 之前

#### Scenario: 请求级重试之前还有一条
- **WHEN** 某步的模型调用得到 `PROVIDER_CONTEXT_OVERFLOW`，请求级压缩之后重试成功
- **THEN** 该步有两条 `context/assembled`，第二条紧接在重试那条 `model/request` 之前，它的消息序列含那条摘要、第一条不含

#### Scenario: 摘要调用不写装配记录
- **WHEN** 某步完成了一次请求级压缩
- **THEN** 那条带 `purpose: compaction` 的 `model/request` 之前没有 `context/assembled`

### Requirement: 折叠是确定性纯函数
系统 SHALL 保证对同一日志文件折叠两次得到逐字段相同的结果；折叠 MUST NOT 依赖墙钟时间、随机数或进程内残留状态。

#### Scenario: 同一日志折叠两次结果相同
- **WHEN** 对同一日志文件连续折叠两次
- **THEN** 两次折叠结果的消息序列与头部指纹完全相等

### Requirement: 折叠一致性由前缀重算定义
系统 SHALL 把「折叠结果与日志一致」定义为逐点性质：对日志任一前缀折叠，结果 MUST NOT 依赖该点之后的事件，也 MUST NOT 依赖进程内残留状态；`minihns replay` 按这条性质逐点校验，任一点不一致即为失败结果。

#### Scenario: 前缀折叠不受后续事件影响
- **WHEN** 对同一日志的两个前缀（前者是后者的严格前缀）分别折叠
- **THEN** 较短前缀的折叠结果与在完整日志上同一位置重算的结果相同

### Requirement: 系统提示与工具描述是内置常量且只能追加

系统 SHALL 使用内置常量系统提示作为受保护头部的第一条；内置常量之后 SHALL 注入一段 `tool:goal` 政策（取自 `GOAL_POLICY_VERSIONS[goal_policy]`，当前版本 `"v2"`），当且仅当该会话的 `session/start.payload.goal_policy` 命中表里的某个版本。政策文本 MUST 说明：轮由若干步组成且步数有上限；写满上限只是本轮结束不是失败；人输入开的轮不推进目标轮次；目标 `active`、已武装、还有轮次额度、没有待回答的问题**且未触发停滞闸门**时，轮结束会自动开下一目标轮（MUST NOT 承诺无条件续跑）；创建目标后想分轮就结束本轮；真正完成才调用 `update_goal` 标 `complete`。涉及 `create_goal` / `update_goal` 的句子 MUST 写成条件句，MUST NOT 给没有这些工具的会话下无条件命令。

政策文本 MUST 按版本冻结：改文案 MUST 新增版本并保留旧版本原文，MUST NOT 就地改写已有版本——`context/assembled` 存了完整 messages，就地改写会让按旧版本记录的日志重算不一致。`GOAL_POLICY_VERSION`（新会话写入的值）MUST 命中 `GOAL_POLICY_VERSIONS` 的某个键。

`--append-system-prompt` SHALL 把文本追加在政策段之后，MUST NOT 覆盖或移除政策段；MUST NOT 提供替换内置系统提示的入口。折叠 SHALL 从该会话的 `session/start` 取追加文本与 `goal_policy`，MUST NOT 读进程内的当前配置——没有 `goal_policy` 字段的旧日志不注入政策，折叠结果 MUST NOT 因本能力改变。

#### Scenario: 新会话默认带政策段

- **WHEN** 开一个新会话（不传 `--append-system-prompt`）
- **THEN** `session/start.goal_policy` 为 `"v2"`；首条 `context/assembled` 的头部以 `SYSTEM_PROMPT` 开头、含政策段的「写满」「目标轮」「停滞」等句子

#### Scenario: 旧版本按原文本重算

- **WHEN** 回放一份 `session/start.goal_policy` 为 `"v1"` 的日志
- **THEN** 头部注入的是 `v1` 的原文，不含 `v2` 才有的「若你有 update_goal 工具」；`replay` 退 0，`REPLAY_MISMATCH` 不出现

#### Scenario: 追加文本不覆盖政策段

- **WHEN** 传 `--append-system-prompt "额外规则"`
- **THEN** 头部顺序是 `SYSTEM_PROMPT` → 政策段 → `额外规则`；政策段仍在，不被替换

#### Scenario: 旧日志没有字段就不注入

- **WHEN** 回放一份 `session/start` 不带 `goal_policy` 的日志
- **THEN** 每条 `context/assembled` 与重算结果逐字段相等，`REPLAY_MISMATCH` 不出现，头部里没有政策段

#### Scenario: 政策段不可由调用方移除

- **WHEN** 配置文件写 `goal_policy = "off"`，或在命令行传 `--goal-policy off`
- **THEN** 配置那条报 `INVALID_ARGUMENT`（未知键），flag 那条报 `unrecognized arguments`；两者都留不下日志文件
- **AND** 正常会话的 `session/start.goal_policy` 仍是 `"v2"`，头部仍含政策段

### Requirement: 头部的工具块由日志前缀派生
系统 SHALL 让受保护头部里的工具块内容取自该装配点当时的工具名列表，且该列表 MUST 从该装配点之前的日志前缀派生（取自 `session/start` 的 payload），MUST NOT 取自进程内注册表或该点之后的事件。

#### Scenario: 注册了工具的日志可被逐点重放
- **WHEN** 对一次注册了五个文件工具的 run 的日志逐点重算折叠
- **THEN** 每条 `context/assembled` 的头部都含这五个工具名，且重算结果与该记录逐字段相等

#### Scenario: 头部不依赖装配点之后的事件
- **WHEN** 某条 `context/assembled` 之后的事件被改动或删除
- **THEN** 该点的头部工具块不变

### Requirement: 未配对的工具调用由折叠派生闭合
当折叠遇到一条没有配对 `tool/result` 的 `tool/call` 时，系统 SHALL 在折叠结果里为该调用派生一条 `role` 为 `tool`、`content` 为 `TOOL_OUTCOME_UNKNOWN` 的工具结果消息，使每个 assistant 工具请求消息都有配平的工具结果消息。该派生 MUST NOT 写入日志、MUST NOT 新造事件类型、MUST NOT 触发对该调用的自动重试，且 MUST 是确定性的。

#### Scenario: 半截日志折叠补出闭合
- **WHEN** 一份日志以「有 `tool/call` 没 `tool/result`」结尾
- **THEN** 折叠结果里该 `tool_call_id` 有一条 `role` 为 `tool`、`content` 为 `TOOL_OUTCOME_UNKNOWN` 的消息，且该日志文件的字节数与内容都不变

#### Scenario: 闭合不被重放成事件
- **WHEN** 对同一份半截日志连续执行两次 `minihns replay`
- **THEN** 日志里没有任何新记录，也没有任何类型为 `TOOL_OUTCOME_UNKNOWN` 的事件

#### Scenario: 完整日志不派生闭合
- **WHEN** 对一次正常收尾的 run 的日志折叠
- **THEN** 折叠结果里没有任何 `TOOL_OUTCOME_UNKNOWN` 消息

#### Scenario: 派生闭合是确定性的
- **WHEN** 对同一份半截日志连续折叠两次
- **THEN** 两次折叠结果的消息序列与头部指纹完全相等

#### Scenario: 闭合不改变已有消息的顺序
- **WHEN** 一份日志里未配对的调用之前已有若干条对话消息
- **THEN** 派生出的工具结果消息出现在该调用的 assistant 请求消息之后、该点之后的既有消息之前

### Requirement: 遮蔽范围由 compaction/summary 记录定义
折叠遇到一条 `compaction/summary` 时，系统 SHALL 把它 payload 里 `shadowed_range` 的 `start` 与 `end`（含两端）覆盖的那些记录视为不产出任何消息。受保护头部与 `session/start` 派生的那条 `user` 消息 MUST NOT 被遮蔽。该规则 MUST 是确定性的，且 MUST 只依赖该装配点之前的日志前缀。

#### Scenario: 被遮蔽的记录不产出消息
- **WHEN** 一份日志里有一条遮蔽了某段对话体的 `compaction/summary`
- **THEN** 折叠结果里不含那段记录对应的任何消息，而该段之后未被遮蔽的消息照常出现

#### Scenario: 被遮蔽的调用不派生闭合
- **WHEN** 被遮蔽的那段里有一条 `tool/call` 与配对的 `tool/result`
- **THEN** 折叠结果里既没有该调用的消息，也没有为它派生的 `TOOL_OUTCOME_UNKNOWN` 消息

#### Scenario: 遮蔽不拆散一对调用与结果
- **WHEN** 一次压缩完成
- **THEN** 折叠结果里没有任何一条 `role` 为 `tool` 的派生闭合消息是由该遮蔽范围造成的

#### Scenario: 压缩过的日志可被逐点重放
- **WHEN** 对一次发生过压缩的 run 的日志逐点重算折叠
- **THEN** 每条 `context/assembled` 都与其前缀的重算结果逐字段相等

### Requirement: 摘要作为头部之后的 system 消息进入表层
系统 SHALL 把每条 `compaction/summary` 的 `summary` 文本作为一条 `role` 为 `system` 的消息进入折叠结果，位置在受保护头部与 `session/start` 派生的那条 `user` 消息之后、保留尾部的第一条消息之前；多条摘要 SHALL 按各自记录的 `seq` 顺序排列。该消息 MUST NOT 被写进日志。

#### Scenario: 一次压缩后用户 prompt 之后是摘要
- **WHEN** 一份日志里有一条 `compaction/summary`
- **THEN** 折叠结果里 `session/start` 派生的那条 `user` 消息之后那条消息 `role` 为 `system`、`content` 为该记录的 `summary` 原文

#### Scenario: 两次压缩的摘要按 seq 排列
- **WHEN** 一份日志里有两条 `compaction/summary`
- **THEN** 折叠结果里两条 `system` 摘要消息相邻且顺序与两条记录的 `seq` 一致

### Requirement: 带压缩用途标记的模型回复不产出消息
`model/response` 的 payload 里 `purpose` 为 `compaction` 时，系统 SHALL 不把该记录折成 assistant 消息：它是压缩的记账，不是对话。没有该标记的 `model/response` 照常产出消息。

#### Scenario: 摘要的回复不在表层里出现两次
- **WHEN** 一次压缩的摘要文本来自一条 `purpose` 为 `compaction` 的 `model/response`
- **THEN** 折叠结果里该文本只作为 `system` 摘要消息出现一次，没有任何 assistant 消息携带它

#### Scenario: 没有标记的回复照常进入表层
- **WHEN** 一次 run 既有普通步回复又有压缩回复
- **THEN** 只有带 `purpose: compaction` 的那条不产出 assistant 消息

### Requirement: 头部的运行环境块由日志前缀派生
系统 SHALL 在受保护头部里放一块运行环境，内容取自该装配点之前的 `session/start` 的 `platform`（`os` 与 `shell`），位置在内置系统提示与工具块之后、追加文本之前。该块 MUST NOT 取自进程内注册表或该装配点之后的事件，也 MUST NOT 成为可由调用方替换的头部。

#### Scenario: 新会话的头部含运行环境块
- **WHEN** 一次 run 的 `session/start` payload 里 `platform` 记着 `os` 与 `shell`
- **THEN** 该会话每条 `context/assembled` 的头部里都有一条消息同时含这两个值，且 `header_fingerprint` 覆盖它

#### Scenario: 运行环境块逐点重放复现
- **WHEN** 对一份带 `platform` 的日志逐点重算折叠
- **THEN** 每条 `context/assembled` 与该记录逐字段相等，没有 `REPLAY_MISMATCH`

#### Scenario: 运行环境块不可由调用方替换
- **WHEN** 运行时传入 `--append-system-prompt "额外规则"`
- **THEN** 追加文本仍在运行环境块之后，头部里没有替换掉 `os` 与 `shell` 的入口

### Requirement: 运行环境块先点原生工具、再点本平台的 shell 命令
运行环境块 SHALL 在事实之外带一句建议：**先**点出原生工具（列文件用 `glob`、搜内容用 `grep`、读文件用 `read`），**再**点出这个平台的 shell 命令——记下来的 `shell` 是 `cmd.exe` 一类时给 `dir` / `findstr` / `Get-Content`，是 POSIX shell 时给 `ls -R` / `tail`。这句建议 MUST 由记下来的 `platform` 推出，MUST NOT 看折叠那一刻所在机器的平台——否则换一台机器重放会得到不同的头部。

#### Scenario: 原生工具排在 shell 命令之前
- **WHEN** 折叠一份带 `platform` 的日志
- **THEN** 运行环境块里 `glob` 出现的位置在 `dir`（记 posix 时是 `ls -R`）之前，两处建议不构成「同一件事两个说法」

#### Scenario: Windows 事实给 Windows 建议
- **WHEN** 折叠一份 `platform` 记着 `os` 为 `nt`、`shell` 为 `cmd.exe /c` 的日志（判据跑在哪个平台上都一样）
- **THEN** 运行环境块里点出 `dir`、`findstr`、`Get-Content`，且没有把 `ls` 说成可用命令

#### Scenario: POSIX 事实给 POSIX 建议
- **WHEN** 折叠一份 `platform` 记着 `os` 为 `posix`、`shell` 为 `/bin/sh -c` 的日志
- **THEN** 运行环境块里点出 `ls -R`、`tail`（`grep` 已在前一句原生工具里点过），且没有把 `dir` 说成可用命令

### Requirement: 没有平台事实的旧日志头部逐字节不变
当 `session/start` 的 payload 里没有 `platform` 时，系统 SHALL 不产出运行环境块，折叠出来的头部只有内置系统提示、工具块与追加文本。系统 MUST NOT 为缺失的平台事实填入猜测值。

#### Scenario: 旧日志的折叠结果不变
- **WHEN** 折叠一份 `session/start` 没有 `platform` 的日志
- **THEN** 头部与这条事实存在之前写下的形状逐字段相等，`header_fingerprint` 与该记录里的一致

#### Scenario: 旧日志 replay 不出 REPLAY_MISMATCH
- **WHEN** 对一份这样的日志跑 `minihns replay <session_id>`
- **THEN** 每个装配点都是 `verified … OK`，退出码为 0

