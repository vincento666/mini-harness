# Spec Delta

## MODIFIED Requirements

### Requirement: chat 的 stdout 只打印模型回复正文与命令输出

系统 SHALL 在 stdout 上按发生顺序打印每条**不带 `purpose`**、且 `content` 去掉首尾空白后非空 的 `model/response` 的 `content` 原文；斜杠命令的结果文本（`command/done.text`）SHALL 也打印在 stdout 上。提示符 SHALL 打印在**不带换行**的同一行上，用户输入紧跟在提示符之后。MUST NOT 打印工具结果、`context/assembled`、`user/message` 或日志的其它投影；MUST NOT 因为一条空或全空白的 `content` 而在 stdout 上留下空行。带 `purpose` 的那次 `model/response` 是请求级压缩产出的内部摘要，不是给人的回复。

#### Scenario: 工具结果不上 stdout

- **WHEN** 一个回合派发一次 `read` 并拿到结果
- **THEN** stdout 里没有出现该工具结果的内容，只有模型回复正文、命令输出与提示符

#### Scenario: 命令输出上 stdout

- **WHEN** 在提示符输入 `/skills`
- **THEN** stdout 里有清单文本，且没有新的 `segment/start`

#### Scenario: 请求级压缩的摘要不上 stdout

- **WHEN** 一次请求级压缩写出带 `purpose` 的 `model/response`
- **THEN** stdout 里没有那条摘要的内容

#### Scenario: 提示符不自带换行

- **WHEN** 一次 chat 的一条输入开一个段、该段以 `MODEL_COMPLETED` 收尾，stdin 是管道
- **THEN** stdout 上提示符与紧随其后的模型回复正文之间没有换行（该段只有一条带正文的回复、且没有命令输入时，stdout 恰为 `> <正文>\n> `）

## ADDED Requirements

### Requirement: chat 的斜杠命令是人机直连的 UI 动作

`chat` SHALL 接受 `/<name>` 形式的斜杠命令：`/skills` 打印技能清单（名字、描述、rank）；`/skill <name>` 打印正文；`/help` 打印命令清单。命令 MUST NOT 创建模型消息、MUST NOT 开启段。`/skills` 与 `/skill` SHALL 落 `command/run` + `command/done`；`/help` 与未知命令 MUST NOT 落日志（未知命令在 stderr 提示）。命令名与参数的分隔 SHALL 是一个空格。

#### Scenario: `/skills` 不开段

- **WHEN** 在提示符输入 `/skills`
- **THEN** 屏幕列出清单，日志里只有 `command/run` 与 `command/done`，没有 `segment/start`

#### Scenario: `/skill` 不开段

- **WHEN** 输入 `/skill tdd`
- **THEN** 屏幕打印正文，日志里只有 `command/run` 与 `command/done`，没有 `user/message` 或新段
