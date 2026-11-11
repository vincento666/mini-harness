# Spec Delta

## ADDED Requirements

### Requirement: 命令面

`GET /commands` SHALL 返回本进程可执行的命令清单，每项含 `name` 与 `description`。`POST /sessions/{id}/commands` SHALL 接受 `{name, arguments}`，执行与 CLI 相同的命令实现，写 `command/run` + `command/done`，并返回 200 与 `{output, cursor}`；它 MUST NOT 创建模型消息或开启段。未知命令或参数不合法 SHALL 是 400 的 `INVALID_ARGUMENT` 信封且不写日志。鉴权、来源与错误信封与其它会话路由一致。

#### Scenario: 列命令

- **WHEN** 已授权客户端 `GET /commands`
- **THEN** 返回含 `skills` 与 `skill` 的清单

#### Scenario: 执行命令

- **WHEN** `POST /sessions/{id}/commands {name:"skill", arguments:"tdd"}`
- **THEN** 返回 200 与正文，日志里有 `command/run` + `command/done`，没有 `user/message` 或新段

#### Scenario: 未知命令

- **WHEN** `POST` 一个不存在的命令名
- **THEN** 返回 400 的 `INVALID_ARGUMENT` 信封，不写日志
