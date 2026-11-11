# Spec Delta

## MODIFIED Requirements

### Requirement: 技能发现按四级根与优先级

系统 SHALL 从四个根发现技能：项目内 `<workspace>/.minihns/skills/`（rank 100）、项目共享 `<workspace>/.agents/skills/`（rank 200）、用户级 `$MINIHNS_HOME/skills/`（默认 `~/.mini-harness/skills/`，rank 400）、内置 `src/mini_harness/builtin_skills/`（rank 600）。300（自定义目录）与 500（agents 家目录）不在本 change。

一个技能 SHALL 是 `<dir>/SKILL.md` 或扁平的 `<name>.md`，MUST NOT 递归发现子目录；名字 SHALL 匹配 kebab-case（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）。frontmatter SHALL 提供非空的 `name` 与 `description`，并 MAY 提供 `disable-model-invocation` 与 `user-invocable` 两个策略键（缺省都为允许）。策略键的取值 SHALL 接受大小写不敏感的 `true/false`、`yes/no`、`on/off`、`1/0`；其它拼写或非布尔值 SHALL 丢弃整个技能，MUST NOT 静默放行任何一面。名字不合规、frontmatter 缺失、描述为空或读不出的条目 SHALL 跳过，MUST NOT 让会话启动失败。描述进清单前 SHALL 截到 500 字符。同名技能 SHALL 只保留一个，rank 数字小者胜出；发现结果 SHALL 按名字排序，保证确定性。

#### Scenario: 四级根各有一个技能

- **WHEN** 四个根里各放一个不同名的技能
- **THEN** 清单按 rank 100 → 200 → 400 → 600 排列

#### Scenario: 同名技能高优先级胜出

- **WHEN** 项目内与用户级各有一个 `tdd` 技能
- **THEN** 清单里只有一个 `tdd`，来自项目内（rank 100）

#### Scenario: 名字不合规的条目被跳过

- **WHEN** 某个根里有一个名字带大写的 `Bad_Name.md`
- **THEN** 它不出现在清单里，会话照常开始

#### Scenario: 缺 description 或无 frontmatter 的条目被跳过

- **WHEN** 某个根里有一个没有 frontmatter 的 `flat.md`
- **THEN** 它不是技能，不出现在任何出口

#### Scenario: 非法策略值丢弃整个技能

- **WHEN** 某个技能写 `disable-model-invocation: maybe`
- **THEN** 整个技能被跳过，而不是按默认值放行

### Requirement: 清单注入，正文按需加载

`session/start.payload.skills` SHALL 只放**模型可调**技能的清单项 `{name, description, rank, path, model_invocable, user_invocable}`，MUST NOT 含正文，MUST NOT 含用户独占或两面都禁用的技能。受保护头部 SHALL 放紧凑清单（名字 + 一句描述），并受字符预算约束（默认 2000 字符）；超出时截断并留「还有 N 个技能未列出」的 marker。正文 MUST NOT 进受保护头部；它只在 `skill` 工具被调用后作为 `tool/result` 进入上下文与日志。

#### Scenario: 头部只有清单

- **WHEN** 一个模型可调技能存在且会话启动
- **THEN** `session/start.payload.skills` 有它的清单项；头部有名字与描述，没有正文

#### Scenario: 用户独占技能不进模型清单

- **WHEN** 一个技能写 `user-invocable: false`
- **THEN** 它不出现在 `session/start.payload.skills` 与受保护头部

#### Scenario: 超预算截断

- **WHEN** 技能多到超过字符预算
- **THEN** 头部只列前若干个，并带「还有 N 个技能未列出」

### Requirement: `skill` 工具按需读正文

系统 SHALL 提供 `skill` 工具，参数 `{name}`，返回该技能的正文（单次上限 32 KiB，超出截断并提示用 `read` 读全文）。结果 SHALL 是 DSH 同形的 XML 三段：`<skill_content name=…>` 包 `<skill_resources>`（技能文件路径）与 `<skill_instructions>`（正文）。未知名字 SHALL 是 `TOOL_ARGS_INVALID`；**非模型可调**（`disable-model-invocation: true`）的名字 SHALL 也是 `TOOL_ARGS_INVALID`，文本与未知区分开，且 MUST NOT 读正文。正文 SHALL 作为 `tool/result` 落日志，`replay` MUST NOT 依赖磁盘上的当前文件内容。

#### Scenario: 加载正文

- **WHEN** 模型调用 `skill(name="tdd")`
- **THEN** 结果是 `<skill_content>` + `<skill_instructions>`，含该技能正文；日志里有配对的 `tool/call` + `tool/result`

#### Scenario: 未知技能

- **WHEN** `skill(name="nope")`
- **THEN** 结果是 `TOOL_ARGS_INVALID`，不读任何文件

#### Scenario: 非模型可调技能不可用

- **WHEN** 一个技能写 `disable-model-invocation: true`，模型调用 `skill(name="它")`
- **THEN** 结果是 `TOOL_ARGS_INVALID`，文本说明它不可由模型调用，不读正文

#### Scenario: 正文超限

- **WHEN** 正文超过 32 KiB
- **THEN** 结果截断并提示用 `read` 读全文

### Requirement: 同一份命令面（命令是 UI 动作；技能 + 指令展开成消息）

CLI `chat` SHALL 提供 `/skills`、`/skill <name>`、`/help` 与 `/<技能名>`；host SHALL 提供 `GET /commands` 与 `POST /sessions/{id}/commands`。两边 SHALL 共用同一份命令实现，返回同一份清单与同一份正文。

**人机面只认用户可调的技能**：`/skills` SHALL 只列 `user_invocable` 的技能；`/<技能名>` 只对 `user_invocable` 的技能生效；`/skill <名字>` 也 SHALL 要求 `user_invocable`（非用户可调返回 `ok=false`）；host 的 `GET /commands?session_id=` 与 `POST` 同源。两面都禁用的技能 MUST NOT 出现在任何命令清单里。

命令是人机直连的 UI 动作，MUST NOT 自己创建模型消息。命令调用 SHALL 落 `command/run`（handler 之前，`{command_id, name, raw_input}`）与 `command/done`（结算之后，`{command_id, ok, text?}`）两条只进日志的事件；语法错误或未知命令的 admission miss MUST NOT 落任何日志。`/help` 是壳本地的帮助，不落日志。

`/<技能名>`（无指令）SHALL 打印正文、不开段；`/<技能名> <指令>` SHALL 把技能正文（XML 三段）与指令拼成一条 `user/message` 并开一个段——展开消息由命令的结果触发，命令本身仍只落两件套。host 的 `POST /sessions/{id}/commands {name:"<技能名>", arguments:"<指令>"}` SHALL 返回 202 与 `{queued, segment_id, cursor}`（空闲起段、忙时排队），与消息投递同一条队列。

#### Scenario: 两个入口同一份清单

- **WHEN** CLI 执行 `/skills`，host 调用 `GET /commands?session_id=<id>`
- **THEN** 两边只返回用户可调的技能命令与内置命令

#### Scenario: 用户独占技能出现在命令面

- **WHEN** 一个技能写 `disable-model-invocation: true`
- **THEN** `/skills` 列出它、`/<技能名>` 能加载它，模型目录与 `skill` 工具里没有它

#### Scenario: 非用户可调技能不在命令面

- **WHEN** 一个技能写 `user-invocable: false`
- **THEN** `/skills` 不列它；`/skill <名字>` 返回 `ok=false`

#### Scenario: 不带指令只查看

- **WHEN** CLI 执行 `/tdd`
- **THEN** 屏幕打印正文，日志里两件套事件，没有 `segment/start`

#### Scenario: 带指令展开成消息

- **WHEN** CLI 执行 `/tdd 帮我改个函数`
- **THEN** 日志里有 `command/run`（`name="tdd"`）、`command/done`、一条含技能正文与指令的 `user/message`，随后是一个新段

## ADDED Requirements

### Requirement: 技能调用策略

每个发现到的技能 SHALL 带两个独立的策略位：`model_invocable` 与 `user_invocable`，缺省都为 `true`。两个值 SHALL 在发现期从 frontmatter 解析并归一成布尔，MUST NOT 在出口各自猜测。

- 模型面（`session/start.payload.skills`、受保护头部、`skill` 工具）只认 `model_invocable`；
- 人机面（`/skills`、`/<技能名>`、`/skill <名字>`、host 命令清单）只认 `user_invocable`；
- 两个都为 `false` 的技能 SHALL 仍被发现进 `settings.skills`（供未来可信调用方），但 MUST NOT 出现在任何模型或人机出口。

#### Scenario: 默认两面都可调

- **WHEN** 技能不写任何策略键
- **THEN** 它同时出现在模型清单与 `/skills`

#### Scenario: 只给模型用

- **WHEN** 技能写 `user-invocable: false`
- **THEN** 模型清单与 `skill` 工具有它；`/skills`、`/<技能名>`、`/skill <名字>` 都没有

#### Scenario: 只给人用

- **WHEN** 技能写 `disable-model-invocation: true`
- **THEN** `/skills` 与 `/<技能名>` 有它；`session/start.payload.skills` 与 `skill` 工具没有

#### Scenario: 两面都禁用

- **WHEN** 技能同时写 `disable-model-invocation: true` 与 `user-invocable: false`
- **THEN** 它不出现在任何清单、工具或命令出口
