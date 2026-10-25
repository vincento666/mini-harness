# Spec Delta

## ADDED Requirements

### Requirement: bash 的描述点明原生工具优先
`bash` 的描述 SHALL 点明它跑的是真命令（构建、测试、版本控制、进程），列目录、搜内容、读文件这类等价能力 SHALL 引导去用 `glob` / `grep` / `read`。这份描述 MUST 与平台无关：平台相关的那半句只出现在头部的运行环境块里，否则同一份事实会有两个来源（ADR-0029 / ADR-0030）。

#### Scenario: bash 的描述把列目录指给 glob
- **WHEN** 读一次 run 发给模型的工具表里 `bash` 的描述
- **THEN** 描述把列目录与搜内容指给 `glob` 与 `grep`，并点明不要用 `ls` / `grep` / `cat` 这类等价命令

#### Scenario: bash 的描述里没有平台专用命令
- **WHEN** 读这份描述
- **THEN** 它不含 `dir`、`findstr`、`Get-Content` 这类只在某一个平台上成立的字样，也不把「临时写一段脚本」当作推荐手段
