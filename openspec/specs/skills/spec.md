# skills Specification

## Purpose
TBD - created by archiving change m14-skills-and-commands. Update Purpose after archive.
## Requirements
### Requirement: 技能发现按四级根与优先级

系统 SHALL 从四个根发现技能：项目内 `<workspace>/.minihns/skills/`（rank 100）、项目共享 `<workspace>/.agents/skills/`（rank 200）、用户级 `$MINIHNS_HOME/skills/`（默认 `~/.mini-harness/skills/`，rank 400）、内置 `src/mini_harness/builtin_skills/`（rank 600）。300（自定义目录）与 500（agents 家目录）不在本 change。

一个技能 SHALL 是 `<dir>/SKILL.md` 或扁平的 `<name>.md`，MUST NOT 递归发现子目录；名字 SHALL 匹配 kebab-case（`^[a-z0-9]+(?:-[a-z0-9]+)*$`），不合规或读不出的条目 SHALL 跳过，MUST NOT 让会话启动失败。可选的 frontmatter 只认 `name` 与 `description` 两个键；缺失时名字回退到目录名/文件名、描述为空。描述进清单前 SHALL 截到 500 字符。同名技能 SHALL 只保留一个，rank 数字小者胜出；发现结果 SHALL 按 `(rank, path)` 排序，保证确定性。

#### Scenario: 四级根各有一个技能

- **WHEN** 四个根里各放一个不同名的技能
- **THEN** 清单按 rank 100 → 200 → 400 → 600 排列

#### Scenario: 同名技能高优先级胜出

- **WHEN** 项目内与用户级各有一个 `tdd` 技能
- **THEN** 清单里只有一个 `tdd`，来自项目内（rank 100）

#### Scenario: 名字不合规的条目被跳过

- **WHEN** 某个根里有一个名字带大写的 `Bad_Name.md`
- **THEN** 它不出现在清单里，会话照常开始

### Requirement: 清单注入，正文按需加载

`session/start.payload.skills` SHALL 只放清单项 `{name, description, rank, path}`，MUST NOT 含正文。受保护头部 SHALL 放紧凑清单（名字 + 一句描述），并受字符预算约束（默认 2000 字符）；超出时截断并留「还有 N 个技能未列出」的 marker。正文 MUST NOT 进受保护头部；它只在 `skill` 工具被调用后作为 `tool/result` 进入上下文与日志。

#### Scenario: 头部只有清单

- **WHEN** 一个技能存在且会话启动
- **THEN** `session/start.payload.skills` 有它的 `{name, description, rank, path}`；头部有名字与描述，没有正文

#### Scenario: 超预算截断

- **WHEN** 技能多到超过字符预算
- **THEN** 头部只列前若干个，并带「还有 N 个技能未列出」

### Requirement: `skill` 工具按需读正文

系统 SHALL 提供 `skill` 工具，参数 `{name}`，返回该技能的正文（单次上限 32 KiB，超出截断并提示用 `read` 读全文）。结果 SHALL 是 DSH 同形的 XML 三段：`<skill_content name=…>` 包 `<skill_resources>`（技能文件路径）与 `<skill_instructions>`（正文）。未知名字 SHALL 是 `TOOL_ARGS_INVALID`。正文 SHALL 作为 `tool/result` 落日志，`replay` MUST NOT 依赖磁盘上的当前文件内容。

#### Scenario: 加载正文

- **WHEN** 模型调用 `skill(name="tdd")`
- **THEN** 结果是 `<skill_content>` + `<skill_instructions>`，含该技能正文；日志里有配对的 `tool/call` + `tool/result`

#### Scenario: 未知技能

- **WHEN** `skill(name="nope")`
- **THEN** 结果是 `TOOL_ARGS_INVALID`，不读任何文件

#### Scenario: 正文超限

- **WHEN** 正文超过 32 KiB
- **THEN** 结果截断并提示用 `read` 读全文

### Requirement: 同一份命令面（人机直连，不开段）

CLI `chat` SHALL 提供 `/skills`、`/skill <name>`、`/help`；host SHALL 提供 `GET /commands` 与 `POST /sessions/{id}/commands`。两边 SHALL 共用同一份命令实现，返回同一份清单与同一份正文。

**每个发现的技能 SHALL 以其名字作为一条命令**：chat 的 `/<name>` 与 `/skill <name>` 等价；host 的 `POST /sessions/{id}/commands {name:"<name>"}` 与 `{name:"skill", arguments:"<name>"}` 等价。内置命令名（`skills`、`skill`、`help`）与技能名冲突时**内置胜出**；`/<name>` 带多余参数 SHALL 是 handler 错误（`ok=false`），照常落两件套。`GET /commands` SHALL 列内置命令；带 `?session_id=<id>` 时 SHALL 追加该会话发现到的技能命令。

命令是人机直连的 UI 动作：MUST NOT 创建模型消息、MUST NOT 开启段。命令调用 SHALL 落 `command/run`（handler 之前，`{command_id, name, raw_input}`）与 `command/done`（结算之后，`{command_id, ok, text?}`）两条只进日志的事件；语法错误或未知命令的 admission miss MUST NOT 落任何日志。`/help` 是壳本地的帮助，不落日志。

#### Scenario: 两个入口同一份清单

- **WHEN** CLI 执行 `/skills`，host 调用 `GET /commands?session_id=<id>`
- **THEN** 两边返回同一组 `{name, description}`（含技能命令），日志里各有一条 `command/run` + `command/done`，且没有新的段

#### Scenario: 两个入口同一份正文

- **WHEN** CLI 执行 `/skill tdd`，host 调用 `POST /commands {name:"skill", arguments:"tdd"}`
- **THEN** 两边加载同一份正文并以 `command/done.text` 返回；没有 `user/message`、没有新的段

#### Scenario: 直接技能命令与 skill 命令等价

- **WHEN** CLI 执行 `/tdd`，host 调用 `POST /commands {name:"tdd"}`
- **THEN** 两边得到的正文与 `/skill tdd` 相同，日志里 `command/run.name` 是 `"tdd"`

#### Scenario: 内置命令同名时内置胜出

- **WHEN** 一个技能叫 `skills`
- **THEN** `/skills` 仍然列清单，不会加载那个技能；用 `/skill skills` 才能加载它

#### Scenario: 未知命令不落日志

- **WHEN** 执行 `/nope`
- **THEN** 本地提示未知命令，日志里没有任何 `command/*` 记录

