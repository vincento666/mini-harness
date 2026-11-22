# Spec Delta: cli

## ADDED Requirements

### Requirement: `/goal` 命令查看目标并做五个动作

`minihns chat` 与 host 的命令面 SHALL 支持 `/goal`、`/goal pause`、`/goal resume`、`/goal complete`、`/goal clear`、`/goal edit <新正文>`。会话内命令 MUST NOT 接受 `--flag` 形式的参数：带参数的定义编辑归 CLI 的 `minihns goal <session_id> edit [--max-rounds N] [正文]`（C 方案，2026-11-23）。

- `/goal` MUST 只读：打印当前目标的 `objective`、`phase`、`rounds_started/max_rounds`、`armed` 与阻塞原因，日志 MUST NOT 新增事件；
- `/goal pause` SHALL 写一条 `goal/updated`，`phase` 置 `paused`、`armed` 置假；
- `/goal resume` SHALL 写一条 `goal/updated`，`revision` 递增，`armed` 置真；对 `paused` 目标 SHALL 同时把 `phase` 置 `active`；
- `/goal complete` SHALL 写一条 `goal/updated`，`phase` 置 `complete`、`armed` 置假；已完成时打印原因、不写事件；
- `/goal edit <新正文>` SHALL 整段替换 `objective`、写一条 `goal/updated`、`revision` 递增；`phase` 与 `armed` MUST NOT 改变（改正文不等于重启目标）；不给正文 MUST 报用法，不写事件；
- 非动词的整段文本（`/goal <新正文>`）SHALL 等价于 `/goal edit <新正文>`（Codex 的形状）；
- `/goal clear` SHALL 写 `goal/updated {goal: null}`。

没有当前目标时，除 `/goal` 外的动作命令 MUST 打印提示并以 `0` 退出，MUST NOT 写 `goal/updated`；命令自己的 `command/run` / `command/done` 照常落（M14 的命令面规则：已知命令无论成败都留这一对）。

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

#### Scenario: 改上限在 CLI，不在提示符

- **WHEN** 目标 `blocked{round-limit}`，用户退出会话后执行 `minihns goal <id> edit --max-rounds 8`，再 `minihns chat --resume <id>` 并输入 `/goal resume`
- **THEN** 第一条命令后日志里的 `max_rounds == 8`、`phase` 仍 `blocked`；第二条命令后 `phase == "active"`、`armed == true`，随后出现下一轮

#### Scenario: edit 不动相位

- **WHEN** 目标 `active` 且未武装，用户输入 `/goal edit 把测试修到全绿`
- **THEN** `objective` 改为新正文、`revision` 递增，`phase` 仍 `active`、`armed` 仍假

#### Scenario: 动词不吃 flag

- **WHEN** 用户输入 `/goal edit --max-rounds 8`
- **THEN** `objective` 变成字面量 `--max-rounds 8`（当正文处理），不是改上限；要改上限用 CLI 子命令

#### Scenario: 人工标完成

- **WHEN** 用户输入 `/goal complete`
- **THEN** 日志新增 `goal/updated`，`phase == "complete"`、`armed == false`，不再出现新的 goal 来源消息

#### Scenario: 已在自动推进时不另起一轮

- **WHEN** 目标 `active` 且已武装（例如未决问题刚把控制权交回人类），用户习惯性输入 `/goal resume`
- **THEN** 打印「已经在自动推进（无需 resume）」；不出现新的 goal 来源 `user/message`，`rounds_started` 不变

### Requirement: CLI 的 `goal` 子命令做离线定义编辑

`minihns goal <session_id> [--session-dir DIR] show|edit|clear` SHALL 读写该会话日志里的目标定义：`show` 打印快照、`edit` 至少给一个有效字段并写 `goal/updated`、`clear` 写 `goal: null`。它 MUST NOT 提供 `pause` / `resume` / `complete`——那三个是运行期控制，离线写会产生「没人按过」的动作。`edit` 的 `max_rounds` SHALL 以部署上限 `DEFAULT_MAX_ROUNDS` 为硬顶。日志不存在时 MUST 以退出码 1 报 `SESSION_NOT_FOUND`；参数缺失 MUST 以退出码 2 报 `INVALID_ARGUMENT`。

#### Scenario: 离线改上限

- **WHEN** 用户执行 `minihns goal s1 edit --max-rounds 8 写成两节`
- **THEN** 日志新增一条 `goal/updated`：`objective == "写成两节"`、`max_rounds == 8`、`revision` 递增、`phase` 不变

#### Scenario: 不做运行期控制

- **WHEN** 用户尝试 `minihns goal s1 pause`
- **THEN** 参数解析失败（退出码 2），不写日志
