# skills Specification

## Purpose
TBD - created by archiving change m14-skills-and-commands. Update Purpose after archive.
## Requirements
### Requirement: 技能发现按四级根与优先级

系统 SHALL 从四个根发现技能：项目内 `<workspace>/.minihns/skills/`（rank 100）、项目共享 `<workspace>/.agents/skills/`（rank 200）、用户级 `$MINIHNS_HOME/skills/`（默认 `~/.mini-harness/skills/`，rank 400）、内置 `src/mini_harness/builtin_skills/`（rank 600）。300（自定义目录）与 500（agents 家目录）不在本 change。

一个技能 SHALL 是 `<dir>/SKILL.md` 或扁平的 `<name>.md`，MUST NOT 递归发现子目录；名字 SHALL 匹配 kebab-case（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）。frontmatter SHALL 提供非空的 `name` 与 `description`，并 MAY 提供 `disable-model-invocation` 与 `user-invocable` 两个策略键（缺省都为允许）。策略键的取值 SHALL 接受大小写不敏感的 `true/false`、`yes/no`、`on/off`、`1/0`；其它拼写或非布尔值 SHALL 丢弃整个技能，MUST NOT 静默放行任何一面。名字不合规、frontmatter 缺失、描述为空或单个文件读不出的条目 SHALL 跳过，MUST NOT 让会话启动失败；**根目录本身扫不动**（`iterdir` 失败）SHALL 把这次发现标记为不完整（见「发现完整性」），MUST NOT 静默当作「没有技能」。描述进清单前 SHALL 截到 500 字符。同名技能 SHALL 只保留一个，rank 数字小者胜出；发现结果 SHALL 按名字排序，保证确定性。

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

`/<技能名>`（无指令）SHALL 把技能正文（XML 三段）与一句默认指令（「用户调用了技能 X，请按技能执行」）拼成一条 `user/message` 并开一个段；`/<技能名> <指令>` SHALL 用指令替换默认句。`/skill <名字>` 是**查看路径**：打印正文、不开段。展开消息由命令的结果触发，命令本身仍只落两件套。host 的 `POST /sessions/{id}/commands {name:"<技能名>", arguments:"<指令>"}` SHALL 返回 202 与 `{queued, segment_id, cursor}`（空闲起段、忙时排队），与消息投递同一条队列。

#### Scenario: 两个入口同一份清单

- **WHEN** CLI 执行 `/skills`，host 调用 `GET /commands?session_id=<id>`
- **THEN** 两边只返回用户可调的技能命令与内置命令

#### Scenario: 用户独占技能出现在命令面

- **WHEN** 一个技能写 `disable-model-invocation: true`
- **THEN** `/skills` 列出它、`/<技能名>` 能加载它，模型目录与 `skill` 工具里没有它

#### Scenario: 非用户可调技能不在命令面

- **WHEN** 一个技能写 `user-invocable: false`
- **THEN** `/skills` 不列它；`/skill <名字>` 返回 `ok=false`

#### Scenario: 不带指令也执行

- **WHEN** CLI 执行 `/tdd`
- **THEN** 日志里两件套事件、一条含技能正文的 `user/message`，随后 `segment/start`（模型按技能执行）

#### Scenario: 查看用 /skill

- **WHEN** CLI 执行 `/skill tdd`
- **THEN** 屏幕打印正文，日志里两件套事件，没有 `segment/start`

#### Scenario: 带指令展开成消息

- **WHEN** CLI 执行 `/tdd 帮我改个函数`
- **THEN** 日志里有 `command/run`（`name="tdd"`）、`command/done`、一条含技能正文与指令的 `user/message`，随后是一个新段

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

### Requirement: 发现完整性

`discover_skills` SHALL 返回技能清单与一个 `complete` 布尔。只有「根目录本身扫不动」或「preset 层目录本身扫不动」才把 `complete` 置为 `false`；单个文件坏掉、frontmatter 非法、目录不存在都 SHALL NOT 影响 `complete`。`complete=false` 时：

- `session/start.payload` SHALL 写 `skills_incomplete: true`；
- 受保护头部的技能块 SHALL 带一行「有一些技能目录没能检查到，只列确认的」，即使清单为空也 SHALL 出现；
- 下一次装配 SHALL 重新发现（mini 的发现是装配期快照，「重试」即下一会话），MUST NOT 沿用上一次的结果。

#### Scenario: 一个根读不了

- **WHEN** 某个根目录的 `iterdir` 抛 `OSError`
- **THEN** 其它根照常发现；`payload.skills_incomplete` 是 true；头部有警告行

#### Scenario: 单个文件坏掉不算不完整

- **WHEN** 一个 `SKILL.md` 读不出来、但根目录能扫
- **THEN** 该文件被跳过；`skills_incomplete` 不出现

#### Scenario: 修好之后下一次发现恢复

- **WHEN** 上一会话因为根读不了而不完整，修好权限后开新会话
- **THEN** 新会话的 `skills_incomplete` 不出现，技能正常列出

### Requirement: preset 作用域技能层

配置 SHALL 接受 `[subagent.presets.<id>.skills]`：`kind`（目前只接受 `filesystem`）与 `dirs`（字符串数组）。子会话的技能视图 SHALL 是「全局 provider 层」加「preset 的 provider 层」：**近层同名技能直接胜出**（MUST NOT 再看 rank）；同一层内按 provider 的 rank 与注册顺序裁决。根会话 MUST NOT 有 preset 层。目录不存在 SHALL 视为空层，MUST NOT 让会话启动失败。

命令面（`/skills`、`/<技能名>`、host 命令清单）SHALL 与模型目录读**同一份注册表快照**，MUST NOT 再读装配期的 `settings.skills`。

#### Scenario: preset 层覆盖同名技能

- **WHEN** 全局有一个 `tdd`，preset 的 `dirs` 里也有一个 `tdd`
- **THEN** 子会话看到 preset 那份；父会话仍是全局那份

#### Scenario: preset 层独有的技能

- **WHEN** 一个技能只在 preset 的 `dirs` 里
- **THEN** 子会话的清单与命令面有它，父会话没有

#### Scenario: 近层低 rank 仍胜

- **WHEN** preset 层的同名技能 rank 比全局层大
- **THEN** 仍然是 preset 层胜出

#### Scenario: 不存在的目录是空层

- **WHEN** `dirs` 指向一个不存在的目录
- **THEN** 子会话照常启动，没有该层的技能，`skills_incomplete` 不出现

#### Scenario: 命令面与模型目录同源

- **WHEN** 会话进行中新增一个技能
- **THEN** 模型目录与 `/skills` 都在下一次观察时看到它

### Requirement: 目录消息与按需加载

模型目录 SHALL 是一条 `user/message`，payload 含 `source: "skill-catalog"` 与 `incomplete: bool`；内容 SHALL 只含**模型可调**技能的 `name`、截断到 500 字符的 `description` 与来源层名 `source`，MUST NOT 含正文与路径。

在第一个 turn 的 `context/assembled` 之前，若存在模型可调技能或发现不完整，系统 SHALL 注入初始目录；之后每个 turn 之前 SHALL 重新观察（全局四根 + 子会话的 preset 层）并计算指纹（模型可调 `(name, description, source)` 列表 + `complete`）。指纹变化 SHALL 追加一条完整替换；指纹不变 MUST NOT 重复注入。

发现不完整 SHALL 发布「确认条目 + 警告」并标 `incomplete: true`，下一次观察 SHALL 重试；恢复完整 SHALL 追加无警告的替换。曾发过目录、现在模型可调条目为空且完整 SHALL 追加一条空目录消息，明确让模型不要使用旧名字；从未发过且为空 MUST NOT 注入。

受保护头部 MUST NOT 再含技能目录。`session/start.payload.skills` MAY 保留装配期快照（审计与命令面），但模型目录 MUST NOT 从它折叠。压缩若把目录消息的 seq 折进 `compaction/summary.shadowed_range`，下一次装配 SHALL 重新注入。

#### Scenario: 首个 turn 注入目录

- **WHEN** 会话有模型可调技能，开第一个 turn
- **THEN** `context/assembled` 之前有一条 `user/message`，`source` 是 `skill-catalog`，内容含 `<available_skills>`

#### Scenario: 指纹不变不重复

- **WHEN** 连续两个 turn 之间技能没有变化
- **THEN** 第二个 turn 之前没有新的目录消息

#### Scenario: 会话中途加技能

- **WHEN** 第一个 turn 之后在根里新增一个技能，跑第二个 turn
- **THEN** 第二个 turn 之前追加一条含新条目的替换目录

#### Scenario: 不完整与恢复

- **WHEN** 一次观察里某个根 `iterdir` 失败
- **THEN** 目录带警告与 `incomplete: true`；下一次观察恢复后追加无警告的替换

#### Scenario: 清空退休旧名字

- **WHEN** 之前发过目录，现在所有技能都被删除
- **THEN** 追加一条空目录消息，明确不要使用旧名字

#### Scenario: 头部不再有技能

- **WHEN** 任意会话启动
- **THEN** 受保护头部里没有「可用技能」块；目录只在 `user/message` 里

