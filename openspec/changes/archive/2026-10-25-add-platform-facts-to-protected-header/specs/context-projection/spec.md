# Spec Delta

## ADDED Requirements

### Requirement: 头部的运行环境块由日志前缀派生
系统 SHALL 在受保护头部里放一块运行环境，内容取自该装配点之前的 `session/start` 的 `platform`（`os` 与 `shell`），位置在内置系统提示与工具块之后、追加文本之前。该块 MUST NOT 取自进程内注册表或该装配点之后的事件，也 MUST NOT 成为可由调用方替换的头部。

#### Scenario: 新会话的头部含运行环境块
- **WHEN** 一次 run 的 `session/start` payload 里 `platform` 记着 `os` 与 `shell`
- **THEN** 该会话每条 `context/assembled` 的头部里都有一条消息同时含这两个值，且 `header_fingerprint` 覆盖它

#### Scenario: 运行环境块逐点重放复现
- **WHEN** 对一份带 `platform` 的日志逐点重算折叠
- **THEN** 每条 `context/assembled` 与该记录逐字段相等，没有 `REPLAY_MISMATCH`

#### Scenario: 运行环境块不可由调用方替换
- **WHEN** 运行时传入 `--append-system-prompt "额外规则"`
- **THEN** 追加文本仍在运行环境块之后，头部里没有替换掉 `os` 与 `shell` 的入口

### Requirement: 运行环境块先点原生工具、再点本平台的 shell 命令
运行环境块 SHALL 在事实之外带一句建议：**先**点出原生工具（列文件用 `glob`、搜内容用 `grep`、读文件用 `read`），**再**点出这个平台的 shell 命令——记下来的 `shell` 是 `cmd.exe` 一类时给 `dir` / `findstr` / `Get-Content`，是 POSIX shell 时给 `ls -R` / `tail`。这句建议 MUST 由记下来的 `platform` 推出，MUST NOT 看折叠那一刻所在机器的平台——否则换一台机器重放会得到不同的头部。

#### Scenario: 原生工具排在 shell 命令之前
- **WHEN** 折叠一份带 `platform` 的日志
- **THEN** 运行环境块里 `glob` 出现的位置在 `dir`（记 posix 时是 `ls -R`）之前，两处建议不构成「同一件事两个说法」

#### Scenario: Windows 事实给 Windows 建议
- **WHEN** 折叠一份 `platform` 记着 `os` 为 `nt`、`shell` 为 `cmd.exe /c` 的日志（判据跑在哪个平台上都一样）
- **THEN** 运行环境块里点出 `dir`、`findstr`、`Get-Content`，且没有把 `ls` 说成可用命令

#### Scenario: POSIX 事实给 POSIX 建议
- **WHEN** 折叠一份 `platform` 记着 `os` 为 `posix`、`shell` 为 `/bin/sh -c` 的日志
- **THEN** 运行环境块里点出 `ls -R`、`tail`（`grep` 已在前一句原生工具里点过），且没有把 `dir` 说成可用命令

### Requirement: 没有平台事实的旧日志头部逐字节不变
当 `session/start` 的 payload 里没有 `platform` 时，系统 SHALL 不产出运行环境块，折叠出来的头部只有内置系统提示、工具块与追加文本。系统 MUST NOT 为缺失的平台事实填入猜测值。

#### Scenario: 旧日志的折叠结果不变
- **WHEN** 折叠一份 `session/start` 没有 `platform` 的日志
- **THEN** 头部与这条事实存在之前写下的形状逐字段相等，`header_fingerprint` 与该记录里的一致

#### Scenario: 旧日志 replay 不出 REPLAY_MISMATCH
- **WHEN** 对一份这样的日志跑 `minihns replay <session_id>`
- **THEN** 每个装配点都是 `verified … OK`，退出码为 0

## MODIFIED Requirements

### Requirement: 折叠产出形状为受保护头部加保留尾部
系统 SHALL 把受保护头部（内置系统提示 + 工具块 + 运行环境块 + 追加文本）放在折叠结果最前，其后按事件发生顺序保留对话体：`role` 为 `user` 的消息有两个来源——一次性 `run` 的 `session/start` payload 里的 prompt（对话体第一条），以及 REPL 的 `user/message` 记录（按 `seq` 顺序进对话体）。随后是 assistant 消息与工具结果消息。`user/message` 与其它正文记录一样可进遮蔽范围。`segment/start` 与 `segment/end` 与 `turn/*` 一样是记账记录，MUST NOT 产出上下文里的消息，遮蔽它们对折叠结果没有效果。被 `compaction/summary` 遮蔽的记录不进入对话体（见「遮蔽范围由 compaction/summary 记录定义」）。

#### Scenario: 用户 prompt 是对话体第一条
- **WHEN** 一次 run 的 `session/start` payload 里 `prompt` 为「写一份报告」
- **THEN** 折叠结果里受保护头部之后的第一条消息 `role` 为 `user`、`content` 为该 prompt 原文

#### Scenario: 头部不被对话内容顶替
- **WHEN** fixture 的模型回复文本与内置系统提示完全相同
- **THEN** 折叠结果的第一条消息仍是内置系统提示

#### Scenario: 工具结果按顺序进入对话体
- **WHEN** 某回合产生一次 `tool/call` 与对应 `tool/result`
- **THEN** 折叠结果按发生顺序包含该 assistant 工具请求消息与对应工具结果消息

#### Scenario: REPL 的输入按 seq 顺序进对话体
- **WHEN** 一份日志里有两条 `user/message`，中间夹着一组工具往返
- **THEN** 折叠结果里两条 `role` 为 `user` 的消息与那组往返按 `seq` 顺序出现，且头部之后第一条仍是第一条输入

#### Scenario: 被遮蔽的输入不进对话体
- **WHEN** 一条 `user/message` 落在某条 `compaction/summary` 的 `shadowed_range` 内
- **THEN** 折叠结果里没有它对应的 `user` 消息，该摘要的 `system` 消息在表层里
