# Spec Delta

## REMOVED Requirements

### Requirement: 同一份命令面（人机直连，不开段）

**Reason**: 技能命令带指令时要展开成一条 `user/message` 并开段，旧 Requirement 的名字与内容把「命令一律不开段」写死了。

**Migration**: 由下面新增的「同一份命令面（命令是 UI 动作；技能 + 指令展开成消息）」取代。

## ADDED Requirements

### Requirement: 同一份命令面（命令是 UI 动作；技能 + 指令展开成消息）

CLI `chat` SHALL 提供 `/skills`、`/skill <name>`、`/help` 与 `/<技能名>`；host SHALL 提供 `GET /commands` 与 `POST /sessions/{id}/commands`。两边 SHALL 共用同一份命令实现，返回同一份清单与同一份正文。

命令是人机直连的 UI 动作，MUST NOT 自己创建模型消息。命令调用 SHALL 落 `command/run`（handler 之前，`{command_id, name, raw_input}`）与 `command/done`（结算之后，`{command_id, ok, text?}`）两条只进日志的事件；语法错误或未知命令的 admission miss MUST NOT 落任何日志。`/help` 是壳本地的帮助，不落日志。

`/<技能名>`（无指令）SHALL 打印正文、不开段；`/<技能名> <指令>` SHALL 把技能正文（XML 三段）与指令拼成一条 `user/message` 并开一个段——展开消息由命令的结果触发，命令本身仍只落两件套。`GET /commands` SHALL 列内置命令；带 `?session_id=<id>` 时 SHALL 追加该会话发现到的技能命令。host 的 `POST /sessions/{id}/commands {name:"<技能名>", arguments:"<指令>"}` SHALL 返回 202 与 `{queued, segment_id, cursor}`（空闲起段、忙时排队），与消息投递同一条队列。

#### Scenario: 两个入口同一份清单

- **WHEN** CLI 执行 `/skills`，host 调用 `GET /commands?session_id=<id>`
- **THEN** 两边返回同一组 `{name, description}`（含技能命令），日志里各有一条 `command/run` + `command/done`

#### Scenario: 不带指令只查看

- **WHEN** CLI 执行 `/tdd`
- **THEN** 屏幕打印正文，日志里两件套事件，没有 `segment/start`

#### Scenario: 带指令展开成消息

- **WHEN** CLI 执行 `/tdd 帮我改个函数`
- **THEN** 日志里有 `command/run`（`name="tdd"`）、`command/done`、一条含技能正文与指令的 `user/message`，随后是一个新段

#### Scenario: host 展开并返回 202

- **WHEN** `POST /sessions/{id}/commands {name:"tdd", arguments:"帮我改个函数"}`
- **THEN** 返回 202 与 `{queued, segment_id, cursor}`；空闲时 `queued=false`，段进行中 `queued=true`

#### Scenario: 未知命令不落日志

- **WHEN** 执行 `/nope`
- **THEN** 本地提示未知命令，日志里没有任何 `command/*` 记录
