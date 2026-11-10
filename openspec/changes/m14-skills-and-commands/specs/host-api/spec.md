# Spec Delta

## ADDED Requirements

### Requirement: 命令面

`GET /commands` SHALL 返回本进程可执行的命令清单，每项含 `name` 与 `description`；它 SHALL 与 CLI 的 `/help` 同源。`POST /sessions/{id}/commands` SHALL 接受 `{name, arguments}`：`skills` 返回 200 与清单（写一条 `command/invoked`，不开启段）；`skill` 在段空闲时开启一个段、返回 202 与 `{segment_id, cursor}`，段进行中返回 202 与 `{queued: true}`（与消息队列同一条）；未知命令或参数不合法 SHALL 是 400 的 `INVALID_ARGUMENT` 信封。鉴权、来源与错误信封与其它会话路由一致。

#### Scenario: 列命令

- **WHEN** 已授权客户端 `GET /commands`
- **THEN** 返回含 `skills` 与 `skill` 的清单

#### Scenario: 执行命令

- **WHEN** `POST /sessions/{id}/commands {name:"skill", arguments:"tdd"}`
- **THEN** 返回 202，日志里有 `command/invoked` 与一条 `user/message`

#### Scenario: 未知命令

- **WHEN** `POST` 一个不存在的命令名
- **THEN** 返回 400 的 `INVALID_ARGUMENT` 信封，不写日志
