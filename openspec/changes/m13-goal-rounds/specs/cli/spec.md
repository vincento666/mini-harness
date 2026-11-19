# Spec Delta: cli

## ADDED Requirements

### Requirement: `/goal` 命令查看目标并做三个动作

`minihns chat` SHALL 支持 `/goal`、`/goal pause`、`/goal resume`、`/goal clear`：

- `/goal` MUST 只读：打印当前目标的 `objective`、`phase`、`rounds_started/max_rounds`、`armed` 与阻塞原因，日志 MUST NOT 新增事件；
- `/goal pause` SHALL 写一条 `goal/updated`，`phase` 置 `paused`、`armed` 置假；
- `/goal resume` SHALL 写一条 `goal/updated`，`revision` 递增，`armed` 置真；对 `paused` 目标 SHALL 同时把 `phase` 置 `active`；
- `/goal clear` SHALL 写 `goal/updated {goal: null}`。

没有当前目标时，四个命令 MUST 打印提示并以 `0` 退出，MUST NOT 写 `goal/updated`；命令自己的 `command/run` / `command/done` 照常落（M14 的命令面规则：已知命令无论成败都留这一对）。

#### Scenario: 查看不写事件

- **WHEN** 用户输入 `/goal`
- **THEN** 终端打印目标摘要，日志里没有新增 `goal/updated`

#### Scenario: 暂停后再跑一轮不续跑

- **WHEN** 用户输入 `/goal pause`，随后发一句话开启新段
- **THEN** 段结束后没有新的 goal 来源 `user/message`

#### Scenario: 人工续跑

- **WHEN** 用户输入 `/goal resume`
- **THEN** 日志新增 `goal/updated`，`phase == "active"`、`revision` 比之前大一；命令返回后**立刻**出现 goal 来源的 `user/message` 与新一轮，不再等人另敲一行

#### Scenario: 无目标时的命令

- **WHEN** 会话里没有目标，用户输入 `/goal resume`
- **THEN** 打印「没有当前目标」，退出码 `0`，日志里没有新增 `goal/updated`

#### Scenario: 清除后读回为空

- **WHEN** 用户输入 `/goal clear`，随后输入 `/goal`
- **THEN** 后者打印「没有当前目标」，`get_goal()` 返回 `{"goal": null}`
