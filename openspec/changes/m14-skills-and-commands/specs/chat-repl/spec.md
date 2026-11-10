# Spec Delta

## ADDED Requirements

### Requirement: chat 的斜杠命令

`chat` SHALL 接受 `/<name>` 形式的斜杠命令：`/skills` 打印技能清单（名字、描述、rank）并写一条 `command/invoked`，不开启段；`/skill <name>` 加载正文、写 `command/invoked` 与一条 `user/message`（正文）、开启一个段；`/help` 打印命令清单，不落日志。命令名与参数的分隔 SHALL 是一个空格；未知命令 SHALL 在 stderr 提示且不产生日志记录。

#### Scenario: `/skills` 不开段

- **WHEN** 在提示符输入 `/skills`
- **THEN** 屏幕列出清单，日志里有一条 `command/invoked`，没有新的 `segment/start`

#### Scenario: `/skill` 开段

- **WHEN** 输入 `/skill tdd`
- **THEN** 日志里有 `command/invoked` 与一条含正文的 `user/message`，随后是一个新段
