# Spec Delta

## MODIFIED Requirements

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
