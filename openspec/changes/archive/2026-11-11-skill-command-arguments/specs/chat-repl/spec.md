# Spec Delta

## MODIFIED Requirements

### Requirement: chat 的斜杠命令是人机直连的 UI 动作

`chat` SHALL 接受 `/<name>` 形式的斜杠命令：`/skills` 打印技能清单（名字、描述、rank）；`/skill <name>` 打印正文；`/<技能名>` 打印正文、不开段；`/<技能名> <指令>` 把技能正文与指令拼成一条 `user/message` 并开一个段；`/help` 打印命令清单（内置命令 + 当前会话的技能命令）。命令本身 MUST NOT 创建模型消息（展开消息由命令结果触发）；`/skills`、`/skill`、`/<技能名>`、`/<技能名> <指令>` SHALL 落 `command/run` + `command/done`；`/help` 与未知命令 MUST NOT 落日志（未知命令在 stderr 提示）。命令名与参数的分隔 SHALL 是一个空格。

#### Scenario: `/skills` 不开段

- **WHEN** 在提示符输入 `/skills`
- **THEN** 屏幕列出清单，日志里只有 `command/run` 与 `command/done`，没有 `segment/start`

#### Scenario: `/skill` 不开段

- **WHEN** 输入 `/skill tdd`
- **THEN** 屏幕打印正文，日志里只有 `command/run` 与 `command/done`，没有 `user/message` 或新段

#### Scenario: 直接技能名带指令开段

- **WHEN** 输入 `/tdd 帮我改个函数`
- **THEN** 日志里有 `command/run`（`name="tdd"`）、`command/done`、含正文与指令的 `user/message`，随后 `segment/start`
