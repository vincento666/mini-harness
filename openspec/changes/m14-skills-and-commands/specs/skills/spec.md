# Spec Delta

## ADDED Requirements

### Requirement: 技能发现按四级根与优先级

系统 SHALL 从四个根发现技能：项目内 `<workspace>/.minihns/skills/`（rank 100）、项目共享 `<workspace>/.agents/skills/`（rank 200）、用户级 `$MINIHNS_HOME/skills/`（默认 `~/.mini-harness/skills/`，rank 500）、内置 `src/mini_harness/skills/`（rank 600）。一个技能 SHALL 是 `<dir>/SKILL.md` 或扁平的 `<name>.md`；可选的 frontmatter 只认 `name` 与 `description` 两个键，缺失时名字回退到目录名/文件名、描述为空。同名技能 SHALL 只保留一个，rank 数字小者胜出；发现结果 SHALL 按 `(rank, path)` 排序，保证确定性。没有名字或读不出的条目 SHALL 跳过，MUST NOT 让会话启动失败。

#### Scenario: 四级根各有一个技能

- **WHEN** 四个根里各放一个不同名的技能
- **THEN** 清单按 rank 100 → 200 → 500 → 600 排列

#### Scenario: 同名技能高优先级胜出

- **WHEN** 项目内与用户级各有一个 `tdd` 技能
- **THEN** 清单里只有一个 `tdd`，来自项目内（rank 100）

#### Scenario: 坏文件不拖垮启动

- **WHEN** 某个根里有一个读不出名字的 `SKILL.md`
- **THEN** 它被跳过，会话照常开始

### Requirement: 清单注入，正文按需加载

`session/start.payload.skills` SHALL 只放清单项 `{name, description, rank, path}`，MUST NOT 含正文。受保护头部 SHALL 放紧凑清单（名字 + 一句描述），并受字符预算约束（默认 2000 字符）；超出时截断并留「还有 N 个技能未列出」的 marker。正文 MUST NOT 进受保护头部；它只在 `skill` 工具被调用后作为 `tool/result` 进入上下文与日志。

#### Scenario: 头部只有清单

- **WHEN** 一个技能存在且会话启动
- **THEN** `session/start.payload.skills` 有它的 `{name, description, rank, path}`；头部有名字与描述，没有正文

#### Scenario: 超预算截断

- **WHEN** 技能多到超过字符预算
- **THEN** 头部只列前若干个，并带「还有 N 个技能未列出」

### Requirement: `skill` 工具按需读正文

系统 SHALL 提供 `skill` 工具，参数 `{name}`，返回该技能的正文（单次上限 32 KiB，超出截断并提示用 `read` 读全文）。未知名字 SHALL 是 `TOOL_ARGS_INVALID`。正文 SHALL 作为 `tool/result` 落日志，`replay` MUST NOT 依赖磁盘上的当前文件内容。

#### Scenario: 加载正文

- **WHEN** 模型调用 `skill(name="tdd")`
- **THEN** 结果是正文，日志里有配对的 `tool/call` + `tool/result`

#### Scenario: 未知技能

- **WHEN** `skill(name="nope")`
- **THEN** 结果是 `TOOL_ARGS_INVALID`，不读任何文件

#### Scenario: 正文超限

- **WHEN** 正文超过 32 KiB
- **THEN** 结果截断并提示用 `read` 读全文

### Requirement: 同一份命令面

CLI `chat` SHALL 提供 `/skills`、`/skill <name>`、`/help`；host SHALL 提供 `GET /commands` 与 `POST /sessions/{id}/commands`。两边 SHALL 共用同一份命令实现，返回同一份清单与同一份正文。命令调用 SHALL 落一条 `command/invoked {name, arguments, ok}`（只进日志、不进 transcript）：`/skills` 只写这一条、不开启段；`/skill <name>` 成功时 SHALL 再写一条 `user/message`（内容是渲染后的正文）并开启一个段。未知命令 SHALL 被拒绝且不落日志。

#### Scenario: 两个入口同一份清单

- **WHEN** CLI 执行 `/skills`，host 调用 `GET /commands`
- **THEN** 两边返回同一组 `{name, description}`

#### Scenario: 两个入口同一份正文

- **WHEN** CLI 执行 `/skill tdd`，host 调用 `POST /commands {name:"skill", arguments:"tdd"}`
- **THEN** 两边加载同一份正文，日志里都有 `command/invoked`；正文作为 `user/message` 进各自的段

#### Scenario: 未知命令

- **WHEN** 执行 `/nope`
- **THEN** 本地提示未知命令，日志里没有 `command/invoked`
